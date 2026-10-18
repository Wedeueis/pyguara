//! The uniform grid every native spatial consumer shares.
//!
//! One implementation, used by the flocking solver over a tick's snapshot
//! positions and by `NativeSpatialHash` over a persistent key set. It was
//! written for the first and extracted for the second, which is why its
//! vocabulary is positions and slots rather than keys: it indexes two
//! parallel coordinate arrays and hands back indices into them. Whatever
//! a slot *means* belongs to the caller.
//!
//! It mirrors `pyguara/common/spatial.py` deliberately and exactly:
//! `cell_of` is that module's `_cell_of`, and `neighbours` is
//! `query_radius` -- the cell range derived straight from
//! `centre +/- radius`, the distance test squared, and candidates
//! confirmed rather than assumed. Parity with the Python index is a
//! tested property, so a change here is a change to both stores.

use pyo3::exceptions::{PyOverflowError, PyValueError};
use pyo3::prelude::*;

/// Largest cell span one radius query may cover.
///
/// A sanity bound on `radius / cell_size`, not a tuning knob. The default
/// pairing is 80 over 64, which spans three cells per axis; this allows a
/// thousand. Python has no equivalent limit and does not need one -- it
/// simply takes proportionally longer, and a `cell_size=0.001` typo
/// becomes a hang rather than an error. Failing loudly is the better of
/// the two.
pub(crate) const MAX_QUERY_CELLS: u64 = 1 << 20;

/// Largest cell index the grid can represent faithfully.
///
/// `cell_of` casts a float cell to `i64`, and Rust saturates that cast
/// rather than wrapping -- so two positions far enough apart would both
/// land on `i64::MAX` and share a cell. The exact-distance test keeps
/// `query_radius` correct regardless, but `query_point` has no distance
/// test to fall back on, so it would start reporting keys from the other
/// side of the world. Python has no equivalent limit, and the divergence
/// begins past 9.2e18 cells -- about 5.9e20 world units at the default
/// cell size, which is 40 orders of magnitude outside any game's
/// coordinates. Rejecting it is still better than diverging silently.
pub(crate) const MAX_CELL_INDEX: f64 = 9.223_372_036_854_776e18;

/// Reject a position the grid cannot index as Python's `_cell_of` would.
///
/// Matches `math.floor`'s own failures by exception type, which is what
/// the parity suite pins: `ValueError` for NaN, `OverflowError` for an
/// infinity. The out-of-range case has no Python counterpart and says so.
pub(crate) fn check_position(x: f64, y: f64, cell_size: f64) -> PyResult<()> {
    for value in [x, y] {
        if value.is_nan() {
            return Err(PyValueError::new_err(
                "cannot convert float NaN to integer",
            ));
        }
        if value.is_infinite() {
            return Err(PyOverflowError::new_err(
                "cannot convert float infinity to integer",
            ));
        }
        if (value / cell_size).abs() >= MAX_CELL_INDEX {
            return Err(PyValueError::new_err(format!(
                "a coordinate of {value} over a cell_size of {cell_size} is past \
                 cell {MAX_CELL_INDEX:e}, beyond which the native index cannot tell \
                 two cells apart. The Python index has no such limit."
            )));
        }
    }
    Ok(())
}

/// Reject a radius/cell-size pairing whose query would span absurdly many
/// cells, naming the configuration rather than arriving as a timeout.
pub(crate) fn check_query_span(widest_radius: f64, cell_size: f64) -> PyResult<()> {
    let span = (2.0 * widest_radius / cell_size).floor() + 2.0;
    if !span.is_finite() || span * span > MAX_QUERY_CELLS as f64 {
        return Err(PyValueError::new_err(format!(
            "a radius of {widest_radius} over a cell_size of {cell_size} spans \
             roughly {span} cells per axis, past the {MAX_QUERY_CELLS}-cell limit \
             for one query. Raise cell_size, or lower the radius."
        )));
    }
    Ok(())
}

