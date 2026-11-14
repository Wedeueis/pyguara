//! A native mirror of a physics world's static boxes, for the queries a
//! character mover makes.
//!
//! `CharacterMover` moves a box one whole pixel at a time and asks the
//! physics engine, per pixel, whether the box would overlap something. In
//! the pymunk backend each question builds a `pymunk.Body` and a
//! `pymunk.Poly` in Python before Chipmunk is even called: measured in a
//! room of 200 enemies, those probes were 31% of a rendered frame and half
//! of a host's tick.
//!
//! This holds the same geometry -- the axis-aligned boxes of static,
//! unrotated, non-sensor shapes -- and answers the same questions without
//! Python objects. It does **not** try to be Chipmunk. Every answer is one
//! of three: certainly clear, certainly this one box, or *ask Chipmunk*.
//! Anything within `MARGIN` of touching is the third, as is a probe that
//! overlaps several boxes, since which one Chipmunk reports first depends
//! on the insertion history of its spatial index. So the fast path cannot
//! disagree with the slow one; it can only decline to answer.
//!
//! That is a different contract from the stores in this crate that have a
//! Python twin and a parity suite with a tolerance. There is no tolerance
//! here: `tests/test_native_solids_parity.py` compares with `==`.

use pyo3::prelude::*;
use pyo3::types::PyDict;

/// How close to touching a probe may come before the answer is left to
/// Chipmunk. Far above any rounding in either implementation at world
/// coordinates up to millions of pixels, and far below `SKIN` (0.05), the
/// allowance the mover itself shrinks its probe by.
const MARGIN: f64 = 1e-6;

/// Answer codes for `overlap`, and blocker codes for `sweep`.
const CLEAR: i64 = -1;
/// The probe is within `MARGIN` of a box's edge.
const UNSURE: i64 = -2;
/// The probe certainly overlaps more than one owner's boxes.
const SEVERAL: i64 = -3;

/// Below this many boxes a linear scan beats the grid.
const SCAN_LIMIT: usize = 24;

struct Solid {
    left: f64,
    bottom: f64,
    right: f64,
    top: f64,
    categories: u32,
    mask: u32,
    owner: u32,
}

/// The static boxes of one physics space.
#[pyclass]
pub struct NativeSolids {
    solids: Vec<Solid>,
    // A dense grid over the boxes' bounds, in compressed-row form: cell
    // `c` holds `members[starts[c]..starts[c + 1]]`.
    origin_x: f64,
    origin_y: f64,
    cell: f64,
    columns: usize,
    rows: usize,
    starts: Vec<u32>,
    members: Vec<u32>,
}

impl NativeSolids {
    fn build_grid(&mut self) {
        self.starts.clear();
        self.members.clear();
        self.columns = 0;
        self.rows = 0;
        if self.solids.len() <= SCAN_LIMIT {
            return;
        }
        let mut left = f64::INFINITY;
        let mut bottom = f64::INFINITY;
        let mut right = f64::NEG_INFINITY;
        let mut top = f64::NEG_INFINITY;
        for solid in &self.solids {
            left = left.min(solid.left);
            bottom = bottom.min(solid.bottom);
            right = right.max(solid.right);
            top = top.max(solid.top);
        }
        let width = (right - left).max(1.0);
        let height = (top - bottom).max(1.0);
        // About one box per cell on average, capped so a huge sparse world
        // cannot ask for an unbounded table.
        let wanted = (self.solids.len() as f64).min(65_536.0);
        self.cell = ((width * height) / wanted).sqrt().max(16.0);
        self.columns = ((width / self.cell).ceil() as usize).clamp(1, 1024);
        self.rows = ((height / self.cell).ceil() as usize).clamp(1, 1024);
        self.origin_x = left;
        self.origin_y = bottom;
        let cells = self.columns * self.rows;
        let mut counts = vec![0u32; cells + 1];
        let spans: Vec<(usize, usize, usize, usize)> = self
            .solids
            .iter()
            .map(|s| self.span(s.left, s.bottom, s.right, s.top))
            .collect();
        for &(c0, r0, c1, r1) in &spans {
            for row in r0..=r1 {
                for column in c0..=c1 {
                    counts[row * self.columns + column + 1] += 1;
                }
            }
        }
        for cell in 0..cells {
            counts[cell + 1] += counts[cell];
        }
        self.starts = counts.clone();
        self.members = vec![0; counts[cells] as usize];
        let mut cursor = counts;
        for (index, &(c0, r0, c1, r1)) in spans.iter().enumerate() {
            for row in r0..=r1 {
                for column in c0..=c1 {
                    let cell = row * self.columns + column;
                    self.members[cursor[cell] as usize] = index as u32;
                    cursor[cell] += 1;
                }
            }
        }
    }

