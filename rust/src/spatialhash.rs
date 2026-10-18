//! `SpatialHash`, natively, with the same Python-facing shape.
//!
//! This is the one native class that hands Python objects back, and
//! `docs/adr/0004-the-native-boundary.md` originally ruled it out for
//! exactly that reason: a query returns `list[K]` of caller-chosen keys,
//! so the crossing scales with how many candidates the query found. That
//! reasoning was half right and the conclusion was wrong, which Decision
//! 7 now records. The crossing does scale with `k` -- but so does the
//! Python broad-phase it replaces, and it does so at about twenty times
//! the cost per candidate, because Python pays a dict lookup, two
//! subtractions and a multiply-add where the crossing pays an incref and
//! a list append. The ratio is therefore roughly **flat in density**, at
//! 16-22x measured over k = 17 to 32.
//!
//! What makes that work is holding the keys rather than rebuilding them:
//! `keys` stores the `Py<PyAny>` the caller inserted, so returning a
//! candidate is a reference count, not a string allocation. Returning
//! `Vec<String>` would have made the ADR's original objection true.
//!
//! **One access pattern is slower here than in Python, and it is
//! asymptotically slower rather than a little slower.** The grid is
//! rebuilt on the first query after any write, which costs O(n) and is
//! free for the pattern every consumer in the engine has -- sync the
//! whole index, then sweep it, so one rebuild serves `n` queries. A
//! caller that *alternates* insert and query instead pays for `n`
//! rebuilds: measured against Python, 1.9x faster at 250 keys, 0.52x at
//! 1000 and **0.13x at 4000**. Python's incremental insert is O(1) and
//! wins outright there. `accelerate=False` is the remedy, and
//! `tests/performance/test_perf_spatial.py` bounds how bad it is allowed
//! to get.
//!
//! **Parity is bit-exact and the suite asserts it on every operation.**
//! An index decides which enemy a magnet pulls and which target a bullet
//! hits, so this is the flow field's regime rather than the particle
//! pool's: `tests/test_native_spatial_hash_parity.py` compares results
//! against the Python index with `==` on sorted keys. One thing is
//! deliberately *not* pinned, because Python does not pin it either --
//! see `query_radius`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::grid::{check_position, check_query_span, Grid};

/// Every bit set, as `spatial.py`'s `_FULL_MASK`.
const FULL_MASK: u32 = 0xFFFF_FFFF;

/// A uniform-grid spatial index over caller-chosen Python keys.
///
/// Mirrors `pyguara.common.spatial.SpatialHash` method for method, and
/// is reached only through it -- a caller writes `SpatialHash(...)` and
/// `accelerate=`/`PerformanceConfig.native_acceleration` decides which
/// store answers, like every other native store. Under the default
/// `auto` that is *this* one whenever the extension is built; the Python
/// implementation is the fallback rather than the default.
#[pyclass]
pub struct NativeSpatialHash {
    cell_size: f64,
    /// Slot -> the key the caller inserted. `None` marks a freed slot.
    keys: Vec<Option<Py<PyAny>>>,
    xs: Vec<f64>,
    ys: Vec<f64>,
    masks: Vec<u32>,
    /// Key -> slot. A `PyDict` rather than a Rust map so lookups use
    /// CPython's own hashing and equality, which is what makes an
    /// arbitrary hashable key work at all.
    slot_of: Py<PyDict>,
    /// Slots whose key was removed, available for the next insert.
    free: Vec<u32>,
    /// Set by every write, cleared by the rebuild the next query forces.
    dirty: bool,
    grid: Grid,
    /// Reused between queries, so a query allocates only its result.
    scratch: Vec<u32>,
}

#[pymethods]
impl NativeSpatialHash {
    /// Create an empty index with the given cell size.
    #[new]
    #[pyo3(signature = (cell_size = 64.0))]
    fn new(python: Python<'_>, cell_size: f64) -> PyResult<Self> {
        if !(cell_size.is_finite() && cell_size > 0.0) {
            return Err(PyValueError::new_err(format!(
                "cell_size must be finite and positive, got {cell_size}"
            )));
        }
        Ok(Self {
            cell_size,
            keys: Vec::new(),
            xs: Vec::new(),
            ys: Vec::new(),
            masks: Vec::new(),
            slot_of: PyDict::new(python).unbind(),
            free: Vec::new(),
            dirty: true,
            grid: Grid::default(),
            scratch: Vec::new(),
        })
    }

