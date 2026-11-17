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
//! **A write does not rebuild the grid by itself.** The grid is a
//! snapshot, rebuilt wholesale in O(n), and a slot written since the
//! last rebuild is *pending*: skipped where the stale grid lists it and
//! checked directly by every query. Once more than about `sqrt(2n)`
//! slots are pending the next query rebuilds instead. So the pattern
//! every consumer in the engine has -- sync the whole index, then sweep
//! it -- still costs one rebuild for `n` queries, and a caller that
//! *alternates* writes and queries pays O(sqrt n) a query where a
//! rebuild per query made that loop quadratic.
//! `tests/performance/test_perf_spatial.py` holds both.
//!
//! **A key that re-enters the index while being hashed raises here and
//! does not in Python.** Every method takes `&mut self`, so PyO3 holds an
//! exclusive borrow for its duration and a nested call gets
//! `RuntimeError: Already borrowed`. Reaching it takes a key whose
//! `__hash__` or `__eq__` calls back into the same index, which no engine
//! key does -- they are entity id strings. Nor is Python's tolerance
//! worth much: it survives a re-entry that fires *once*, and recurses
//! until the stack runs out if the key re-enters every time, since the
//! nested query hashes it again. So this is one store failing loudly
//! where the other fails slowly. It is stated because `SpatialHash`
//! otherwise promises to take whatever key the caller likes, and because
//! the *safe* version of the same shape is load-bearing:
//! a query materialises its result list before returning, so the engine's
//! real pattern -- iterate a query, destroy an entity, let
//! `SpatialIndexSystem` remove it -- releases the borrow first and works.
//! Returning a lazy view instead would break that, which is what
//! `test_the_index_can_be_mutated_from_inside_a_loop_over_a_query` is for.
//!
//! **Membership is exact and the tests assert it on every operation.**
//! An index decides which enemy a magnet pulls and which target a bullet
//! hits, so this is the flow field's regime rather than the particle
//! pool's: `tests/test_spatial_hash_reference.py` compares results with
//! the Python reference index, and `tests/test_spatial_hash_golden.py`
//! with recorded answers, both with `==` on sorted keys. The order is
//! deliberately *not* pinned -- see `query_radius`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::grid::{check_position, check_query_span, Grid};

/// Every bit set, as `spatial.py`'s `_FULL_MASK`.
const FULL_MASK: u32 = 0xFFFF_FFFF;

/// A uniform-grid spatial index over caller-chosen Python keys.
///
/// Reached only through `pyguara.common.spatial.SpatialHash`, which is a
/// thin wrapper over it; there is no Python implementation to fall back
/// to.
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
    /// The grid must be rebuilt before the next query can use it.
    dirty: bool,
    /// Slots written since the grid was built, while there are few
    /// enough to check one by one. Not maintained once `dirty` is set.
    pending: Vec<u32>,
    /// Slot -> whether it is in `pending`, so the grid's stale entry for
    /// it is skipped.
    is_pending: Vec<bool>,
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
            pending: Vec::new(),
            is_pending: Vec::new(),
            grid: Grid::default(),
            scratch: Vec::new(),
        })
    }

    /// Add `key`, or reposition it if already present.
    ///
    /// Unlike the Python index this does no cell comparison to decide
    /// whether a move is "free": the slot becomes pending either way,
    /// and a pending slot is checked by position, not by cell.
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
            self.touched(slot);
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
                self.is_pending.push(false);
                self.keys.len() - 1
            }
        };
        map.set_item(key, slot)?;
        self.touched(slot);
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
        // The grid is left alone: its entry for this slot fails the
        // liveness check until a rebuild drops it, and a later insert
        // that reuses the slot marks it pending.
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
            if self.is_pending[index] || self.masks[index] & mask == 0 {
                continue;
            }
            if self.grid.cell_of(self.xs[index]) != want_cx
                || self.grid.cell_of(self.ys[index]) != want_cy
            {
                continue;
            }
            found.append(key)?;
        }
        for &slot in &self.pending {
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
            if self.is_pending[index] || self.masks[index] & mask == 0 {
                continue;
            }
            found.append(key)?;
        }
        self.scratch = scratch;
        // The same squared-distance test `Grid::neighbours` applies.
        let radius_sq = radius * radius;
        for &slot in &self.pending {
            let index = slot as usize;
            let Some(key) = &self.keys[index] else {
                continue;
            };
            if self.masks[index] & mask == 0 {
                continue;
            }
            let offset_x = self.xs[index] - center.0;
            let offset_y = self.ys[index] - center.1;
            if offset_x * offset_x + offset_y * offset_y <= radius_sq {
                found.append(key)?;
            }
        }
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
            if self.is_pending[index] || self.masks[index] & mask == 0 {
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
        for &slot in &self.pending {
            let index = slot as usize;
            let Some(key) = &self.keys[index] else {
                continue;
            };
            if self.masks[index] & mask == 0 {
                continue;
            }
            let (x, y) = (self.xs[index], self.ys[index]);
            if x < left || x >= right || y < top || y >= bottom {
                continue;
            }
            found.append(key)?;
        }
        Ok(found)
    }

    /// How many keys the index holds. `SpatialHash` has no equivalent;
    /// the parity suite uses it to confirm `remove` reclaimed a slot.
    fn __len__(&self) -> usize {
        self.keys.len() - self.free.len()
    }
}

impl NativeSpatialHash {
    /// Record that a slot's position or mask was written.
    ///
    /// The slot joins `pending` while that list is short enough to scan
    /// on every query. Past `sqrt(2n)` slots, scanning costs more than a
    /// rebuild amortised over the queries it serves, so the index is
    /// marked for one and stops tracking.
    fn touched(&mut self, slot: usize) {
        if self.dirty || self.is_pending[slot] {
            return;
        }
        let limit = (((2 * self.keys.len()) as f64).sqrt() as usize).max(16);
        if self.pending.len() >= limit {
            self.dirty = true;
            return;
        }
        self.pending.push(slot as u32);
        self.is_pending[slot] = true;
    }

    /// Re-index, if enough has been written since the grid was built.
    fn rebuild_if_dirty(&mut self) {
        if !self.dirty {
            return;
        }
        self.grid.build(&self.xs, &self.ys, self.cell_size);
        for &slot in &self.pending {
            self.is_pending[slot as usize] = false;
        }
        self.pending.clear();
        self.dirty = false;
    }
}
