# Decide whether GridGraph should prevent diagonal corner-cutting

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
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

## Answer

Grilled live with the dev, one sub-question at a time. Usage check first: grepped for
`GridGraph` across `pyguara/` and `games/` — only the pathfinding package itself
references it (`ai/__init__.py`'s re-export, `ai/pathfinding/__init__.py`, `grid.py`
itself). No current consumer depends on the permissive behavior. Decisions:

1. **Prevent corner-cutting: yes.** `GridGraph.get_neighbors()` refuses a diagonal move
   when either flanking orthogonal cell is a wall, matching the deleted `GridMap`. It's
   the standard rule for tile-based pathfinding precisely because the alternative reads
   as a visible bug (an agent's sprite clipping a wall's corner mid-move), the old engine
   code already enforced it, and there's no compatibility cost since nothing consumes the
   permissive behavior today.
2. **Unconditional — no separate opt-in flag.** Enforced whenever `allow_diagonal=True`,
   not gated by a new `allow_corner_cutting` flag. Corner-safety is what "diagonal
   movement" means in essentially every tile-based game that supports it; the permissive
   variant is a niche exception not worth defaulting to or speculatively flagging when no
   consumer wants it. A flag can be added later, backward-compatibly, if a real
   motivated use case shows up.
3. **Edge case, found not decided:** checked the deleted `GridMap`'s actual behavior via
   git history (`git show <pre-deletion commit>^:pyguara/ai/pathfinding.py`) rather than
   asking, since it's a fact about existing behavior, not a fresh design choice. The old
   `is_walkable()` combined bounds-checking and obstacle-checking into one predicate, and
   the old corner-check called it on both flanking cells — so an out-of-bounds flanking
   cell was treated as *blocking*, refusing a diagonal move along the grid's edge if the
   flank it would graze falls outside the map. `GridGraph`'s new check reproduces this
   exactly: a flanking cell must be both `in_bounds()` and `is_passable()` (i.e., not
   `is_walkable()`-equivalent) to permit the diagonal, not `is_passable()` alone.

Lands as one execution ticket — see [Execute the diagonal corner-cutting
fix](32-execute-diagonal-corner-cutting-fix.md).
