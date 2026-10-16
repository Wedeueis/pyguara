//! Native structure-of-arrays pools, for RFC-0003's Marco 3.
//!
//! Marco 3 proposes replacing `ParticleSystem`, `Sparks` and
//! `ProjectileSystem` -- three self-contained pools that are not ECS
//! entities -- with native equivalents. They are the engine's best
//! candidates for it: a fixed capacity, flat numeric state, and no Python
//! object a game holds a reference to.
//!
//! The extension is **optional**. The pure-Python pools are kept and used
//! whenever it is absent, so the engine installs and runs with no Rust
//! toolchain; `pyguara/graphics/components/_native.py` is the seam, and the
//! price -- two implementations that must agree -- is paid by the parity
//! tests beside it.
//!
//! Measured against the Python pools it replaces: a 1000-particle frame
//! goes 2.574 ms -> 0.126 ms (20.5x), 4000 goes 7.843 -> 0.537 (14.6x). See
//! `docs/adr/0003-native-core-spike.md` and `docs/guides/performance.md`.
//!
//! Two things deliberately stay in Python throughout, and they shape every
//! pool's API: the seeded RNG draws an emission takes (a replay restores
//! that seed, so drawing in Rust would stop a recording reproducing), and
//! any Python object a slot refers to, such as a texture.

use pyo3::prelude::*;

mod particles;
mod sparks;

/// An RGBA tint as the renderer wants it.
pub type Rgba = (u8, u8, u8, u8);

/// Register the module's classes.
#[pymodule]
fn pyguara_core_rs(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<particles::NativeParticlePool>()?;
    module.add_class::<sparks::NativeSparkPool>()?;
    Ok(())
}
