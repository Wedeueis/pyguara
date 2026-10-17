//! A grid flow field that is computed natively and stays native.
//!
//! The first native port of something that is not a cosmetic pool, and the
//! strongest candidate in the engine by a wide margin: a 96x96 recompute
//! measures **89 ms in Python**, which is 536% of a 16.7 ms frame. That is
//! less an optimisation target than a feature that cannot be used at
//! interactive rates -- a goal moving one cell drops five frames.
//!
//! The boundary is the *service*, not `dijkstra_map`. Porting the sweep
//! alone would mean handing a `dict[Cell, float]` of 8000 entries back to
//! Python so the descent pass could run there, and the descent pass is
//! itself 41% of the cost (36.9 ms of the 89.4). So the cost map and the
//! field both live here, and nothing crosses but the query -- which is
//! what `docs/adr/0004-the-native-boundary.md` calls opacity, and why this
//! port is cheap where flocking's is not.
//!
//! **This is bit-exact with the Python implementation, not merely close**,
//! and that is a requirement rather than a bonus: the field steers
//! gameplay, so a cell whose descent neighbour differs is an enemy that
//! walks the other way round a wall. Three things make exactness
//! reachable here where the float pools settled for a tolerance:
//!
//! 1. `GridGraph.get_neighbors`' order is replicated exactly, including
//!    its refusal to cut a solid corner. The descent pass takes the
//!    *first* strictly-cheaper neighbour, so the order is the tie-break.
//! 2. The frontier carries the same `(cost, insertion)` total order as
//!    `heapq` with `dijkstra_map`'s counter, so the pop sequence is
//!    identical rather than merely equivalent.
//! 3. A Dijkstra cost map is in fact order-*independent* given
//!    non-negative weights: a node is popped with its final cost, so every
//!    node's value is `min` over its predecessors of a sum computed the
//!    same way here as there. Point 2 therefore makes the sequence
//!    identical and point 3 makes the result identical even where it is
//!    not -- which is what lets the parity test assert `==` on 9216 cells
//!    instead of a tolerance.

use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Neighbour offsets, in `pyguara.common.grid._NEIGHBORS_8` order.
///
/// The order is load-bearing: `flow_field` keeps the first neighbour that
/// is strictly cheaper than the running best, so two equal-cost neighbours
/// are decided by which comes first here. The orthogonal four lead, which
/// is also what `_NEIGHBORS_4` is a prefix of.
const NEIGHBORS: [(i32, i32); 8] = [
    (1, 0),
    (0, 1),
    (-1, 0),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
];

/// The diagonal step cost, as `GridGraph.cost` spells it.
///
/// Deliberately `1.414` and not `SQRT_2`: the Python it has to agree with
/// uses the rounded constant, and "more accurate" here would mean
/// "different field".
const DIAGONAL: f64 = 1.414;

/// The largest grid this will configure, in cells.
///
/// A bound rather than a `checked_mul`, so a plausible typo
/// (`GridGraph(1 << 20, 1 << 20)`) fails with a message instead of asking
/// the allocator for 8 TB.
const MAX_CELLS: i64 = 1 << 26;

/// One frontier entry, ordered cheapest-first then oldest-first.
struct Visit {
    cost: f64,
    insertion: u64,
    node: (i32, i32),
}

impl PartialEq for Visit {
    fn eq(&self, other: &Self) -> bool {
        self.insertion == other.insertion
    }
}

impl Eq for Visit {}

impl Ord for Visit {
    /// Reversed, because `BinaryHeap` is a max-heap and Dijkstra wants the
    /// cheapest. `insertion` is unique, so this is a total order and the
    /// `unwrap_or` is unreachable for the finite costs the sweep produces.
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .cost
            .partial_cmp(&self.cost)
            .unwrap_or(Ordering::Equal)
            .then_with(|| other.insertion.cmp(&self.insertion))
    }
}

