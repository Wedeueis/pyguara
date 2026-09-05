# Execute the diagonal corner-cutting fix

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: fog graduation, follows from Decide whether GridGraph should prevent diagonal
corner-cutting, ticket 28

## Question

Nothing to decide — execute the decision recorded in [Decide whether GridGraph should
prevent diagonal corner-cutting](28-diagonal-corner-cutting-decision.md).

**`pyguara/ai/pathfinding/grid.py`:**
- `GridGraph.get_neighbors()`: for each diagonal direction `(dx, dy)` (both `abs(dx) ==
  1` and `abs(dy) == 1`), before yielding the diagonal destination, check both flanking
  orthogonal cells `(x + dx, y)` and `(x, y + dy)`. Skip the diagonal move (do not
  yield) unless *both* flanking cells are `in_bounds()` and `is_passable()` — an
  out-of-bounds flanking cell blocks the diagonal, matching the deleted `GridMap`'s
  `is_walkable()` semantics exactly.
- No new flag. This check always applies when `allow_diagonal=True`.

## Done when

- A diagonal move is refused when either flanking orthogonal cell is a wall (both
  interior-wall and grid-edge cases), verified by porting the old suite's
  `test_diagonal_corner_cutting_prevention` case (previously dropped during ticket 17
  since no equivalent behavior existed to assert) into `tests/test_pathfinding.py`.
- A regression test for the edge-of-grid case: a diagonal move along the grid boundary
  is refused when the flanking cell it would graze falls outside the grid.
- Existing diagonal-movement tests (moves through open corners) still pass unchanged.
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

## Resolution

Executed exactly as specified. Commit `0d61b1c`.

`GridGraph.get_neighbors()` gained a `_is_walkable()` helper (`in_bounds() and
is_passable()`, mirroring the deleted `GridMap.is_walkable()`'s combined semantics) and
a corner-cutting check: for each diagonal direction, both flanking orthogonal cells
must be walkable or the diagonal is skipped. No new flag -- always applies when
`allow_diagonal=True`, per the decision.

Four new tests in `tests/test_pathfinding.py`: a wall on one flank blocks the diagonal
even though the destination itself is open (the case ticket 17 originally dropped);
either flank alone is sufficient to block, not just both together; an out-of-bounds
flank at the grid edge blocks the diagonal too (the edge case resolved via git history
during the grilling session); and a fully open corner stays unaffected (no regression
on the common case). All 40 pre-existing pathfinding tests pass unchanged -- traced
each one that uses walls or diagonals (`test_path_around_obstacle`,
`test_complex_maze`, `test_get_neighbors_corner`, `test_diagonal_path`) and confirmed
none has a wall directly flanking a diagonal move its expected path depends on.

Full suite green (1120 passed, up from 1116 -- the 4 new tests). `ruff check .`,
`ruff format --check`, and `mypy pyguara` (217 files) all clean. No deviations.
