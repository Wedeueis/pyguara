//! A spark pool in structure-of-arrays layout.
//!
//! The shape-drawn sibling of `particles::NativeParticlePool`. `Sparks`
//! draws coloured primitives rather than textured quads, and that changes
//! where its frame goes: measured, a 1000-spark frame is 45% `update` and
//! 55% `render` for dots, 29/71 for streaks, because every spark costs one
//! `draw_circle` or `draw_line` call where a particle costs a share of one
//! batch. Porting only the arithmetic would therefore cap at 1.4-1.8x.
//!
//! So this pool packs the render too, and `pack_rows` is the half that
//! matters. Two things stay in Python, exactly as they do for particles:
//! the three seeded RNG draws per spark (handed over as whole arrays, one
//! crossing per burst), and the decision of what to do with the packed
//! rows.

use pyo3::prelude::*;

use crate::Rgba;

/// One packed primitive: centre, half-extents, rotation, colour, stroke.
///
/// The canonical layout `pyguara.graphics.types.SHAPE_INSTANCE_FLOATS`
/// documents, which is also what the ModernGL shape shader reads per
/// instance. Mirrored here rather than invented: the whole point of
/// packing natively is that the rows need no further work in Python.
pub type ShapeRow = [f32; 11];

const KIND_CIRCLE: f32 = 1.0;
const KIND_LINE: f32 = 2.0;

/// How far back along its velocity a streak's tail sits, in seconds.
const STREAK_SECONDS: f32 = 0.03;

/// A fixed-capacity spark pool, one column per field.
#[pyclass]
pub struct NativeSparkPool {
    capacity: usize,
    next: usize,
    pos_x: Vec<f32>,
    pos_y: Vec<f32>,
    vel_x: Vec<f32>,
    vel_y: Vec<f32>,
    life: Vec<f32>,
    life_total: Vec<f32>,
    radius: Vec<f32>,
    color: Vec<Rgba>,
    gravity: Vec<f32>,
    drag: Vec<f32>,
    streak: Vec<bool>,
    active: Vec<bool>,
}

impl NativeSparkPool {
    /// The fraction of life a slot has left, as `Sparks.render` computes it.
    fn remaining(&self, i: usize) -> f32 {
        if self.life_total[i] > 0.0 {
            self.life[i] / self.life_total[i]
        } else {
            0.0
        }
    }

    /// The slot's current tint: its colour with alpha faded by `remaining`.
    ///
    /// Truncates rather than rounds, because `Sparks.render` does --
    /// `int(spark.color.a * remaining)`.
    fn faded(&self, i: usize, remaining: f32) -> (f32, f32, f32, f32) {
        let (r, g, b, a) = self.color[i];
        let alpha = (f32::from(a) * remaining) as u8;
        (
            f32::from(r) / 255.0,
            f32::from(g) / 255.0,
            f32::from(b) / 255.0,
            f32::from(alpha) / 255.0,
        )
    }

    /// The row a dot spark draws: a filled circle shrinking as it fades.
    fn circle_row(&self, i: usize, offset_x: f32, offset_y: f32) -> ShapeRow {
        let remaining = self.remaining(i);
        let (r, g, b, a) = self.faded(i, remaining);
        let extent = self.radius[i] * remaining;
        [
            self.pos_x[i] + offset_x,
            self.pos_y[i] + offset_y,
            extent,
            extent,
            0.0,
            r,
            g,
            b,
            a,
            0.0,
            KIND_CIRCLE,
        ]
    }

    /// The row a streak spark draws: a capsule back along its velocity.
    ///
    /// Reproduces what `Sparks.render` asks for and what the ModernGL
    /// `draw_line` then derives -- a tail at `position - velocity * 0.03`,
    /// a thickness of `max(1, int(radius))`, and the capsule's centre,
    /// half-length and angle computed from the two endpoints.
    fn line_row(&self, i: usize, offset_x: f32, offset_y: f32) -> ShapeRow {
        let remaining = self.remaining(i);
        let (r, g, b, a) = self.faded(i, remaining);

        let end_x = self.pos_x[i] + offset_x;
        let end_y = self.pos_y[i] + offset_y;
        let run_x = self.vel_x[i] * STREAK_SECONDS;
        let run_y = self.vel_y[i] * STREAK_SECONDS;
        let start_x = end_x - run_x;
        let start_y = end_y - run_y;

        let width = (self.radius[i] as i32).max(1);
        let half_width = width as f32 / 2.0;
        let half_length = run_x.hypot(run_y) / 2.0;

        [
            (start_x + end_x) / 2.0,
            (start_y + end_y) / 2.0,
            half_length + half_width,
            half_width,
            run_y.atan2(run_x),
            r,
            g,
            b,
            a,
            0.0,
            KIND_LINE,
        ]
    }
}

#[pymethods]
impl NativeSparkPool {
    /// Pre-allocate every column to `capacity`.
    #[new]
    fn new(capacity: usize) -> Self {
        Self {
            capacity,
            next: 0,
            pos_x: vec![0.0; capacity],
            pos_y: vec![0.0; capacity],
            vel_x: vec![0.0; capacity],
            vel_y: vec![0.0; capacity],
            life: vec![0.0; capacity],
            life_total: vec![1.0; capacity],
            radius: vec![2.0; capacity],
            color: vec![(255, 255, 255, 255); capacity],
            gravity: vec![0.0; capacity],
            drag: vec![1.0; capacity],
            streak: vec![false; capacity],
            active: vec![false; capacity],
        }
    }

    /// How many slots the pool holds.
    #[getter]
    fn capacity(&self) -> usize {
        self.capacity
    }

