//! A boid flocking tick, computed natively.
//!
//! The second gameplay port, and a deliberately different shape from the
//! flow field's. A field is *opaque* -- nothing outside
//! `FlowFieldService` reads a cell -- so its state never comes back to
//! Python and only a query crosses, which is why it prices at 50x. A
//! flock is the opposite: every agent is an ECS entity whose `Transform`
//! and `FlockingAgent` are read by rendering, animation and game code, so
//! positions and velocities *must* cross every tick. That bounds this port
//! at **19x** before a line of it is written, and it is the reason ADR
//! 0004 ranks it second rather than first.
//!
//! So this holds no state between ticks beyond scratch buffers: one call
//! takes the whole flock in and hands the whole flock back. Measured at
//! 1000 agents, a Python tick is 17.1 ms, of which the unavoidable
//! crossing -- packing 15 floats per agent in, writing 4 back out -- is
//! 0.9 ms.
//!
//! # Why this one is not bit-exact, and what is asserted instead
//!
//! `SpatialHash._cells` is a `dict[Cell, set[int]]`, and a radius query
//! yields each cell's members in **CPython set iteration order**: a
//! function of the slot numbers' hashes, the table size and the insertion
//! history. Reproducing it here would mean reimplementing a CPython
//! internal and depending on it not changing. So the neighbour *order*
//! differs, and `flock_force` sums over neighbours, and float addition is
//! not associative -- the force differs in its last bits. Measured over
//! 1000 agents: 46% of agents get a different force, worst relative
//! difference 6.4e-13.
//!
//! That is not "Python is right and this is close". Both are equally
//! correct summations of the same numbers; the Python answer simply is not
//! canonical, because it is whatever CPython's set internals produce for
//! this interpreter. Demanding bit-exactness here would demand more
//! determinism of this code than the Python it mirrors offers.
//!
//! What *is* asserted, because it does not depend on order:
//!
//! 1. **The neighbour sets are identical, exactly.** Order is free, but
//!    membership is not: `query_radius` confirms every candidate against
//!    an exact squared distance, so the neighbourhood is a property of the
//!    positions alone. `neighbour_counts()` exists so the parity suite can
//!    check that cell by cell rather than inferring it from a force.
//! 2. **Every other operation is bit-exact**, and that is load-bearing
//!    rather than tidy. A transcription slip -- `dx * (s / len)` for
//!    `(dx / len) * s` -- moves a result by about one ulp, which is three
//!    orders of magnitude *below* the ordering noise above. No tolerance
//!    wide enough to admit the ordering could ever catch it. So the
//!    tolerance has exactly one permitted cause, and the parity suite
//!    pins the arithmetic separately, in the one regime where ordering
//!    cannot intrude: an agent with no more than one neighbour, where the
//!    sum has no order to differ in and `==` applies.
//!
//! See `docs/adr/0004-the-native-boundary.md`, Decision 5.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::grid::{check_query_span, Grid};

/// Floats per agent in the uploaded row, as `FlockingSystem._pack` writes
/// it: `x, y, vx, vy` then the eleven tuning values.
const STRIDE: usize = 15;

/// One agent's tuning, read straight out of the uploaded row.
#[derive(Clone, Copy, Default)]
struct Params {
    max_speed: f64,
    max_force: f64,
    mass: f64,
    neighbor_radius: f64,
    separation_radius: f64,
    cohesion_weight: f64,
    alignment_weight: f64,
    separation_weight: f64,
    /// Already zeroed by the caller when there is no `seek_target`, so
    /// `!= 0.0` here is exactly Python's
    /// `if agent.seek_weight and agent.seek_target is not None`.
    seek_weight: f64,
    seek_x: f64,
    seek_y: f64,
}

/// `Vec2d.length`, as `Vector2` overrides it: `sqrt(x * x + y * y)`.
///
/// Spelled out rather than borrowed from `hypot`, which is a different
/// (and more careful) algorithm and does not agree with either.
#[inline]
fn length(x: f64, y: f64) -> f64 {
    (x * x + y * y).sqrt()
}

/// `vector.normalized() * target`, in pymunk's order of operations.
///
/// `normalized()` is `self / length`, then `__mul__` scales -- so it is
/// `(x / length) * target`, not `x * (target / length)`. The two differ by
/// an ulp, which is exactly the kind of difference the parity suite's
/// bit-exact regime exists to catch.
#[inline]
fn scaled_to(x: f64, y: f64, len: f64, target: f64) -> (f64, f64) {
    if len != 0.0 {
        ((x / len) * target, (y / len) * target)
    } else {
        // What `Vec2d.normalized()` returns for a zero vector; scaling it
        // leaves it zero.
        (0.0, 0.0)
    }
}