/// A uniform grid over two parallel coordinate arrays.
///
/// Rebuilt wholesale rather than maintained, like the `SpatialHash` it
/// mirrors and for the same reason: a caller that sweeps every slot
/// anyway gets the rebuild for free, against the alternative of an index
/// that can hold a stale entry. `NativeSpatialHash` takes the same trade
/// one step further -- it rebuilds on the first query after any write,
/// so a caller that inserts everything and then queries everything pays
/// for exactly one.
///
/// Cells are bucketed by a hash rather than stored in a map, and the
/// buckets are a flat CSR pair filled by counting sort, so a rebuild
/// allocates nothing after the first. **Hash collisions cannot affect the
/// result**, which is what makes that safe: two distinct cells landing in
/// one bucket only means a query sees slots from a cell it did not ask
/// about, and every candidate is then confirmed against an exact squared
/// distance. A slot within `radius` of the centre necessarily lies in
/// the queried cell range, so the extras can only ever *fail* that test.
/// The one thing collisions could break is double-counting, if two cells
/// in a single query's range shared a bucket -- hence the visit stamps.
#[derive(Default)]
pub(crate) struct Grid {
    cell_size: f64,
    /// `buckets - 1`, so a hash becomes an index with one `&`.
    mask: usize,
    /// Which bucket each slot's cell hashes to.
    bucket_of: Vec<usize>,
    /// CSR row starts, `buckets + 1` long.
    offsets: Vec<u32>,
    /// A copy of `offsets`, advanced while scattering.
    cursor: Vec<u32>,
    /// Slots, grouped by bucket.
    items: Vec<u32>,
    /// Per-bucket stamp of the query that last visited it.
    visited: Vec<u32>,
    stamp: u32,
}

impl Grid {
    /// The cell a world coordinate falls in, as `SpatialHash._cell_of`.
    #[inline]
    pub(crate) fn cell_of(&self, value: f64) -> i64 {
        (value / self.cell_size).floor() as i64
    }

    /// Scatter a cell's coordinates across the bucket range.
    ///
    /// Two odd multipliers and a xor-fold, which is enough for integer
    /// cell coordinates: they arrive in a dense band, and the fold is what
    /// stops the mask throwing away all the mixing.
    ///
    /// **Any deterministic function of `(cx, cy)` is correct here**, and
    /// that is worth knowing before trying to test this. Insert and query
    /// both go through it, so a different mixing merely redistributes the
    /// buckets; swapping the two multipliers was tried as a sabotage and
    /// no test noticed, as none should. What the constants buy is the
    /// distribution, and the only thing that can go wrong is slower
    /// queries -- which `tests/performance/test_perf_spatial.py` is the
    /// place to notice.
    #[inline]
    fn bucket(&self, cx: i64, cy: i64) -> usize {
        let hash = (cx as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15)
            ^ (cy as u64).wrapping_mul(0xC2B2_AE3D_27D4_EB4F);
        ((hash ^ (hash >> 29)) as usize) & self.mask
    }

    /// Index `count` positions, discarding any previous contents.
    ///
    /// A non-finite coordinate is tolerated here rather than rejected,
    /// although `check_position` rejects one on the way in: a removed
    /// key's slot is parked at NaN, and a NaN cast to `i64` saturates to
    /// 0, so such a slot lands in cell (0, 0)'s bucket. It cannot be
    /// returned by a query -- its mask is zeroed, and every NaN distance
    /// comparison is false anyway -- so the only cost is a slightly
    /// fuller bucket.
    pub(crate) fn build(&mut self, snap_x: &[f64], snap_y: &[f64], cell_size: f64) {
        let count = snap_x.len();
        self.cell_size = cell_size;

        let buckets = (count * 2).next_power_of_two().max(16);
        self.mask = buckets - 1;

        self.bucket_of.clear();
        self.bucket_of.reserve(count);
        for slot in 0..count {
            let cx = self.cell_of(snap_x[slot]);
            let cy = self.cell_of(snap_y[slot]);
            self.bucket_of.push(self.bucket(cx, cy));
        }

        // Counting sort into CSR. `offsets[b + 1]` counts first, then the
        // prefix sum turns it into the end of bucket `b`.
        self.offsets.clear();
        self.offsets.resize(buckets + 1, 0);
        for &bucket in &self.bucket_of {
            self.offsets[bucket + 1] += 1;
        }
        for index in 0..buckets {
            self.offsets[index + 1] += self.offsets[index];
        }

        self.items.clear();
        self.items.resize(count, 0);
        self.cursor.clear();
        self.cursor.extend_from_slice(&self.offsets[..buckets]);
        // Slots land in increasing order within a bucket. Nothing depends
        // on that -- the candidate order cannot be made to match Python's
        // anyway, since Python's comes from set iteration -- but it does
        // make a native sweep reproducible against itself, which replay
        // comparisons rely on.
        for (slot, &bucket) in self.bucket_of.iter().enumerate() {
            let at = self.cursor[bucket] as usize;
            self.items[at] = slot as u32;
            self.cursor[bucket] += 1;
        }

        self.visited.clear();
        self.visited.resize(buckets, 0);
        self.stamp = 0;
    }