    /// Spawn sparks into free slots, one crossing for the whole burst.
    ///
    /// `vel_x`, `vel_y` and `life` are per spark and come from the caller's
    /// seeded stream; the shortest of them sets how many to spawn. Free
    /// slots are searched for rather than overwritten, and the burst stops
    /// when the pool is full -- `Sparks.burst`'s own contract.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (x, y, vel_x, vel_y, life, radius, color, gravity, drag, streak))]
    fn burst(
        &mut self,
        x: f32,
        y: f32,
        vel_x: Vec<f32>,
        vel_y: Vec<f32>,
        life: Vec<f32>,
        radius: f32,
        color: Rgba,
        gravity: f32,
        drag: f32,
        streak: bool,
    ) -> usize {
        let wanted = vel_x.len().min(vel_y.len()).min(life.len());

        let mut spawned = 0usize;
        let search_start = self.next;
        while spawned < wanted {
            let i = self.next;
            if !self.active[i] {
                self.pos_x[i] = x;
                self.pos_y[i] = y;
                self.vel_x[i] = vel_x[spawned];
                self.vel_y[i] = vel_y[spawned];
                self.life[i] = life[spawned];
                self.life_total[i] = life[spawned];
                self.radius[i] = radius;
                self.color[i] = color;
                self.gravity[i] = gravity;
                self.drag[i] = drag;
                self.streak[i] = streak;
                self.active[i] = true;
                spawned += 1;
            }
            self.next = (self.next + 1) % self.capacity;
            if self.next == search_start {
                break; // wrapped: the pool is full
            }
        }
        spawned
    }

    /// Advance every live spark by `dt`.
    ///
    /// The same arithmetic in the same order as the Python loop: expire,
    /// drag the horizontal, drag the vertical and add gravity, integrate.
    /// Note that drag is applied per frame rather than per second, which is
    /// framerate-dependent and faithfully reproduced -- parity with the
    /// Python pool is worth more than a correction that changes how every
    /// existing burst looks.
    fn update(&mut self, py: Python<'_>, dt: f32) {
        py.detach(|| {
            for i in 0..self.capacity {
                if !self.active[i] {
                    continue;
                }
                self.life[i] -= dt;
                if self.life[i] <= 0.0 {
                    self.active[i] = false;
                    continue;
                }
                self.vel_x[i] *= self.drag[i];
                self.vel_y[i] = self.vel_y[i] * self.drag[i] + self.gravity[i] * dt;
                self.pos_x[i] += self.vel_x[i] * dt;
                self.pos_y[i] += self.vel_y[i] * dt;
            }
        });
    }

    /// Pack every live spark into ready-to-upload instance rows.
    ///
    /// Returns `(circles, lines)` -- dots and streaks separately, because
    /// they are different primitives and batch independently.
    ///
    /// This is the candidate that lets the caller hand the rows straight to
    /// a renderer's instance bucket, doing no per-spark work in Python.
    fn pack_rows(
        &self,
        py: Python<'_>,
        offset_x: f32,
        offset_y: f32,
    ) -> (Vec<ShapeRow>, Vec<ShapeRow>) {
        py.detach(|| {
            let mut circles: Vec<ShapeRow> = Vec::new();
            let mut lines: Vec<ShapeRow> = Vec::new();
            for i in 0..self.capacity {
                if !self.active[i] {
                    continue;
                }
                if self.streak[i] {
                    lines.push(self.line_row(i, offset_x, offset_y));
                } else {
                    circles.push(self.circle_row(i, offset_x, offset_y));
                }
            }
            (circles, lines)
        })
    }

    /// Pack every live spark as the arguments its draw call would take.
    ///
    /// The semantic candidate: `(centre, radius, rgba)` per dot and
    /// `(start, end, width, rgba)` per streak, leaving the instance layout
    /// to the renderer. Measured against `pack_rows` to decide which shape
    /// the batch handoff should take; see `tools/bench_native_sparks.py`.
    #[allow(clippy::type_complexity)]
    fn pack_draw_calls(
        &self,
        py: Python<'_>,
        offset_x: f32,
        offset_y: f32,
    ) -> (
        Vec<(f32, f32, f32, Rgba)>,
        Vec<(f32, f32, f32, f32, i32, Rgba)>,
    ) {
        py.detach(|| {
            let mut dots: Vec<(f32, f32, f32, Rgba)> = Vec::new();
            let mut streaks: Vec<(f32, f32, f32, f32, i32, Rgba)> = Vec::new();
            for i in 0..self.capacity {
                if !self.active[i] {
                    continue;
                }
                let remaining = self.remaining(i);
                let (r, g, b, a) = self.color[i];
                let rgba = (r, g, b, (f32::from(a) * remaining) as u8);
                let end_x = self.pos_x[i] + offset_x;
                let end_y = self.pos_y[i] + offset_y;
                if self.streak[i] {
                    streaks.push((
                        end_x - self.vel_x[i] * STREAK_SECONDS,
                        end_y - self.vel_y[i] * STREAK_SECONDS,
                        end_x,
                        end_y,
                        (self.radius[i] as i32).max(1),
                        rgba,
                    ));
                } else {
                    dots.push((end_x, end_y, self.radius[i] * remaining, rgba));
                }
            }
            (dots, streaks)
        })
    }

    /// How many slots are live.
    fn live_count(&self) -> usize {
        self.active.iter().filter(|slot| **slot).count()
    }

    /// One slot's state, for parity tests against the Python pool.
    fn slot(&self, index: usize) -> (f32, f32, f32, f32, f32, bool, bool) {
        (
            self.pos_x[index],
            self.pos_y[index],
            self.vel_x[index],
            self.vel_y[index],
            self.life[index],
            self.streak[index],
            self.active[index],
        )
    }

    /// Deactivate every slot.
    fn clear(&mut self) {
        self.active.iter_mut().for_each(|slot| *slot = false);
        self.next = 0;
    }
}