/// Steers a whole flock in one crossing.
///
/// Stateless between ticks by design: the module docstring explains why
/// the alternative is not available to a system whose agents are ECS
/// entities. The buffers held here are scratch, reused so that a steady
/// flock allocates nothing per tick.
#[pyclass]
#[derive(Default)]
pub struct NativeFlockingSolver {
    /// Positions as they were at the start of the tick. The grid is built
    /// from these and the radius test reads them -- see `tick`.
    snap_x: Vec<f64>,
    snap_y: Vec<f64>,
    /// Positions and velocities as the sweep leaves them, read by agents
    /// later in the same sweep.
    live_x: Vec<f64>,
    live_y: Vec<f64>,
    vel_x: Vec<f64>,
    vel_y: Vec<f64>,
    params: Vec<Params>,
    grid: Grid,
    scratch: Vec<u32>,
    /// How many flockmates each agent steered by, for the parity suite.
    counts: Vec<u32>,
}

impl NativeFlockingSolver {
    /// Sum cohesion, alignment and separation for one agent.
    ///
    /// A transcription of `flock_force`, in its order of operations: the
    /// three reductions share one pass over the neighbourhood, distances
    /// are compared squared, and `Vector2` never appears.
    ///
    /// The two reads are deliberately split, and this is the Gauss-Seidel
    /// behaviour `FlockingSystem._neighbors_of` warns against losing.
    /// *Which* agents are flockmates is decided from the snapshot, because
    /// the Python hash is built once at the start of the tick and the
    /// radius test runs against what it holds. *What* they contribute is
    /// read live, because `_neighbors_of` yields the component values at
    /// the moment it is iterated -- so an agent already steered this tick
    /// contributes its new position and new velocity. Snapshotting both
    /// would quietly turn this into a Jacobi solver and change how a flock
    /// settles.
    fn flock_force(&mut self, slot: usize) -> (f64, f64) {
        let agent = self.params[slot];
        let max_speed = agent.max_speed;
        let separation_radius = agent.separation_radius;
        let separation_radius_sq = separation_radius * separation_radius;
        let want_cohesion = agent.cohesion_weight != 0.0;
        let want_alignment = agent.alignment_weight != 0.0;
        let want_separation = agent.separation_weight != 0.0;

        let x = self.live_x[slot];
        let y = self.live_y[slot];

        self.grid.neighbours(
            x,
            y,
            agent.neighbor_radius,
            &self.snap_x,
            &self.snap_y,
            &mut self.scratch,
        );

        let mut count = 0u32;
        let (mut sum_x, mut sum_y) = (0.0f64, 0.0f64);
        let (mut sum_vx, mut sum_vy) = (0.0f64, 0.0f64);
        let (mut push_x, mut push_y) = (0.0f64, 0.0f64);

        for &found in &self.scratch {
            let other = found as usize;
            if other == slot {
                continue;
            }
            count += 1;
            let neighbor_x = self.live_x[other];
            let neighbor_y = self.live_y[other];

            if want_cohesion {
                sum_x += neighbor_x;
                sum_y += neighbor_y;
            }
            if want_alignment {
                sum_vx += self.vel_x[other];
                sum_vy += self.vel_y[other];
            }
            if !want_separation {
                continue;
            }

            let offset_x = x - neighbor_x;
            let offset_y = y - neighbor_y;
            let distance_sq = offset_x * offset_x + offset_y * offset_y;
            if distance_sq >= separation_radius_sq {
                continue;
            }
            if distance_sq < 1e-06 {
                // Coincident agents: push in a fixed, stable direction
                // rather than dividing by zero.
                push_x += max_speed;
                continue;
            }
            let distance = distance_sq.sqrt();
            let scale = (1.0 - distance / separation_radius) * max_speed / distance;
            push_x += offset_x * scale;
            push_y += offset_y * scale;
        }

        self.counts[slot] = count;
        if count == 0 {
            return (0.0, 0.0);
        }

        let velocity_x = self.vel_x[slot];
        let velocity_y = self.vel_y[slot];
        let (mut force_x, mut force_y) = (0.0f64, 0.0f64);
        let inverse_count = 1.0 / f64::from(count);

        if want_cohesion {
            let direction_x = sum_x * inverse_count - x;
            let direction_y = sum_y * inverse_count - y;
            let direction_sq = direction_x * direction_x + direction_y * direction_y;
            if direction_sq >= 1e-06 {
                let scale = max_speed / direction_sq.sqrt();
                let weight = agent.cohesion_weight;
                force_x += (direction_x * scale - velocity_x) * weight;
                force_y += (direction_y * scale - velocity_y) * weight;
            }
        }

        if want_alignment {
            let mut average_x = sum_vx * inverse_count;
            let mut average_y = sum_vy * inverse_count;
            let average_sq = average_x * average_x + average_y * average_y;
            if average_sq > max_speed * max_speed {
                let scale = max_speed / average_sq.sqrt();
                average_x *= scale;
                average_y *= scale;
            }
            let weight = agent.alignment_weight;
            force_x += (average_x - velocity_x) * weight;
            force_y += (average_y - velocity_y) * weight;
        }

        if want_separation {
            let push_sq = push_x * push_x + push_y * push_y;
            if push_sq > max_speed * max_speed {
                let scale = max_speed / push_sq.sqrt();
                push_x *= scale;
                push_y *= scale;
            }
            let weight = agent.separation_weight;
            force_x += push_x * weight;
            force_y += push_y * weight;
        }

        (force_x, force_y)
    }