impl PartialOrd for Visit {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// A `GridGraph`'s cost map and descent field, held natively.
#[pyclass]
pub struct NativeFlowField {
    width: i32,
    height: i32,
    allow_diagonal: bool,
    /// `GridGraph.walls`, as one byte per in-bounds cell.
    blocked: Vec<bool>,
    /// `GridGraph.weights`, defaulted to 1.0 per cell.
    weights: Vec<f64>,
    /// Cost to the nearest goal, meaningful only where `reached`.
    cost: Vec<f64>,
    /// Whether the cell is in the cost map at all -- `dijkstra_map`
    /// returning a `dict` makes "unreached" and "reached at infinity"
    /// distinguishable, and an infinite terrain weight makes the
    /// difference reachable, so it is tracked rather than inferred.
    reached: Vec<bool>,
    /// The descent neighbour's flat index, or -1 for none.
    next: Vec<i32>,
    /// Costs for goals outside the grid.
    ///
    /// `dijkstra_map` seeds every goal at cost 0 without asking whether it
    /// is on the grid, so a goal off the edge -- which happens the moment a
    /// quarry leaves the level -- really is in the cost map and really does
    /// expand into its in-bounds neighbours. A flat array cannot hold it,
    /// and dropping it would change the costs of the cells next to it, so
    /// the handful of them live here.
    outside: HashMap<(i32, i32), f64>,
}

impl NativeFlowField {
    #[inline]
    fn in_bounds(&self, x: i32, y: i32) -> bool {
        x >= 0 && x < self.width && y >= 0 && y < self.height
    }

    #[inline]
    fn index(&self, x: i32, y: i32) -> usize {
        (y as i64 * self.width as i64 + x as i64) as usize
    }

    /// `GridGraph._is_walkable`: on the grid and not a wall.
    #[inline]
    fn walkable(&self, x: i32, y: i32) -> bool {
        self.in_bounds(x, y) && !self.blocked[self.index(x, y)]
    }

    /// `GridGraph.get_neighbors`, in order, into `out`.
    ///
    /// `(x, y)` may be off the grid: an out-of-bounds goal is expanded the
    /// same way, and the corner rule treats an off-grid flanking cell as
    /// solid exactly as `_is_walkable` does.
    fn neighbors(&self, x: i32, y: i32, out: &mut Vec<(i32, i32)>) {
        out.clear();
        let candidates = if self.allow_diagonal {
            &NEIGHBORS[..]
        } else {
            &NEIGHBORS[..4]
        };
        for &(dx, dy) in candidates {
            let (nx, ny) = (x + dx, y + dy);
            if !self.walkable(nx, ny) {
                continue;
            }
            if dx.abs() == 1
                && dy.abs() == 1
                && (!self.walkable(x + dx, y) || !self.walkable(x, y + dy))
            {
                continue;
            }
            out.push((nx, ny));
        }
    }

    /// `GridGraph.cost`. `to` is always on the grid.
    #[inline]
    fn step_cost(&self, from: (i32, i32), to: (i32, i32)) -> f64 {
        let base = self.weights[self.index(to.0, to.1)];
        let dx = (from.0 - to.0).abs();
        let dy = (from.1 - to.1).abs();
        base * if dx + dy == 2 { DIAGONAL } else { 1.0 }
    }

    /// Cost of a node that may be off the grid, and whether it is known.
    #[inline]
    fn known_cost(&self, node: (i32, i32)) -> Option<f64> {
        if self.in_bounds(node.0, node.1) {
            let i = self.index(node.0, node.1);
            if self.reached[i] { Some(self.cost[i]) } else { None }
        } else {
            self.outside.get(&node).copied()
        }
    }

