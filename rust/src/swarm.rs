//! A swarm: thousands of flocking agents owned here, not by the ECS.
//!
//! ADR 0013. An agent is a slot in these arrays, named to Python by a
//! 64-bit id (generation high, slot low). Python never walks agents one at
//! a time; it spawns, kills and queries in batches.
//!
//! # Jacobi, not Gauss-Seidel
//!
//! `NativeFlockingSolver` lets agent `n` see what agents `0..n` already did
//! this tick, so its sweep order is part of the simulation. Here every
//! agent steers from the state at the start of the tick: the snapshot
//! decides both who is a flockmate and what each contributes. The result
//! does not depend on which agent is computed first, which is what lets
//! the sweep run across threads.
//!
//! # The sum order is the grid's
//!
//! Each agent sums its neighbours in the order `Grid::neighbours` finds
//! them: cell by cell, then by slot within a bucket. That order is a
//! function of the positions, the slot count and the grid's bucket hash,
//! so it is the same every run and on every platform, and
//! `tests/reference/swarm.py` reproduces it to agree bit for bit. Sorting
//! by slot instead would free the result from the hash, but costs a
//! quarter of the tick in a crowded swarm. The arithmetic is
//! `flocking.rs`'s, operation for operation, and calls no maths function
//! beyond `sqrt`, which IEEE 754 rounds exactly everywhere.

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;

use crate::grid::{check_position, check_query_span, Grid};
use crate::vector::{Pair, Point};

/// One kind's tuning, shared by every agent of that kind.
#[derive(Clone, Copy)]
struct Kind {
    max_speed: f64,
    max_force: f64,
    mass: f64,
    neighbor_radius: f64,
    separation_radius: f64,
    cohesion_weight: f64,
    alignment_weight: f64,
    separation_weight: f64,
    seek_weight: f64,
}

/// `sqrt(x * x + y * y)`, as `Vector2.length` and `flocking.rs` spell it.
#[inline]
fn length(x: f64, y: f64) -> f64 {
    (x * x + y * y).sqrt()
}

/// `(x / len) * target`, `Vector2.normalized() * target`'s order.
#[inline]
fn scaled_to(x: f64, y: f64, len: f64, target: f64) -> (f64, f64) {
    if len != 0.0 {
        ((x / len) * target, (y / len) * target)
    } else {
        (0.0, 0.0)
    }
}

const SLOT_BITS: u32 = 32;
const SLOT_MASK: u64 = (1 << SLOT_BITS) - 1;

/// A pool of flocking agents, stepped together.
#[pyclass]
pub struct NativeSwarm {
    cell_size: f64,
    kinds: Vec<Kind>,
    /// Per slot. A free slot's position is NaN, which the grid tolerates
    /// and no distance test passes, so it is never anyone's flockmate.
    x: Vec<f64>,
    y: Vec<f64>,
    vx: Vec<f64>,
    vy: Vec<f64>,
    kind: Vec<u32>,
    alive: Vec<bool>,
    /// Bumped when a slot is freed, so an id for its last occupant fails.
    generation: Vec<u32>,
    has_seek: Vec<bool>,
    seek_x: Vec<f64>,
    seek_y: Vec<f64>,
    /// Freed slots, reused last-freed first.
    free: Vec<u32>,
    live: usize,
    /// The tick's starting state, which every agent steers from.
    snap_x: Vec<f64>,
    snap_y: Vec<f64>,
    snap_vx: Vec<f64>,
    snap_vy: Vec<f64>,
    grid: Grid,
    /// Whether `grid` indexes the current positions, for queries.
    grid_current: bool,
    scratch: Vec<u32>,
    counts: Vec<u32>,
}

impl NativeSwarm {
    fn id_of(&self, slot: usize) -> u64 {
        (u64::from(self.generation[slot]) << SLOT_BITS) | slot as u64
    }

    /// The slot an id names, or a `KeyError` if it is not alive.
    fn resolve(&self, id: u64) -> PyResult<usize> {
        let slot = (id & SLOT_MASK) as usize;
        let generation = (id >> SLOT_BITS) as u32;
        if slot < self.alive.len() && self.alive[slot] && self.generation[slot] == generation {
            Ok(slot)
        } else {
            Err(PyKeyError::new_err(format!(
                "agent {id} is not alive in this swarm; it was killed, or came from \
                 another swarm"
            )))
        }
    }

    fn kind_index(&self, kind: usize) -> PyResult<usize> {
        if kind < self.kinds.len() {
            Ok(kind)
        } else {
            Err(PyValueError::new_err(format!(
                "kind {kind} is not registered; this swarm has {} kinds",
                self.kinds.len()
            )))
        }
    }

