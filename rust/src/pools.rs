//! A particle pool in structure-of-arrays layout.
//!
//! The Python pool holds a `Vec` of dataclass instances, each owning two
//! `Vector2` objects it replaces every tick -- that replacement is where
//! 44% of its update cost goes. Here each field is its own contiguous
//! `Vec`, so a tick is a handful of tight loops over flat memory and
//! nothing is allocated at all.
//!
//! Two things deliberately stay in Python, and they shape this API:
//!
//! **Randomness.** `ParticleSystem.emit` takes three draws per particle
//! from the engine's seeded `RandomStream` (angle, speed, initial
//! rotation). Moving those into Rust would put them outside the seed a
//! replay restores, so the caller computes them and hands over whole
//! arrays -- one FFI crossing per burst, not per particle.
//!
//! **Textures.** A `Texture` is a Python object with no place in a float
//! column, so slots carry a `u32` index into a list the caller keeps.

use pyo3::prelude::*;

/// An RGBA tint as the renderer wants it.
type Rgba = (u8, u8, u8, u8);

/// One texture's packed draw data: id, screen positions, tints, any tinted.
type TextureBatch = (u32, Vec<(f32, f32)>, Vec<Rgba>, bool);

const WHITE: Rgba = (255, 255, 255, 255);

/// A fixed-capacity particle pool, one column per field.
#[pyclass]
pub struct NativeParticlePool {
    capacity: usize,
    next: usize,
    pos_x: Vec<f32>,
    pos_y: Vec<f32>,
    vel_x: Vec<f32>,
    vel_y: Vec<f32>,
    acc_x: Vec<f32>,
    acc_y: Vec<f32>,
    damping: Vec<f32>,
    life: Vec<f32>,
    life_total: Vec<f32>,
    rotation: Vec<f32>,
    angular_velocity: Vec<f32>,
    scale_x: Vec<f32>,
    scale_y: Vec<f32>,
    scale_vel_x: Vec<f32>,
    scale_vel_y: Vec<f32>,
    texture_id: Vec<u32>,
    color_start: Vec<Rgba>,
    color_end: Vec<Rgba>,
    has_color: Vec<bool>,
    active: Vec<bool>,
}

impl NativeParticlePool {
    /// The tint a slot shows now, lerped start -> end over its life.
    ///
    /// Mirrors `_particle_color`: opaque white when the slot has no colour
    /// animation, so a particle emitted without one renders untinted.
    fn tint(&self, i: usize) -> Rgba {
        if !self.has_color[i] {
            return WHITE;
        }
        let t = if self.life_total[i] <= 0.0 {
            0.0
        } else {
            (1.0 - self.life[i] / self.life_total[i]).clamp(0.0, 1.0)
        };
        let (sr, sg, sb, sa) = self.color_start[i];
        let (er, eg, eb, ea) = self.color_end[i];
        let lerp = |a: u8, b: u8| -> u8 {
            (f32::from(a) + (f32::from(b) - f32::from(a)) * t).round() as u8
        };
        (lerp(sr, er), lerp(sg, eg), lerp(sb, eb), lerp(sa, ea))
    }
}