    /// Steer, clamp and integrate every agent, in slot order.
    ///
    /// Sequential on purpose. The sweep is Gauss-Seidel -- agent `n` reads
    /// what agents `0..n` already did this tick -- so the order is part of
    /// the behaviour rather than an implementation detail, and running it
    /// across threads would change the simulation rather than merely speed
    /// it up.
    fn sweep(&mut self, dt: f64, groups: usize, steering_group: usize, enabled: &[bool]) {
        let count = enabled.len();
        let steering_dt = dt * groups as f64;

        for slot in 0..count {
            if !enabled[slot] {
                continue;
            }

            if groups > 1 && slot % groups != steering_group {
                // Not this agent's tick to think. It still moves.
                self.live_x[slot] += self.vel_x[slot] * dt;
                self.live_y[slot] += self.vel_y[slot] * dt;
                continue;
            }

            let agent = self.params[slot];
            let (mut force_x, mut force_y) = self.flock_force(slot);

            let position_x = self.live_x[slot];
            let position_y = self.live_y[slot];
            let velocity_x = self.vel_x[slot];
            let velocity_y = self.vel_y[slot];

            if agent.seek_weight != 0.0 {
                let (seek_x, seek_y) = seek(
                    position_x,
                    position_y,
                    agent.seek_x,
                    agent.seek_y,
                    agent.max_speed,
                    velocity_x,
                    velocity_y,
                );
                force_x += seek_x * agent.seek_weight;
                force_y += seek_y * agent.seek_weight;
            }

            // `force.normalized()` would recompute the same length, so
            // reusing it is not a shortcut -- it is the same value.
            let force_length = length(force_x, force_y);
            if force_length > agent.max_force {
                (force_x, force_y) =
                    scaled_to(force_x, force_y, force_length, agent.max_force);
            }

            let inverse_mass = 1.0 / agent.mass;
            let acceleration_x = force_x * inverse_mass;
            let acceleration_y = force_y * inverse_mass;
            let mut new_vx = velocity_x + acceleration_x * steering_dt;
            let mut new_vy = velocity_y + acceleration_y * steering_dt;
            let speed = length(new_vx, new_vy);
            if speed > agent.max_speed {
                (new_vx, new_vy) = scaled_to(new_vx, new_vy, speed, agent.max_speed);
            }
            self.vel_x[slot] = new_vx;
            self.vel_y[slot] = new_vy;

            self.live_x[slot] = position_x + new_vx * dt;
            self.live_y[slot] = position_y + new_vy * dt;
        }
    }
}

/// `SteeringBehavior.seek`, which `FlockingSystem` adds after the flock
/// forces rather than folding into them.
#[inline]
fn seek(
    position_x: f64,
    position_y: f64,
    target_x: f64,
    target_y: f64,
    max_speed: f64,
    velocity_x: f64,
    velocity_y: f64,
) -> (f64, f64) {
    let direction_x = target_x - position_x;
    let direction_y = target_y - position_y;
    let len = length(direction_x, direction_y);
    if len < 0.001 {
        return (0.0, 0.0);
    }
    let (desired_x, desired_y) = scaled_to(direction_x, direction_y, len, max_speed);
    (desired_x - velocity_x, desired_y - velocity_y)
}