    /// The inclusive cell range a rectangle touches, clamped to the grid.
    ///
    /// Clamping is what makes it conservative: a rectangle outside the
    /// bounds maps to the edge cells, whose boxes are then tested exactly.
    fn span(&self, left: f64, bottom: f64, right: f64, top: f64) -> (usize, usize, usize, usize) {
        let column = |x: f64| -> usize {
            let raw = ((x - self.origin_x) / self.cell).floor();
            if raw.is_nan() || raw < 0.0 {
                0
            } else {
                (raw as usize).min(self.columns - 1)
            }
        };
        let row = |y: f64| -> usize {
            let raw = ((y - self.origin_y) / self.cell).floor();
            if raw.is_nan() || raw < 0.0 {
                0
            } else {
                (raw as usize).min(self.rows - 1)
            }
        };
        (column(left), row(bottom), column(right), row(top))
    }

    /// Call `visit` with every box that might touch the rectangle. A box
    /// can be visited more than once; every caller tolerates that.
    fn candidates(
        &self,
        left: f64,
        bottom: f64,
        right: f64,
        top: f64,
        mut visit: impl FnMut(&Solid) -> bool,
    ) {
        if self.columns == 0 {
            for solid in &self.solids {
                if !visit(solid) {
                    return;
                }
            }
            return;
        }
        let (c0, r0, c1, r1) = self.span(left, bottom, right, top);
        for row in r0..=r1 {
            for column in c0..=c1 {
                let cell = row * self.columns + column;
                let from = self.starts[cell] as usize;
                let to = self.starts[cell + 1] as usize;
                for &member in &self.members[from..to] {
                    if !visit(&self.solids[member as usize]) {
                        return;
                    }
                }
            }
        }
    }

    /// Classify one probe box. See the answer codes above.
    fn classify(&self, x: f64, y: f64, half_x: f64, half_y: f64, mask: u32, ignore: i64) -> i64 {
        if !(x.is_finite() && y.is_finite() && half_x.is_finite() && half_y.is_finite()) {
            // Every comparison below is false for a NaN, which would read
            // as a certain overlap.
            return UNSURE;
        }
        // Spelled as Chipmunk spells a box's corners -- centre plus a
        // signed half extent -- so the edges are the same floats.
        let left = x + -half_x;
        let right = x + half_x;
        let bottom = y + -half_y;
        let top = y + half_y;
        let mut answer = CLEAR;
        self.candidates(
            left - MARGIN,
            bottom - MARGIN,
            right + MARGIN,
            top + MARGIN,
            |solid| {
                // Chipmunk's filter test with the probe's categories all
                // set and its group zero.
                if solid.categories & mask == 0 || solid.mask == 0 {
                    return true;
                }
                if i64::from(solid.owner) == ignore {
                    return true;
                }
                let gap_x = (solid.left - right).max(left - solid.right);
                let gap_y = (solid.bottom - top).max(bottom - solid.top);
                if gap_x > MARGIN || gap_y > MARGIN {
                    return true;
                }
                if gap_x >= -MARGIN || gap_y >= -MARGIN {
                    answer = UNSURE;
                    return false;
                }
                let owner = i64::from(solid.owner);
                if answer == CLEAR {
                    answer = owner;
                } else if answer != owner {
                    answer = SEVERAL;
                }
                true
            },
        );
        answer
    }

    /// One axis of `CharacterMover._move_axis`. `None` means a probe was
    /// `UNSURE` and the caller must run the Python loop instead.
    #[allow(clippy::too_many_arguments)]
    fn axis(
        &self,
        mut current: f64,
        fixed: f64,
        half_x: f64,
        half_y: f64,
        distance: f64,
        mut remainder: f64,
        horizontal: bool,
        mask: u32,
        ignore: i64,
    ) -> Option<(f64, f64, i64)> {
        remainder += distance;
        // Python's `round()`: ties to even.
        let amount = remainder.round_ties_even();
        if !amount.is_finite() || amount.abs() > 1e7 {
            // Python raises on a non-finite remainder; let it. And a move
            // of ten million pixels is not one to loop over here.
            return None;
        }
        remainder -= amount;
        let mut amount = amount as i64;
        if amount == 0 {
            return Some((current, remainder, CLEAR));
        }
        let step: i64 = if amount > 0 { 1 } else { -1 };
        let stride = step as f64;
        while amount != 0 {
            let candidate = current + stride;
            let found = if horizontal {
                self.classify(candidate, fixed, half_x, half_y, mask, ignore)
            } else {
                self.classify(fixed, candidate, half_x, half_y, mask, ignore)
            };
            if found == UNSURE {
                return None;
            }
            if found != CLEAR {
                return Some((current, 0.0, found));
            }
            current = candidate;
            amount -= step;
        }
        Some((current, remainder, CLEAR))
    }
}