    /// `dijkstra_map`, then `flow_field`, over the configured grid.
    fn sweep(&mut self, goals: &[(i32, i32)], max_cost: Option<f64>) {
        self.cost.iter_mut().for_each(|c| *c = f64::INFINITY);
        self.reached.iter_mut().for_each(|r| *r = false);
        self.next.iter_mut().for_each(|n| *n = -1);
        self.outside.clear();

        let mut frontier: BinaryHeap<Visit> = BinaryHeap::new();
        let mut insertion: u64 = 0;
        for &goal in goals {
            if self.in_bounds(goal.0, goal.1) {
                let i = self.index(goal.0, goal.1);
                self.cost[i] = 0.0;
                self.reached[i] = true;
            } else {
                self.outside.insert(goal, 0.0);
            }
            frontier.push(Visit {
                cost: 0.0,
                insertion,
                node: goal,
            });
            insertion += 1;
        }

        let mut out: Vec<(i32, i32)> = Vec::with_capacity(8);
        while let Some(visit) = frontier.pop() {
            match self.known_cost(visit.node) {
                // `if cost > cost_so_far[current]: continue` -- a stale
                // entry left behind by a cheaper route.
                Some(known) if visit.cost > known => continue,
                Some(_) => {}
                // Unreachable: nothing is pushed without being recorded.
                None => continue,
            }
            self.neighbors(visit.node.0, visit.node.1, &mut out);
            for &neighbor in &out {
                let new_cost = visit.cost + self.step_cost(visit.node, neighbor);
                if let Some(limit) = max_cost {
                    if new_cost > limit {
                        continue;
                    }
                }
                let i = self.index(neighbor.0, neighbor.1);
                if self.reached[i] && new_cost >= self.cost[i] {
                    continue;
                }
                self.cost[i] = new_cost;
                self.reached[i] = true;
                frontier.push(Visit {
                    cost: new_cost,
                    insertion,
                    node: neighbor,
                });
                insertion += 1;
            }
        }

        // `flow_field`: the steepest-descent neighbour of every reached
        // cell, first-cheapest-wins so the neighbour order decides a tie.
        for y in 0..self.height {
            for x in 0..self.width {
                let i = self.index(x, y);
                if !self.reached[i] {
                    continue;
                }
                let mut best = self.cost[i];
                let mut chosen: i32 = -1;
                self.neighbors(x, y, &mut out);
                for &neighbor in &out {
                    let j = self.index(neighbor.0, neighbor.1);
                    if self.reached[j] && self.cost[j] < best {
                        best = self.cost[j];
                        chosen = j as i32;
                    }
                }
                self.next[i] = chosen;
            }
        }
    }
}

#[pymethods]
impl NativeFlowField {
    /// Create an unconfigured field; `set_grid` has to be called first.
    #[new]
    fn new() -> Self {
        Self {
            width: 0,
            height: 0,
            allow_diagonal: true,
            blocked: Vec::new(),
            weights: Vec::new(),
            cost: Vec::new(),
            reached: Vec::new(),
            next: Vec::new(),
            outside: HashMap::new(),
        }
    }

    /// Upload the graph: dimensions, the wall mask and the terrain weights.
    ///
    /// Takes the dimensions on every call rather than at construction, so
    /// a `GridGraph` that is resized at runtime is a re-upload rather than
    /// a rebuilt object. Measured at 0.08 ms for 96x96, against 89 ms for
    /// the recompute it precedes, so there is no reason to be clever about
    /// it -- but `FlowFieldService` skips it anyway when its fingerprint
    /// says the graph has not changed, because then it also skips the
    /// recompute.
    ///
    /// Args:
    ///     width: Grid width in cells.
    ///     height: Grid height in cells.
    ///     allow_diagonal: Whether the eight-neighbourhood is used.
    ///     blocked: One flag per cell, row-major, true for a wall.
    ///     weights: One terrain multiplier per cell, row-major, 1.0 for
    ///         ordinary ground.
    ///
    /// Raises:
    ///     ValueError: If the dimensions are negative or implausibly large,
    ///         or either array is not exactly `width * height` long.
    fn set_grid(
        &mut self,
        width: i32,
        height: i32,
        allow_diagonal: bool,
        blocked: Vec<bool>,
        weights: Vec<f64>,
    ) -> PyResult<()> {
        if width < 0 || height < 0 {
            return Err(PyValueError::new_err(format!(
                "grid dimensions must not be negative, got {width}x{height}"
            )));
        }
        let cells = width as i64 * height as i64;
        if cells > MAX_CELLS {
            return Err(PyValueError::new_err(format!(
                "{width}x{height} is {cells} cells, over the {MAX_CELLS} limit"
            )));
        }
        let cells = cells as usize;
        if blocked.len() != cells || weights.len() != cells {
            return Err(PyValueError::new_err(format!(
                "a {width}x{height} grid needs {cells} flags and {cells} \
                 weights, got {} and {}",
                blocked.len(),
                weights.len()
            )));
        }

        self.width = width;
        self.height = height;
        self.allow_diagonal = allow_diagonal;
        self.blocked = blocked;
        self.weights = weights;
        self.cost = vec![f64::INFINITY; cells];
        self.reached = vec![false; cells];
        self.next = vec![-1; cells];
        self.outside.clear();
        Ok(())
    }

