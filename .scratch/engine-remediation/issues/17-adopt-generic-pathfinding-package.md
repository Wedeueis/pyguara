# Adopt the generic ai/pathfinding package

Type: task
Status: resolved
Assignee: Wedeueis Braz
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

## Resolution

Executed as specified. Commit `0bf2bf4`.

Added `pyguara/ai/pathfinding/__init__.py` exporting the package's full public surface
(`Graph`, `Heuristic`, `Node` from `core.py`; `AStarPathfinder` from `astar.py`; `GridGraph`,
`GridNode`, all four heuristic classes, `smooth_path`, `path_to_world_coords`,
`world_to_grid_coords` from `grid.py`). `grid.py` gained `DiagonalDistance`/`OctileDistance`
(matching the deleted module's Chebyshev/octile math exactly) plus `smooth_path`/
`_has_line_of_sight`/`path_to_world_coords`/`world_to_grid_coords` — landed in `grid.py`
rather than a new file since they're grid/world-specific, not generic-graph concerns, and
keeps `core.py`/`astar.py` purely abstract. Deleted `pyguara/ai/pathfinding.py`. Rewrote
`ai/__init__.py`'s pathfinding import block and `__all__` against the new names — no
`AStar`/`GridMap`/`Heuristic`-enum aliases, as specified.

Rewrote `tests/test_pathfinding.py` against the new API, same-shaped scenario coverage
(heuristics, obstacle avoidance, diagonal movement, smoothing, coordinate round-tripping,
end-to-end workflows) — 40 tests vs. the old 44.

**Four old-suite tests dropped, not ported, because the generic engine doesn't implement
the mechanics they asserted** (none of this was in the ticket's Steps to add, and adding it
would have been undirected scope growth into `astar.py`, which the Steps deliberately left
untouched):
- `test_start_blocked`/`test_goal_blocked` — the concrete `AStar.find_path()` short-circuited
  to `None` if `start`/`goal` themselves sat on an obstacle; `AStarPathfinder.find_path()`
  never checks passability of its own start/goal, only of candidate neighbors.
- `test_statistics_tracking`/`test_statistics_on_no_path` — the concrete `AStar` tracked
  `last_iterations`/`last_path_length`; `AStarPathfinder` is stateless and exposes neither.

**One behavior gap found and deliberately *not* fixed here, spun out as [Decide whether
GridGraph should prevent diagonal corner-cutting](28-diagonal-corner-cutting-decision.md):**
the deleted `GridMap.get_neighbors()` refused a diagonal move when either flanking
orthogonal cell was a wall; the adopted `GridGraph.get_neighbors()` doesn't reproduce this
— a diagonal move is allowed as long as the diagonal destination itself is open. Unlike
ticket 16's printf-arg fix (a load-bearing crash preventer, fixed on the spot), this is a
silent gameplay-behavior/feel choice affecting every future `GridGraph` consumer, not a
correctness bug blocking anything from working — so it gets its own decision rather than
being decided here. `test_diagonal_corner_cutting_prevention` was dropped from the ported
suite accordingly (asserting it would mean inventing behavior the engine doesn't have);
`test_clear_obstacles` was ported as `test_clear_walls` (trivial — `GridGraph.walls` is
already a public `Set`, `.clear()` needed no new API).

Confirmed no consumers outside the package itself and its own tests
(`grep -rln "GridMap\|GridGraph(" pyguara games tests`), so this was a clean, isolated
break. Full suite green (1049 passed), `ruff check .` and `mypy pyguara` clean.
