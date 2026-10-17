//! The engine's optional native half.
//!
//! Two kinds of thing live here, and the difference is the whole of
//! `docs/adr/0004-the-native-boundary.md`:
//!
//! **Structure-of-arrays pools** -- `particles` and `sparks`. Fixed
//! capacity, flat numeric state, no Python object a game holds a reference
//! to. A 1000-particle frame goes 2.574 ms -> 0.126 ms (20.5x), 4000 goes
//! 7.843 -> 0.537 (14.6x). Cosmetic, so a last-bit float difference
//! between the two stores is a tolerance in a test rather than a bug.
//!
//! **A grid flow field** -- `flowfield`. Not cosmetic: it steers gameplay,
//! so it is bit-exact with the Python implementation rather than close to
//! it, and `tests/test_native_flow_field_parity.py` asserts that on every
//! cell. 85 ms -> 1.3 ms at 96x96, which turns five dropped frames per
//! recompute into a tenth of one.
//!
//! The extension is **optional** throughout. The pure-Python
//! implementations are kept and used whenever it is absent, so the engine
//! installs and runs with no Rust toolchain; `pyguara/native.py` is the
//! seam and `PerformanceConfig.native_acceleration` is the switch. The
//! price -- two implementations that must agree -- is paid by the parity
//! tests beside each one.
//!
//! Two things deliberately stay in Python throughout, and they shape every
//! API here: the seeded RNG draws an emission takes (a replay restores
//! that seed, so drawing in Rust would stop a recording reproducing), and
//! any Python object a slot refers to, such as a texture.

use pyo3::prelude::*;

mod flowfield;
mod particles;
mod sparks;

/// An RGBA tint as the renderer wants it.
pub type Rgba = (u8, u8, u8, u8);

/// Register the module's classes.
#[pymodule]
fn pyguara_core_rs(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<flowfield::NativeFlowField>()?;
    module.add_class::<particles::NativeParticlePool>()?;
    module.add_class::<sparks::NativeSparkPool>()?;
    Ok(())
}