    /// Add `key`, or reposition it if already present.
    ///
    /// Unlike the Python index this does no cell comparison to decide
    /// whether a move is "free": the grid is rebuilt on the next query
    /// regardless, so checking would be work that changes nothing. That
    /// deferral is also what makes an alternating insert/query loop
    /// quadratic here -- see the module docstring.
    #[pyo3(signature = (key, position, mask = FULL_MASK))]
    fn insert(
        &mut self,
        python: Python<'_>,
        key: Py<PyAny>,
        position: (f64, f64),
        mask: u32,
    ) -> PyResult<()> {
        check_position(position.0, position.1, self.cell_size)?;
        let map = self.slot_of.bind(python);
        if let Some(existing) = map.get_item(&key)? {
            let slot: usize = existing.extract()?;
            self.xs[slot] = position.0;
            self.ys[slot] = position.1;
            self.masks[slot] = mask;
            self.dirty = true;
            return Ok(());
        }

        let slot = match self.free.pop() {
            Some(reused) => {
                let slot = reused as usize;
                self.keys[slot] = Some(key.clone_ref(python));
                self.xs[slot] = position.0;
                self.ys[slot] = position.1;
                self.masks[slot] = mask;
                slot
            }
            None => {
                self.keys.push(Some(key.clone_ref(python)));
                self.xs.push(position.0);
                self.ys.push(position.1);
                self.masks.push(mask);
                self.keys.len() - 1
            }
        };
        map.set_item(key, slot)?;
        self.dirty = true;
        Ok(())
    }

    /// Remove `key`, if present. A no-op otherwise.
    fn remove(&mut self, python: Python<'_>, key: Py<PyAny>) -> PyResult<()> {
        let map = self.slot_of.bind(python);
        let Some(existing) = map.get_item(&key)? else {
            return Ok(());
        };
        let slot: usize = existing.extract()?;
        map.del_item(key)?;
        // `keys[slot] = None` is the *only* thing that makes this slot
        // invisible, and every query checks it first for that reason.
        // Zeroing the mask as well was tried and removed: the suite could
        // not tell its absence from its presence, which is the definition
        // of a guard that is not guarding.
        self.keys[slot] = None;
        // NaN rather than a real position so `query_radius` rejects the
        // slot on distance before it reaches the liveness check -- which
        // is a cost saving, not a correctness one. `query_point` and
        // `query_rect` have no distance test and rely on liveness alone.
        self.xs[slot] = f64::NAN;
        self.ys[slot] = f64::NAN;
        self.free.push(slot as u32);
        self.dirty = true;
        Ok(())
    }