    fn ensure_grid_current(&mut self) {
        if !self.grid_current {
            self.grid.build(&self.x, &self.y, self.cell_size);
            self.grid_current = true;
        }
    }

    /// Cohesion, alignment and separation for one agent, from the snapshot.
    fn flock_force(&mut self, slot: usize) -> (f64, f64) {
        let agent = self.kinds[self.kind[slot] as usize];
        let max_speed = agent.max_speed;
        let separation_radius = agent.separation_radius;
        let separation_radius_sq = separation_radius * separation_radius;
        let want_cohesion = agent.cohesion_weight != 0.0;
        let want_alignment = agent.alignment_weight != 0.0;
        let want_separation = agent.separation_weight != 0.0;

        let x = self.snap_x[slot];
        let y = self.snap_y[slot];

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
            let neighbor_x = self.snap_x[other];
            let neighbor_y = self.snap_y[other];
            if want_cohesion {
                sum_x += neighbor_x;
                sum_y += neighbor_y;
            }
            if want_alignment {
                sum_vx += self.snap_vx[other];
                sum_vy += self.snap_vy[other];
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
                // Coincident agents push in a fixed direction rather than
                // dividing by zero.
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

        let velocity_x = self.snap_vx[slot];
        let velocity_y = self.snap_vy[slot];
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

    /// Steer and move every live agent from the snapshot.
    fn sweep(&mut self, dt: f64) {
        for slot in 0..self.alive.len() {
            if !self.alive[slot] {
                continue;
            }
            let agent = self.kinds[self.kind[slot] as usize];
            let (mut force_x, mut force_y) = self.flock_force(slot);
            let position_x = self.snap_x[slot];
            let position_y = self.snap_y[slot];
            let velocity_x = self.snap_vx[slot];
            let velocity_y = self.snap_vy[slot];

            if agent.seek_weight != 0.0 && self.has_seek[slot] {
                let direction_x = self.seek_x[slot] - position_x;
                let direction_y = self.seek_y[slot] - position_y;
                let len = length(direction_x, direction_y);
                if len >= 0.001 {
                    let (desired_x, desired_y) =
                        scaled_to(direction_x, direction_y, len, agent.max_speed);
                    force_x += (desired_x - velocity_x) * agent.seek_weight;
                    force_y += (desired_y - velocity_y) * agent.seek_weight;
                }
            }

            let force_length = length(force_x, force_y);
            if force_length > agent.max_force {
                (force_x, force_y) = scaled_to(force_x, force_y, force_length, agent.max_force);
            }
            let inverse_mass = 1.0 / agent.mass;
            let mut new_vx = velocity_x + force_x * inverse_mass * dt;
            let mut new_vy = velocity_y + force_y * inverse_mass * dt;
            let speed = length(new_vx, new_vy);
            if speed > agent.max_speed {
                (new_vx, new_vy) = scaled_to(new_vx, new_vy, speed, agent.max_speed);
            }
            self.vx[slot] = new_vx;
            self.vy[slot] = new_vy;
            self.x[slot] = position_x + new_vx * dt;
            self.y[slot] = position_y + new_vy * dt;
        }
    }
}

#[pymethods]
impl NativeSwarm {
    #[new]
    fn new(cell_size: f64) -> PyResult<Self> {
        if !(cell_size.is_finite() && cell_size > 0.0) {
            return Err(PyValueError::new_err(format!(
                "cell_size must be finite and positive, got {cell_size}"
            )));
        }
        Ok(Self {
            cell_size,
            kinds: Vec::new(),
            x: Vec::new(),
            y: Vec::new(),
            vx: Vec::new(),
            vy: Vec::new(),
            kind: Vec::new(),
            alive: Vec::new(),
            generation: Vec::new(),
            has_seek: Vec::new(),
            seek_x: Vec::new(),
            seek_y: Vec::new(),
            free: Vec::new(),
            live: 0,
            snap_x: Vec::new(),
            snap_y: Vec::new(),
            snap_vx: Vec::new(),
            snap_vy: Vec::new(),
            grid: Grid::default(),
            grid_current: false,
            scratch: Vec::new(),
            counts: Vec::new(),
        })
    }

    /// Register a kind's tuning and return its index.
    ///
    /// `tuning` is `SwarmKind`'s nine numbers in field order; the Python
    /// side validates them.
    fn add_kind(&mut self, tuning: Vec<f64>) -> PyResult<usize> {
        let [
            max_speed,
            max_force,
            mass,
            neighbor_radius,
            separation_radius,
            cohesion_weight,
            alignment_weight,
            separation_weight,
            seek_weight,
        ] = tuning[..]
        else {
            return Err(PyValueError::new_err(format!(
                "a kind takes 9 numbers, got {}",
                tuning.len()
            )));
        };
        check_query_span(neighbor_radius, self.cell_size)?;
        self.kinds.push(Kind {
            max_speed,
            max_force,
            mass,
            neighbor_radius,
            separation_radius,
            cohesion_weight,
            alignment_weight,
            separation_weight,
            seek_weight,
        });
        Ok(self.kinds.len() - 1)
    }

    /// Add agents of one kind, at rest unless velocities are given.
    ///
    /// Returns their ids, in the order of `positions`.
    #[pyo3(signature = (kind, positions, velocities = None))]
    fn spawn(
        &mut self,
        kind: usize,
        positions: Vec<Pair>,
        velocities: Option<Vec<Pair>>,
    ) -> PyResult<Vec<u64>> {
        let kind = self.kind_index(kind)?;
        if let Some(given) = &velocities {
            if given.len() != positions.len() {
                return Err(PyValueError::new_err(format!(
                    "got {} positions but {} velocities",
                    positions.len(),
                    given.len()
                )));
            }
        }
        for (index, point) in positions.iter().enumerate() {
            check_position(point.0, point.1, self.cell_size)?;
            if let Some(given) = &velocities {
                let velocity = given[index];
                if !(velocity.0.is_finite() && velocity.1.is_finite()) {
                    return Err(PyValueError::new_err(format!(
                        "velocity {index} is not finite: ({}, {})",
                        velocity.0, velocity.1
                    )));
                }
            }
        }

        let mut ids = Vec::with_capacity(positions.len());
        for (index, point) in positions.iter().enumerate() {
            let (velocity_x, velocity_y) = velocities
                .as_ref()
                .map_or((0.0, 0.0), |given| (given[index].0, given[index].1));
            let slot = if let Some(slot) = self.free.pop() {
                slot as usize
            } else {
                self.x.push(0.0);
                self.y.push(0.0);
                self.vx.push(0.0);
                self.vy.push(0.0);
                self.kind.push(0);
                self.alive.push(false);
                self.generation.push(0);
                self.has_seek.push(false);
                self.seek_x.push(0.0);
                self.seek_y.push(0.0);
                self.alive.len() - 1
            };
            if slot > SLOT_MASK as usize {
                return Err(PyValueError::new_err("a swarm holds at most 2**32 slots"));
            }
            self.x[slot] = point.0;
            self.y[slot] = point.1;
            self.vx[slot] = velocity_x;
            self.vy[slot] = velocity_y;
            self.kind[slot] = kind as u32;
            self.alive[slot] = true;
            self.has_seek[slot] = false;
            self.live += 1;
            ids.push(self.id_of(slot));
        }
        self.grid_current = false;
        Ok(ids)
    }

    /// Remove agents. Every id must be alive and appear once, or nothing
    /// is removed.
    fn kill(&mut self, ids: Vec<u64>) -> PyResult<()> {
        let mut slots = Vec::with_capacity(ids.len());
        for &id in &ids {
            slots.push(self.resolve(id)?);
        }
        let mut sorted = slots.clone();
        sorted.sort_unstable();
        if sorted.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err(PyValueError::new_err("an agent is listed twice in one kill"));
        }
        for slot in slots {
            self.alive[slot] = false;
            self.generation[slot] = self.generation[slot].wrapping_add(1);
            self.x[slot] = f64::NAN;
            self.y[slot] = f64::NAN;
            self.free.push(slot as u32);
            self.live -= 1;
        }
        self.grid_current = false;
        Ok(())
    }

    /// Whether an id names a live agent.
    fn is_alive(&self, id: u64) -> bool {
        self.resolve(id).is_ok()
    }

    /// How many agents are alive.
    fn count(&self) -> usize {
        self.live
    }

    /// Every live agent's id, in slot order.
    fn ids(&self) -> Vec<u64> {
        (0..self.alive.len())
            .filter(|&slot| self.alive[slot])
            .map(|slot| self.id_of(slot))
            .collect()
    }

    /// Positions of the given agents.
    fn positions(&self, ids: Vec<u64>) -> PyResult<Vec<Point>> {
        ids.iter()
            .map(|&id| self.resolve(id).map(|slot| Point::of(self.x[slot], self.y[slot])))
            .collect()
    }

    /// Velocities of the given agents.
    fn velocities(&self, ids: Vec<u64>) -> PyResult<Vec<Point>> {
        ids.iter()
            .map(|&id| self.resolve(id).map(|slot| Point::of(self.vx[slot], self.vy[slot])))
            .collect()
    }

    /// The kind index of each given agent.
    fn kinds_of(&self, ids: Vec<u64>) -> PyResult<Vec<usize>> {
        ids.iter()
            .map(|&id| self.resolve(id).map(|slot| self.kind[slot] as usize))
            .collect()
    }

    /// Point every live agent of a kind at a target, or at none.
    fn set_kind_seek(&mut self, kind: usize, target: Option<Pair>) -> PyResult<()> {
        let kind = self.kind_index(kind)? as u32;
        if let Some(point) = target {
            check_position(point.0, point.1, self.cell_size)?;
        }
        for slot in 0..self.alive.len() {
            if self.alive[slot] && self.kind[slot] == kind {
                self.set_seek_slot(slot, target);
            }
        }
        Ok(())
    }

    /// Point each given agent at its own target.
    fn set_seek(&mut self, ids: Vec<u64>, targets: Vec<Pair>) -> PyResult<()> {
        if ids.len() != targets.len() {
            return Err(PyValueError::new_err(format!(
                "got {} ids but {} targets",
                ids.len(),
                targets.len()
            )));
        }
        let mut slots = Vec::with_capacity(ids.len());
        for (&id, point) in ids.iter().zip(&targets) {
            check_position(point.0, point.1, self.cell_size)?;
            slots.push(self.resolve(id)?);
        }
        for (slot, point) in slots.into_iter().zip(targets) {
            self.set_seek_slot(slot, Some(point));
        }
        Ok(())
    }

    /// Ids of the live agents within `radius` of a point, sorted.
    fn query_radius(&mut self, centre: Pair, radius: f64) -> PyResult<Vec<u64>> {
        check_position(centre.0, centre.1, self.cell_size)?;
        if !(radius.is_finite() && radius >= 0.0) {
            return Err(PyValueError::new_err(format!(
                "radius must be finite and not negative, got {radius}"
            )));
        }
        check_query_span(radius, self.cell_size)?;
        self.ensure_grid_current();
        self.grid
            .neighbours(centre.0, centre.1, radius, &self.x, &self.y, &mut self.scratch);
        let mut ids: Vec<u64> = self.scratch.iter().map(|&slot| self.id_of(slot as usize)).collect();
        ids.sort_unstable();
        Ok(ids)
    }

    /// Ids of the live agents farther than `radius` from a point, sorted.
    fn query_outside(&self, centre: Pair, radius: f64) -> PyResult<Vec<u64>> {
        check_position(centre.0, centre.1, self.cell_size)?;
        if !(radius.is_finite() && radius >= 0.0) {
            return Err(PyValueError::new_err(format!(
                "radius must be finite and not negative, got {radius}"
            )));
        }
        let radius_sq = radius * radius;
        let mut ids: Vec<u64> = (0..self.alive.len())
            .filter(|&slot| {
                let offset_x = self.x[slot] - centre.0;
                let offset_y = self.y[slot] - centre.1;
                self.alive[slot] && offset_x * offset_x + offset_y * offset_y > radius_sq
            })
            .map(|slot| self.id_of(slot))
            .collect();
        ids.sort_unstable();
        Ok(ids)
    }

    /// Steer and move every agent by one step of `dt` seconds.
    fn tick(&mut self, py: Python<'_>, dt: f64) -> PyResult<()> {
        if !(dt.is_finite() && dt >= 0.0) {
            return Err(PyValueError::new_err(format!(
                "dt must be finite and not negative, got {dt}"
            )));
        }
        self.snap_x.clone_from(&self.x);
        self.snap_y.clone_from(&self.y);
        self.snap_vx.clone_from(&self.vx);
        self.snap_vy.clone_from(&self.vy);
        self.counts.clear();
        self.counts.resize(self.alive.len(), 0);
        py.detach(|| {
            self.grid.build(&self.snap_x, &self.snap_y, self.cell_size);
            self.sweep(dt);
        });
        self.grid_current = false;
        Ok(())
    }

    /// How many flockmates each live agent steered by on the last tick,
    /// in `ids()` order.
    fn neighbour_counts(&self) -> Vec<u32> {
        (0..self.alive.len())
            .filter(|&slot| self.alive[slot])
            .map(|slot| self.counts.get(slot).copied().unwrap_or(0))
            .collect()
    }
}

impl NativeSwarm {
    fn set_seek_slot(&mut self, slot: usize, target: Option<Pair>) {
        match target {
            Some(point) => {
                self.has_seek[slot] = true;
                self.seek_x[slot] = point.0;
                self.seek_y[slot] = point.1;
            }
            None => self.has_seek[slot] = false,
        }
    }
}
