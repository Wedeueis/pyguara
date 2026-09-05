# Execute the diagonal corner-cutting fix

Type: task
Status: open
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
