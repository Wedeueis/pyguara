//! A particle pool in structure-of-arrays layout.
//!
//! The Python pool holds a `Vec` of dataclass instances, each owning two
//! `Vector2` objects it replaces every tick -- that replacement is where
//! 44% of its update cost goes. Here each field is its own contiguous
//! `Vec<f32>`, so a tick is a handful of tight loops over flat memory and
//! nothing is allocated at all.

use pyo3::prelude::*;

/// A fixed-capacity particle pool, one `Vec` per field.
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
    active: Vec<bool>,
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
            active: vec![false; capacity],
        }
    }

    /// Spawn `count` particles, filling slots from the ring cursor.
    ///
    /// One crossing for the whole burst, per the RFC's coarse-grained FFI
    /// rule -- not one per particle.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (count, x, y, vx, vy, life, damping=1.0, angular_velocity=0.0))]
    fn emit(
        &mut self,
        count: usize,
        x: f32,
        y: f32,
        vx: f32,
        vy: f32,
        life: f32,
        damping: f32,
        angular_velocity: f32,
    ) {
        for _ in 0..count {
            let i = self.next;
            self.next = (self.next + 1) % self.capacity;
            self.pos_x[i] = x;
            self.pos_y[i] = y;
            self.vel_x[i] = vx;
            self.vel_y[i] = vy;
            self.acc_x[i] = 0.0;
            self.acc_y[i] = 0.0;
            self.damping[i] = damping;
            self.life[i] = life;
            self.life_total[i] = life;
            self.rotation[i] = 0.0;
            self.angular_velocity[i] = angular_velocity;
            self.scale_x[i] = 1.0;
            self.scale_y[i] = 1.0;
            self.scale_vel_x[i] = 0.0;
            self.scale_vel_y[i] = 0.0;
            self.active[i] = true;
        }
    }

    /// Advance every live particle by `dt`.
    ///
    /// The same arithmetic as the Python loop, in the same order: expire,
    /// accelerate, damp, integrate, rotate, scale. The GIL is released --
    /// nothing here touches a Python object, which is the whole point.
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

    /// How many slots are live, for parity checks against the Python pool.
    fn live_count(&self) -> usize {
        self.active.iter().filter(|a| **a).count()
    }

    /// One live particle's position, so a test can assert the maths agrees.
    fn position_at(&self, index: usize) -> (f32, f32) {
        (self.pos_x[index], self.pos_y[index])
    }
}