/// `(left, bottom, right, top, categories, mask, owner)`.
type SolidRow = (f64, f64, f64, f64, u32, u32, u32);

/// One body for `step_bodies`: box centre, collider offset, half extents,
/// velocity, remainder, and the entity id the mirror may know as an owner.
type StepRow<'py> = (
    f64,
    f64,
    f64,
    f64,
    f64,
    f64,
    f64,
    f64,
    f64,
    f64,
    Bound<'py, PyAny>,
);

#[pymethods]
impl NativeSolids {
    /// Build from one row per box.
    #[new]
    fn new(rows: Vec<SolidRow>) -> Self {
        let mut built = Self {
            solids: rows
                .into_iter()
                .map(|(left, bottom, right, top, categories, mask, owner)| Solid {
                    left,
                    bottom,
                    right,
                    top,
                    categories,
                    mask,
                    owner,
                })
                .collect(),
            origin_x: 0.0,
            origin_y: 0.0,
            cell: 1.0,
            columns: 0,
            rows: 0,
            starts: Vec::new(),
            members: Vec::new(),
        };
        built.build_grid();
        built
    }

    /// How many boxes are held.
    fn __len__(&self) -> usize {
        self.solids.len()
    }

    /// Which owner a box overlaps: an owner index, or -1 for certainly
    /// clear, -2 for too close to call, -3 for several owners.
    #[pyo3(signature = (x, y, half_x, half_y, mask, ignore = -1))]
    fn overlap(&self, x: f64, y: f64, half_x: f64, half_y: f64, mask: u32, ignore: i64) -> i64 {
        self.classify(x, y, half_x, half_y, mask, ignore)
    }

    /// The whole of `CharacterMover.move`: x, then y from where x ended.
    ///
    /// `half_x` and `half_y` are the probe's half extents, already shrunk
    /// by the mover's skin. Returns `(x, y, remainder_x, remainder_y,
    /// blocker_x, blocker_y)` with blockers as `overlap` codes -- -1 for
    /// none, -3 for "several, ask the engine which" -- or `None` when any
    /// probe on the way was too close to call.
    #[pyo3(signature = (x, y, half_x, half_y, delta_x, delta_y, remainder_x, remainder_y, mask, ignore = -1))]
    #[allow(clippy::too_many_arguments)]
    fn sweep(
        &self,
        x: f64,
        y: f64,
        half_x: f64,
        half_y: f64,
        delta_x: f64,
        delta_y: f64,
        remainder_x: f64,
        remainder_y: f64,
        mask: u32,
        ignore: i64,
    ) -> Option<(f64, f64, f64, f64, i64, i64)> {
        let (new_x, rem_x, block_x) =
            self.axis(x, y, half_x, half_y, delta_x, remainder_x, true, mask, ignore)?;
        let (new_y, rem_y, block_y) =
            self.axis(y, new_x, half_x, half_y, delta_y, remainder_y, false, mask, ignore)?;
        Some((new_x, new_y, rem_x, rem_y, block_x, block_y))
    }

