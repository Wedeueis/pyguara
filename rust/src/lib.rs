//! Spike: a structure-of-arrays particle pool, for RFC-0003's Marco 3.
//!
//! Marco 3 proposes replacing `ParticleSystem`, `Sparks` and
//! `ProjectileSystem` with native SoA pools. This implements one of them --
//! particles -- because one real number decides the milestone, and three
//! would not decide it any harder.
//!
//! The Python baseline it is measured against is
//! `ParticleSystem.update()`: 2.196 ms for 1000 live particles and 9.020 ms
//! for 4000, with 44-45% of that spent constructing `Vector2` objects. See
//! `docs/adr/0003-native-core-spike.md`.
//!
//! Deliberately not a full port: no textures, no colour interpolation, no
//! render packing. It does exactly the arithmetic the Python `update` loop
//! does, so the comparison is like for like and the number means something.

use pyo3::prelude::*;

mod pools;

/// Register the module's classes.
#[pymodule]
fn pyguara_core_rs(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<pools::NativeParticlePool>()?;
    Ok(())
}