#[pymethods]
impl NativeFlockingSolver {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    /// Steer and integrate a whole flock, returning what changed.
    ///
    /// Args:
    ///     dt: The frame's delta time, in seconds.
    ///     cell_size: The neighbour grid's bucket size.
    ///     groups: How many ticks steering is spread across; 1 steers
    ///         everyone.
    ///     steering_group: Which group thinks this tick, `tick % groups`.
    ///     agents: `STRIDE` floats per agent -- `x, y, vx, vy` then the
    ///         eleven tuning values, in `_pack`'s order.
    ///     enabled: One flag per agent. A disabled agent is skipped
    ///         entirely, but is **still a flockmate** to the others,
    ///         because the Python hash indexes every transform regardless.
    ///
    /// Returns:
    ///     `((x, y), (vx, vy))` per agent, in slot order. A skipped
    ///     agent's row is its input unchanged, so the caller can write
    ///     back only the agents it enabled. Nested rather than four flat
    ///     floats so the caller can hand each pair straight to
    ///     `tuple.__new__`, which is the cheapest way to build the
    ///     `Vector2` the components have to hold -- and at 63% of a
    ///     native tick, the write-back is the dominant cost here, not a
    ///     detail. See `FlockingSystem._tick_natively`.
    #[pyo3(signature = (dt, cell_size, groups, steering_group, agents, enabled))]
    fn tick(
        &mut self,
        py: Python<'_>,
        dt: f64,
        cell_size: f64,
        groups: usize,
        steering_group: usize,
        agents: Vec<f64>,
        enabled: Vec<bool>,
    ) -> PyResult<Vec<((f64, f64), (f64, f64))>> {
        if agents.len() % STRIDE != 0 {
            return Err(PyValueError::new_err(format!(
                "agents has {} floats, which is not a multiple of the {STRIDE}-float \
                 stride; see FlockingSystem._pack",
                agents.len()
            )));
        }
        let count = agents.len() / STRIDE;
        if enabled.len() != count {
            return Err(PyValueError::new_err(format!(
                "got {count} agents but {} enabled flags",
                enabled.len()
            )));
        }
        // Spelled so a NaN fails it: `cell_size <= 0.0` alone would let one
        // through, and every cell index downstream would be garbage.
        if !(cell_size.is_finite() && cell_size > 0.0) {
            return Err(PyValueError::new_err(format!(
                "cell_size must be finite and positive, got {cell_size}"
            )));
        }
        if groups == 0 {
            return Err(PyValueError::new_err(
                "groups must be at least 1; FlockingSystem clamps it",
            ));
        }

        self.snap_x.clear();
        self.snap_y.clear();
        self.live_x.clear();
        self.live_y.clear();
        self.vel_x.clear();
        self.vel_y.clear();
        self.params.clear();
        for slot in 0..count {
            let row = &agents[slot * STRIDE..(slot + 1) * STRIDE];
            self.snap_x.push(row[0]);
            self.snap_y.push(row[1]);
            self.live_x.push(row[0]);
            self.live_y.push(row[1]);
            self.vel_x.push(row[2]);
            self.vel_y.push(row[3]);
            self.params.push(Params {
                max_speed: row[4],
                max_force: row[5],
                mass: row[6],
                neighbor_radius: row[7],
                separation_radius: row[8],
                cohesion_weight: row[9],
                alignment_weight: row[10],
                separation_weight: row[11],
                seek_weight: row[12],
                seek_x: row[13],
                seek_y: row[14],
            });
        }

        // Checked before the sweep rather than inside it, so the error
        // names the configuration instead of arriving as a timeout.
        let widest = self
            .params
            .iter()
            .map(|agent| agent.neighbor_radius)
            .fold(0.0f64, f64::max);
        check_query_span(widest, cell_size)?;

        self.counts.clear();
        self.counts.resize(count, 0);

        py.detach(|| {
            self.grid.build(&self.snap_x, &self.snap_y, cell_size);
            self.sweep(dt, groups, steering_group, &enabled);
        });

        Ok((0..count)
            .map(|slot| {
                (
                    (self.live_x[slot], self.live_y[slot]),
                    (self.vel_x[slot], self.vel_y[slot]),
                )
            })
            .collect())
    }

    /// How many flockmates each agent steered by on the last `tick`.
    ///
    /// For the parity suite, and the one thing about a flocking tick that
    /// *can* be compared exactly: the neighbour order is unreproducible
    /// but the neighbour set is not, so this is what separates "the same
    /// neighbourhood summed in another order" from "a different
    /// neighbourhood". A force comparison alone cannot tell those apart.
    ///
    /// A staggered agent that did not think this tick, and a disabled one,
    /// both report 0.
    fn neighbour_counts(&self) -> Vec<u32> {
        self.counts.clone()
    }
}