    /// `TopDownSystem`'s whole movement step, for every body at once.
    ///
    /// One row per body: `(centre_x, centre_y, offset_x, offset_y, half_x,
    /// half_y, velocity_x, velocity_y, remainder_x, remainder_y, entity_id)`:
    /// the box's centre and the collider's offset exactly as
    /// `collider_bounds` gives them, and the half extents *before* the
    /// skin. The rest of the arithmetic `step_body` does in Python is done
    /// here in the same order on the same doubles, so each answer is the
    /// one it would have reached: the probe is the half extent less `skin`
    /// but never under 0.01, the move is `velocity * delta_time`, and the
    /// position handed back is the swept centre less the offset.
    ///
    /// The centre arrives already offset, rather than being added here,
    /// because without a collider `step_body` adds nothing at all -- and
    /// adding a zero offset is not nothing: `-0.0 + 0.0` is `+0.0`.
    ///
    /// Bodies are independent of one another here -- the mirror holds only
    /// static boxes, and nothing a sweep does changes it -- so one call for
    /// all of them gives what a call apiece in any order would.
    ///
    /// Returns, per row, `(x, y, remainder_x, remainder_y)`, or `None` when
    /// that body has to be stepped the slow way: a probe on its path was
    /// too close to call. Which box blocked it is not reported, because
    /// nothing in the step reads it -- a block is a block, whoever owns it.
    #[pyo3(signature = (rows, owners, delta_time, skin, mask))]
    fn step_bodies<'py>(
        &self,
        rows: Vec<StepRow<'py>>,
        owners: &Bound<'py, PyDict>,
        delta_time: f64,
        skin: f64,
        mask: u32,
    ) -> PyResult<Vec<Option<(f64, f64, f64, f64)>>> {
        let mut out = Vec::with_capacity(rows.len());
        for (x, y, offset_x, offset_y, half_x, half_y, velocity_x, velocity_y, rem_x, rem_y, id) in
            rows
        {
            let ignore = match owners.get_item(&id)? {
                Some(index) => index.extract::<i64>()?,
                None => CLEAR,
            };
            // Python's `max(h - SKIN, 0.01)`, spelled out: `f64::max` and
            // Python's `max` disagree about NaN.
            let probe_x = half_x - skin;
            let probe_x = if 0.01 > probe_x { 0.01 } else { probe_x };
            let probe_y = half_y - skin;
            let probe_y = if 0.01 > probe_y { 0.01 } else { probe_y };
            out.push(
                self.sweep(
                    x,
                    y,
                    probe_x,
                    probe_y,
                    velocity_x * delta_time,
                    velocity_y * delta_time,
                    rem_x,
                    rem_y,
                    mask,
                    ignore,
                )
                .map(|(new_x, new_y, new_rem_x, new_rem_y, _, _)| {
                    (new_x - offset_x, new_y - offset_y, new_rem_x, new_rem_y)
                }),
            );
        }
        Ok(out)
    }

    /// Whether a ray of the given radius certainly touches nothing.
    ///
    /// True only when the segment clears every box, grown by the radius
    /// and the margin, that the mask admits. False means "ask Chipmunk",
    /// never "it hits".
    fn segment_clear(
        &self,
        start_x: f64,
        start_y: f64,
        end_x: f64,
        end_y: f64,
        radius: f64,
        mask: u32,
    ) -> bool {
        if !(start_x.is_finite() && start_y.is_finite() && end_x.is_finite() && end_y.is_finite())
        {
            return false;
        }
        let grow = radius + MARGIN;
        let mut clear = true;
        self.candidates(
            start_x.min(end_x) - grow,
            start_y.min(end_y) - grow,
            start_x.max(end_x) + grow,
            start_y.max(end_y) + grow,
            |solid| {
                if solid.categories & mask == 0 || solid.mask == 0 {
                    return true;
                }
                if segment_meets_box(
                    start_x,
                    start_y,
                    end_x,
                    end_y,
                    solid.left - grow,
                    solid.bottom - grow,
                    solid.right + grow,
                    solid.top + grow,
                ) {
                    clear = false;
                    return false;
                }
                true
            },
        );
        clear
    }
}

/// Whether a segment might touch a rectangle. Errs towards "yes".
#[allow(clippy::too_many_arguments)]
fn segment_meets_box(
    start_x: f64,
    start_y: f64,
    end_x: f64,
    end_y: f64,
    left: f64,
    bottom: f64,
    right: f64,
    top: f64,
) -> bool {
    // Slab test over the segment's parameter in [0, 1].
    let mut enter = 0.0f64;
    let mut exit = 1.0f64;
    for (start, end, low, high) in [
        (start_x, end_x, left, right),
        (start_y, end_y, bottom, top),
    ] {
        let delta = end - start;
        if delta == 0.0 {
            if start < low || start > high {
                return false;
            }
            continue;
        }
        let mut near = (low - start) / delta;
        let mut far = (high - start) / delta;
        if near > far {
            std::mem::swap(&mut near, &mut far);
        }
        enter = enter.max(near);
        exit = exit.min(far);
    }
    // Slack on the comparison itself, on top of the grown rectangle, so a
    // rounding in the divisions above cannot turn a graze into a miss.
    enter <= exit + 1e-9
}