    /// Recompute the cost map and the descent field toward `goals`.
    ///
    /// The one expensive crossing, and the GIL is released for all of it:
    /// the sweep touches nothing Python-owned once the goals are copied in.
    ///
    /// Args:
    ///     goals: Target cells, each seeded at cost 0. May be off the
    ///         grid, which `dijkstra_map` also permits.
    ///     max_cost: Stop expanding past this cost, if given.
    ///
    /// Returns:
    ///     How many nodes the cost map holds, off-grid goals included --
    ///     the length of `dijkstra_map`'s dict, which is what
    ///     `FlowFieldService.is_computed` is really asking about.
    #[pyo3(signature = (goals, max_cost=None))]
    fn recompute(
        &mut self,
        py: Python<'_>,
        goals: Vec<(i32, i32)>,
        max_cost: Option<f64>,
    ) -> usize {
        py.detach(|| {
            self.sweep(&goals, max_cost);
            self.reached.iter().filter(|r| **r).count() + self.outside.len()
        })
    }

    /// Return the normalised step direction out of cell `(x, y)`.
    ///
    /// The whole of `FlowFieldService.vector_at` after the world-to-cell
    /// conversion, which is why it takes `cell_size` and `offset` rather
    /// than returning a neighbour for Python to subtract: the Python
    /// version spends 3.18 us per call and only ~0.1 us of that is the
    /// field lookup -- the rest is four `Vector2` operations. Done here it
    /// is 0.7 us including the crossing.
    ///
    /// The arithmetic is deliberately the long way round -- both cell
    /// centres in world space, then subtract -- rather than the algebraically
    /// equal `(nx - x) * cell_size`, because the two are not equal in
    /// floating point for every `cell_size` and `offset`, and this has to
    /// match what Python produced.
    ///
    /// Args:
    ///     x: Cell x, from `pyguara.common.grid.world_to_cell`.
    ///     y: Cell y.
    ///     cell_size: World units per cell.
    ///     offset_x: World x of the grid origin.
    ///     offset_y: World y of the grid origin.
    ///
    /// Returns:
    ///     A unit vector toward the next cell, or `(0.0, 0.0)` where the
    ///     cell is off the grid, unreached, or a goal.
    fn direction_at(
        &self,
        x: i32,
        y: i32,
        cell_size: f64,
        offset_x: f64,
        offset_y: f64,
    ) -> (f64, f64) {
        if !self.in_bounds(x, y) {
            return (0.0, 0.0);
        }
        let chosen = self.next[self.index(x, y)];
        if chosen < 0 {
            return (0.0, 0.0);
        }
        let next_x = chosen % self.width;
        let next_y = chosen / self.width;
        let half = cell_size / 2.0;
        let dx = (f64::from(next_x) * cell_size + half + offset_x)
            - (f64::from(x) * cell_size + half + offset_x);
        let dy = (f64::from(next_y) * cell_size + half + offset_y)
            - (f64::from(y) * cell_size + half + offset_y);
        let length = (dx * dx + dy * dy).sqrt();
        if length < 0.001 {
            return (0.0, 0.0);
        }
        (dx / length, dy / length)
    }

    /// Return `(x, y)`'s descent neighbour, or None.
    ///
    /// Not on any hot path -- `direction_at` is what a steering agent
    /// calls. This exists for the parity tests, which compare the field
    /// cell by cell against `flow_field`'s dict.
    fn next_cell(&self, x: i32, y: i32) -> Option<(i32, i32)> {
        if !self.in_bounds(x, y) {
            return None;
        }
        let chosen = self.next[self.index(x, y)];
        if chosen < 0 {
            return None;
        }
        Some((chosen % self.width, chosen / self.width))
    }

    /// Return `(x, y)`'s cost to the nearest goal, or infinity.
    ///
    /// Infinity for a cell the sweep did not reach, matching
    /// `dict.get(cell, math.inf)`.
    fn cost_at(&self, x: i32, y: i32) -> f64 {
        match self.known_cost((x, y)) {
            Some(cost) => cost,
            None => f64::INFINITY,
        }
    }

    /// Whether the last `recompute` reached `(x, y)` at all.
    ///
    /// Distinct from a finite `cost_at`, for the same reason `reached` is a
    /// separate array: an infinite terrain weight puts a cell in the cost
    /// map at infinity.
    fn is_reached(&self, x: i32, y: i32) -> bool {
        self.known_cost((x, y)).is_some()
    }
}