    /// Every key sharing `point`'s cell, filtered by `mask`.
    #[pyo3(signature = (point, mask = FULL_MASK))]
    fn query_point<'py>(
        &mut self,
        python: Python<'py>,
        point: (f64, f64),
        mask: u32,
    ) -> PyResult<Bound<'py, PyList>> {
        check_position(point.0, point.1, self.cell_size)?;
        self.rebuild_if_dirty();
        // The Python index looks up one cell and filters by mask, with no
        // distance test at all -- a key anywhere in the cell counts. A
        // bucket may hold more than one cell, so the cell is re-confirmed
        // here where Python gets it from the dict key.
        let want_cx = self.grid.cell_of(point.0);
        let want_cy = self.grid.cell_of(point.1);
        let found = PyList::empty(python);
        self.grid.visit_bucket(want_cx, want_cy, &mut self.scratch);
        for &slot in &self.scratch {
            let index = slot as usize;
            let Some(key) = &self.keys[index] else {
                continue;
            };
            if self.masks[index] & mask == 0 {
                continue;
            }
            if self.grid.cell_of(self.xs[index]) != want_cx
                || self.grid.cell_of(self.ys[index]) != want_cy
            {
                continue;
            }
            found.append(key)?;
        }
        Ok(found)
    }

    /// Every key within `radius` of `center`, confirmed by exact distance.
    ///
    /// **The order is not Python's and cannot be.** Python yields from
    /// `set[K]`, so its candidate order is the keys' hash order -- which
    /// `PYTHONHASHSEED` randomises per process for the string keys the
    /// engine actually uses. A caller that takes the *first* result of a
    /// query returning several (as `ProjectileSystem._check_hit` does)
    /// therefore already gets an arbitrary one, differing between two runs
    /// of the same Python process. This store returns them in slot order,
    /// which is at least stable; the parity suite compares sorted results
    /// and pins the arbitrariness as a documented divergence rather than
    /// pretending either store decides it.
    #[pyo3(signature = (center, radius, mask = FULL_MASK))]
    fn query_radius<'py>(
        &mut self,
        python: Python<'py>,
        center: (f64, f64),
        radius: f64,
        mask: u32,
    ) -> PyResult<Bound<'py, PyList>> {
        check_position(center.0, center.1, self.cell_size)?;
        check_query_span(radius, self.cell_size)?;
        self.rebuild_if_dirty();
        let found = PyList::empty(python);
        // `Grid::neighbours` is the shared implementation of exactly the
        // cell range and squared-distance test `query_radius` documents.
        let mut scratch = std::mem::take(&mut self.scratch);
        self.grid
            .neighbours(center.0, center.1, radius, &self.xs, &self.ys, &mut scratch);
        for &slot in &scratch {
            let index = slot as usize;
            let Some(key) = &self.keys[index] else {
                continue;
            };
            if self.masks[index] & mask == 0 {
                continue;
            }
            found.append(key)?;
        }
        self.scratch = scratch;
        Ok(found)
    }

    /// Every key whose position lies inside the given bounds.
    ///
    /// Half-open, as `Rect.contains_point` is.
    ///
    /// Takes the four edges rather than a `Rect`, because `Rect` is a
    /// plain Python class and reading four attributes across the boundary
    /// costs more than the caller unpacking it. `SpatialHash.query_rect`
    /// keeps the `Rect` signature and does that unpacking.
    #[pyo3(signature = (left, top, right, bottom, mask = FULL_MASK))]
    fn query_rect<'py>(
        &mut self,
        python: Python<'py>,
        left: f64,
        top: f64,
        right: f64,
        bottom: f64,
        mask: u32,
    ) -> PyResult<Bound<'py, PyList>> {
        check_position(left, top, self.cell_size)?;
        check_position(right, bottom, self.cell_size)?;
        // `check_query_span` is written for a radius, so halve the wider
        // side to speak its language: the limit is on cells visited, and
        // a rect visits as many as a radius covering the same extent.
        let half_extent = ((right - left) * 0.5).max((bottom - top) * 0.5);
        check_query_span(half_extent, self.cell_size)?;
        self.rebuild_if_dirty();

        let min_cx = self.grid.cell_of(left);
        let max_cx = self.grid.cell_of(right);
        let min_cy = self.grid.cell_of(top);
        let max_cy = self.grid.cell_of(bottom);

        let found = PyList::empty(python);
        let mut scratch = std::mem::take(&mut self.scratch);
        self.grid
            .cells_in_range(min_cx, max_cx, min_cy, max_cy, &mut scratch);
        for &slot in &scratch {
            let index = slot as usize;
            let Some(key) = &self.keys[index] else {
                continue;
            };
            if self.masks[index] & mask == 0 {
                continue;
            }
            // `Rect.contains_point` is `left <= x < right`: inclusive on
            // the left and top edges, exclusive on the right and bottom,
            // matching `pygame.Rect.collidepoint`. Getting this inclusive
            // on all four looks harmless and puts a key one pixel outside
            // the rect into the result.
            let (x, y) = (self.xs[index], self.ys[index]);
            if x < left || x >= right || y < top || y >= bottom {
                continue;
            }
            found.append(key)?;
        }
        self.scratch = scratch;
        Ok(found)
    }

    /// How many keys the index holds. `SpatialHash` has no equivalent;
    /// the parity suite uses it to confirm `remove` reclaimed a slot.
    fn __len__(&self) -> usize {
        self.keys.len() - self.free.len()
    }
}

impl NativeSpatialHash {
    /// Re-index, if a write has happened since the last query.
    fn rebuild_if_dirty(&mut self) {
        if !self.dirty {
            return;
        }
        self.grid.build(&self.xs, &self.ys, self.cell_size);
        self.dirty = false;
    }
}
