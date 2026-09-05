# Decide whether GridGraph should prevent diagonal corner-cutting

Type: grilling
Status: open
Blocked by: —
Audit ref: fog graduation, found while executing Adopt the generic ai/pathfinding package
(ticket 17)

## Question

The deleted concrete `pathfinding.py`'s `GridMap.get_neighbors()` refused a diagonal move
when either of the two adjacent orthogonal cells was a wall/obstacle — the standard
"no cutting through a solid corner" rule. The generic `GridGraph.get_neighbors()`
(`pyguara/ai/pathfinding/grid.py`) that ticket 17 adopted as the real implementation does
**not** reproduce this: it allows a diagonal move as long as the diagonal destination cell
itself is open, regardless of the two flanking cells. This is a genuine behavior
regression versus the module being replaced, discovered while porting
`tests/test_pathfinding.py` (the old suite's `test_diagonal_corner_cutting_prevention` had
no equivalent ported, since asserting it would have meant inventing behavior that doesn't
exist in the new engine).

Not fixed on the spot in ticket 17 because — unlike that ticket's printf-arg fix, which
was a load-bearing crash preventer — this is a silent behavior/feel choice affecting every
future consumer of `GridGraph` (games, `NavMeshPathfinder`'s eventual unification, editor
tooling), not a correctness bug that blocks anything from working.

- Should `GridGraph.get_neighbors()` reject a diagonal move when either flanking
  orthogonal cell is a wall, matching the old `GridMap`'s behavior?
- If yes: does this belong as `GridGraph`'s only behavior, or as an opt-in flag (some
  games may want permissive diagonal movement through corners)?
- Any consumer, if one already exists, whose current pathing depends on the permissive
  behavior (grep before deciding)?
