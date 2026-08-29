# Adopt the generic ai/pathfinding package

Type: task
Status: open
Blocked by: —
Audit ref: follows from Dead-code disposition, ticket 09

## Question

Nothing to decide — execute the decision recorded in [Dead-code
disposition](09-dead-code-disposition.md): `pyguara.ai.pathfinding` currently resolves to
`pathfinding.py` (concrete, grid-only) because `ai/pathfinding/` has no `__init__.py` and a
regular module always wins over a namespace-package directory. The generic `Protocol`-based
package (`ai/pathfinding/{core,astar,grid}.py`) is unreachable by any import path. Make it the
real implementation; delete the concrete one. Clean break — no compatibility shim.

## Steps

1. Add `pyguara/ai/pathfinding/__init__.py` exporting the package's public surface
   (`Graph`, `Node`, `Heuristic` protocols from `core.py`; `AStarPathfinder` from `astar.py`;
   `GridGraph` and its heuristic classes from `grid.py`).
2. Add the two missing heuristic classes to `grid.py` for feature parity with the concrete
   module: `DiagonalDistance` (Chebyshev — `max(|dx|, |dy|)`) and `OctileDistance`
   (`(dx + dy) + (sqrt(2) - 2) * min(dx, dy)`), matching `pathfinding.py`'s
   `diagonal_distance`/`octile_distance` semantics.
3. Add grid↔world coordinate conversion and path smoothing to the generic package (currently
   only in `pathfinding.py`, with no equivalent in `ai/pathfinding/`): `path_to_world_coords`,
   `world_to_grid_coords`, `smooth_path` (line-of-sight waypoint reduction over a `GridGraph`,
   port `_has_line_of_sight`'s Bresenham check to operate against `GridGraph.is_passable`).
4. Delete `pyguara/ai/pathfinding.py`.
5. Rewrite `pyguara/ai/__init__.py`'s pathfinding import block and `__all__` entries against
   the new package's names (`AStarPathfinder`, `GridGraph`, `ManhattanDistance`,
   `EuclideanDistance`, `DiagonalDistance`, `OctileDistance`, plus the smoothing/conversion
   functions) — this is a breaking public-API change, no `AStar`/`GridMap`/`Heuristic` (enum)
   compatibility aliases.
6. Rewrite `tests/test_pathfinding.py` against the new API — same scenarios (path found,
   obstacles avoided, diagonal movement, each heuristic, smoothing), same coverage.

## Done when

- `pyguara.ai.pathfinding.astar`, `.core`, `.grid` are all importable.
- `pyguara/ai/pathfinding.py` is deleted.
- `ai/__init__.py`'s public exports and `tests/test_pathfinding.py` are on the generic API;
  full parity with the old concrete module's behavior (all four heuristics, smoothing,
  grid↔world conversion) covered by tests.
- `grep -rn "GridMap\|Heuristic\.MANHATTAN" pyguara tests` (the old concrete-module names)
  returns nothing.
- Full suite green, `ruff check .` and `mypy pyguara` clean.
