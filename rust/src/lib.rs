//! The engine's optional native half.
//!
//! Four kinds of thing live here, and the differences between them are the
//! whole of `docs/adr/0004-the-native-boundary.md`:
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
//! **A whole-flock solver** -- `flocking`. The first port of something
//! that is *not* opaque: every agent is an ECS entity, so the entire flock
//! crosses the boundary every tick and the crossing is 63% of the native
//! tick rather than a rounding error. 16.6 ms -> 1.9 ms at 1000 agents,
//! and the first store where bit-exactness was **unavailable** -- Python
//! sums forces in `set` iteration order, so there is no single Python
//! answer to be exact to. Its parity suite has one permitted cause and
//! pins everything else with `==`.
//!
//! **A shared spatial index** -- `grid` and `spatialhash`. `grid` is the
//! uniform grid both the flocking solver and the index use; `spatialhash`
//! is the one class here that hands Python objects back, which ADR 0004
//! had ruled out and Decision 7 corrects with the measurement. 17x on the
//! index, 1.3-4.3x for the consumers that sit on top of it, and the only
//! store that is *worse* than Python at anything: an alternating
//! insert/query loop rebuilds the grid per query, 0.13x over 4000 keys.
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

mod flocking;
mod flowfield;
mod grid;
mod particles;
mod sparks;

/// An RGBA tint as the renderer wants it.
pub type Rgba = (u8, u8, u8, u8);

/// Register the module's classes.
#[pymodule]
fn pyguara_core_rs(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<flocking::NativeFlockingSolver>()?;
    module.add_class::<flowfield::NativeFlowField>()?;
    module.add_class::<particles::NativeParticlePool>()?;
    module.add_class::<sparks::NativeSparkPool>()?;
    Ok(())
}