#[pymethods]
impl NativeParticlePool {
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
            acc_x: vec![0.0; capacity],
            acc_y: vec![0.0; capacity],
            damping: vec![1.0; capacity],
            life: vec![0.0; capacity],
            life_total: vec![1.0; capacity],
            rotation: vec![0.0; capacity],
            angular_velocity: vec![0.0; capacity],
            scale_x: vec![1.0; capacity],
            scale_y: vec![1.0; capacity],
            scale_vel_x: vec![0.0; capacity],
            scale_vel_y: vec![0.0; capacity],
            texture_id: vec![0; capacity],
            color_start: vec![WHITE; capacity],
            color_end: vec![WHITE; capacity],
            has_color: vec![false; capacity],
            active: vec![false; capacity],
        }
    }

    /// How many slots the pool holds.
    #[getter]
    fn capacity(&self) -> usize {
        self.capacity
    }

    /// Spawn particles into free slots, one crossing for the whole burst.
    ///
    /// `vel_x`, `vel_y` and `rotation` are per particle and come from the
    /// caller's seeded RNG; the shortest of them sets how many to spawn.
    /// Everything else is shared across the burst, matching
    /// `ParticleSystem.emit`'s own signature.
    ///
    /// Free slots are *searched for*, not overwritten, and the burst stops
    /// when the pool is full -- the same contract as the Python pool, which
    /// drops the remainder rather than evicting a live particle.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        texture_id, x, y, vel_x, vel_y, rotation, life,
        acc_x=0.0, acc_y=0.0, damping=1.0, angular_velocity=0.0,
        scale_x=1.0, scale_y=1.0, scale_vel_x=0.0, scale_vel_y=0.0,
        color_start=None, color_end=None,
    ))]
    fn emit(
        &mut self,
        texture_id: u32,
        x: f32,
        y: f32,
        vel_x: Vec<f32>,
        vel_y: Vec<f32>,
        rotation: Vec<f32>,
        life: f32,
        acc_x: f32,
        acc_y: f32,
        damping: f32,
        angular_velocity: f32,
        scale_x: f32,
        scale_y: f32,
        scale_vel_x: f32,
        scale_vel_y: f32,
        color_start: Option<Rgba>,
        color_end: Option<Rgba>,
    ) -> usize {
        let wanted = vel_x.len().min(vel_y.len()).min(rotation.len());
        let has_color = color_start.is_some() && color_end.is_some();
        let start_color = color_start.unwrap_or(WHITE);
        let end_color = color_end.unwrap_or(WHITE);

        let mut spawned = 0usize;
        let search_start = self.next;
        while spawned < wanted {
            let i = self.next;
            if !self.active[i] {
                self.pos_x[i] = x;
                self.pos_y[i] = y;
                self.vel_x[i] = vel_x[spawned];
                self.vel_y[i] = vel_y[spawned];
                self.rotation[i] = rotation[spawned];
                self.life[i] = life;
                self.life_total[i] = life;
                self.acc_x[i] = acc_x;
                self.acc_y[i] = acc_y;
                self.damping[i] = damping;
                self.angular_velocity[i] = angular_velocity;
                self.scale_x[i] = scale_x;
                self.scale_y[i] = scale_y;
                self.scale_vel_x[i] = scale_vel_x;
                self.scale_vel_y[i] = scale_vel_y;
                self.texture_id[i] = texture_id;
                self.color_start[i] = start_color;
                self.color_end[i] = end_color;
                self.has_color[i] = has_color;
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

    /// Advance every live particle by `dt`.
    ///
    /// The same arithmetic as the Python loop, in the same order: expire,
    /// accelerate, damp, integrate, rotate, scale. The GIL is released --
    /// nothing in here touches a Python object, which is the point.
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
                self.vel_x[i] = (self.vel_x[i] + self.acc_x[i] * dt) * self.damping[i];
                self.vel_y[i] = (self.vel_y[i] + self.acc_y[i] * dt) * self.damping[i];
                self.pos_x[i] += self.vel_x[i] * dt;
                self.pos_y[i] += self.vel_y[i] * dt;
                self.rotation[i] += self.angular_velocity[i] * dt;
                self.scale_x[i] += self.scale_vel_x[i] * dt;
                self.scale_y[i] += self.scale_vel_y[i] * dt;
            }
        });
    }

    /// Group live particles by texture, transformed to screen space.
    ///
    /// Does what `ParticleSystem.render`'s loop did -- world-to-screen, the
    /// colour lerp and the per-texture grouping -- and hands back one entry
    /// per texture rather than per particle.
    ///
    /// The lists come back as Python lists because `RenderBatch` wants
    /// `list[tuple[float, float]]`. Handing over a buffer instead needs the
    /// renderer to accept one, which is RFC-0003's Marco 2, not this.
    fn pack_for_render(
        &self,
        py: Python<'_>,
        zoom: f32,
        offset_x: f32,
        offset_y: f32,
    ) -> Vec<TextureBatch> {
        py.detach(|| {
            let mut order: Vec<u32> = Vec::new();
            let mut batches: Vec<TextureBatch> = Vec::new();

            for i in 0..self.capacity {
                if !self.active[i] {
                    continue;
                }
                let id = self.texture_id[i];
                let slot = match order.iter().position(|candidate| *candidate == id) {
                    Some(found) => found,
                    None => {
                        order.push(id);
                        batches.push((id, Vec::new(), Vec::new(), false));
                        order.len() - 1
                    }
                };
                let tint = self.tint(i);
                let entry = &mut batches[slot];
                entry.1.push((
                    self.pos_x[i] * zoom + offset_x,
                    self.pos_y[i] * zoom + offset_y,
                ));
                entry.2.push(tint);
                if tint != WHITE {
                    entry.3 = true;
                }
            }
            batches
        })
    }

    /// How many slots are live.
    fn live_count(&self) -> usize {
        self.active.iter().filter(|slot| **slot).count()
    }

    /// One slot's state, for parity tests against the Python pool.
    fn slot(&self, index: usize) -> (f32, f32, f32, f32, f32, f32, bool) {
        (
            self.pos_x[index],
            self.pos_y[index],
            self.vel_x[index],
            self.vel_y[index],
            self.life[index],
            self.rotation[index],
            self.active[index],
        )
    }

    /// Deactivate every slot.
    fn clear(&mut self) {
        self.active.iter_mut().for_each(|slot| *slot = false);
        self.next = 0;
    }
}