    /// Bump the visit stamp, so this query cannot revisit a bucket.
    #[inline]
    fn next_stamp(&mut self) -> u32 {
        self.stamp = match self.stamp.checked_add(1) {
            Some(next) => next,
            None => {
                // Once in several billion queries. Clearing is cheaper
                // than carrying a wider counter for it.
                self.visited.iter_mut().for_each(|slot| *slot = 0);
                1
            }
        };
        self.stamp
    }

    /// Every slot in the cells spanning a cell range, unfiltered.
    ///
    /// `SpatialHash._candidates`, and the same warning applies in
    /// reverse: this yields slots from *at least* the cells asked for,
    /// because a bucket may hold more than one cell. A caller that does
    /// not go on to confirm a position -- as `neighbours` does with its
    /// distance test -- must confirm the cell itself.
    pub(crate) fn cells_in_range(
        &mut self,
        min_cx: i64,
        max_cx: i64,
        min_cy: i64,
        max_cy: i64,
        out: &mut Vec<u32>,
    ) {
        out.clear();
        let stamp = self.next_stamp();
        for cx in min_cx..=max_cx {
            for cy in min_cy..=max_cy {
                let bucket = self.bucket(cx, cy);
                if self.visited[bucket] == stamp {
                    continue;
                }
                self.visited[bucket] = stamp;
                let from = self.offsets[bucket] as usize;
                let to = self.offsets[bucket + 1] as usize;
                out.extend_from_slice(&self.items[from..to]);
            }
        }
    }

    /// Every slot in the bucket one cell hashes to, unfiltered.
    pub(crate) fn visit_bucket(&mut self, cx: i64, cy: i64, out: &mut Vec<u32>) {
        self.cells_in_range(cx, cx, cy, cy, out);
    }

    /// Collect every slot within `radius` of a centre, as
    /// `SpatialHash.query_radius` would -- the centre's own slot included
    /// when the centre is one of the indexed positions.
    ///
    /// The cell range comes straight from `centre +/- radius` and the
    /// distance test is squared, exactly as there.
    pub(crate) fn neighbours(
        &mut self,
        centre_x: f64,
        centre_y: f64,
        radius: f64,
        snap_x: &[f64],
        snap_y: &[f64],
        out: &mut Vec<u32>,
    ) {
        out.clear();

        let min_cx = self.cell_of(centre_x - radius);
        let max_cx = self.cell_of(centre_x + radius);
        let min_cy = self.cell_of(centre_y - radius);
        let max_cy = self.cell_of(centre_y + radius);

        let stamp = self.next_stamp();

        let radius_sq = radius * radius;
        for cx in min_cx..=max_cx {
            for cy in min_cy..=max_cy {
                let bucket = self.bucket(cx, cy);
                if self.visited[bucket] == stamp {
                    continue;
                }
                self.visited[bucket] = stamp;
                let from = self.offsets[bucket] as usize;
                let to = self.offsets[bucket + 1] as usize;
                for &slot in &self.items[from..to] {
                    let index = slot as usize;
                    let offset_x = snap_x[index] - centre_x;
                    let offset_y = snap_y[index] - centre_y;
                    if offset_x * offset_x + offset_y * offset_y <= radius_sq {
                        out.push(slot);
                    }
                }
            }
        }
    }
}
