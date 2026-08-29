# Dead-code disposition

Type: grilling
Status: resolved
Blocked by: —
Assignee: Wedeueis Braz
Audit ref: inventory

## Question

The audit found 8,956 LOC — about 28% of the engine — unreachable, unwired, or reachable only
from tests. The graphics portion is already decided (the GL track is being fixed and
supported, so `pipeline/`, `vfx/`, `materials/`, `lighting/` and `moderngl/` all stay). This
ticket rules on the seven remaining islands. One ticket rather than seven because each call is
small and they share a single question: what does a 0.5 library ship?

| Module | LOC | Status today |
|---|---|---|
| `replay/` | 1,070 | Not wired to `InputManager` or `Application`. Tests only. |
| `dev/` (hot reload) | 672 | No integration point in the application loop. |
| `ecs/archetype.py` | 311 | Zero references anywhere, including tests. |
| `error/` | 268 | Zero references anywhere, including tests. |
| `games/XXX_scenes/` | 243 | Placeholder-named orphan demo; not in the validation suite. |
| `ai/pathfinding/` | 159 | Unimportable — shadowed by `pathfinding.py`, no `__init__.py`. |
| `backends/headless_renderer.py` | 118 | Never registered; `validate_demos.py` uses SDL dummy. |

## To resolve

For each: delete, wire, or defer with an explicit note. Specific angles worth a view:

- `ai/pathfinding/` is a second, independent A* implementation that Python cannot import
  (`ModuleNotFoundError: 'pyguara.ai.pathfinding' is not a package`). Is anything in it better
  than what is in `pathfinding.py`, or is this a straight delete?
- `replay/` is the largest island and a genuine feature. Wiring it needs an `InputManager`
  recording hook — and `ReplayPlayer` reconstructing entities depends on ECS-5 (deepcopy)
  being fixed. Defer to its own effort, or wire here?
- `ecs/archetype.py` and `error/` have zero references including tests. Any reason not to
  delete outright?
- `headless_renderer.py` would make the integration suite faster and less SDL-dependent than
  the dummy driver. Wire it as the test backend rather than delete?
- `dev/` hot reload: does a pre-alpha engine carry it, and what is its integration point?

## Constraint

Carrying undecided code is what makes the codebase read as larger and more finished than it
is. "Defer" is a legitimate answer but must come with a note on the map, not silence.

## Why this is unblocked

The audit is sufficient input for the discussion. Implementing the answer wants a booting
engine (Repair the composition root, Bootstrap smoke test), but deciding it does not — so this
sits on the frontier and can run in parallel with the critical fixes.

## Answer

**`ai/pathfinding/` — finish and adopt it; clean break, not a delete.** Confirmed
`pyguara.ai.pathfinding` currently resolves to `pathfinding.py` (the concrete module wins
over the `__init__.py`-less directory), so `ai/__init__.py`'s public exports (`AStar`,
`GridMap`, `Heuristic`, `manhattan_distance`, `smooth_path`, `path_to_world_coords`,
`world_to_grid_coords`) all come from `pathfinding.py` today; the generic `Graph`/`Node`
`Protocol`-based package (`astar.py`, `core.py`, `grid.py`) is unreachable by any import path,
even internally. It's architecturally the better fit for this codebase (structural typing
over concrete types, matches the `Protocol`-over-`ABC` preference), and the concrete grid-only
version is exactly the kind of speculative parallel implementation worth finishing rather than
carrying both. Decision: delete `pathfinding.py`, add `ai/pathfinding/__init__.py` to make the
package real, add the two missing heuristics (`DiagonalDistance`/`OctileDistance` — `grid.py`
only has `Manhattan`/`Euclidean` today) and grid↔world/path-smoothing utilities
(`pathfinding.py` has `smooth_path`/`path_to_world_coords`/`world_to_grid_coords`; the generic
package has none), then rewrite `ai/__init__.py`'s exports and `tests/test_pathfinding.py`
against the generic `Graph[Node]`/`AStarPathfinder`/`GridGraph` shape. Clean break, no
compatibility facade — consistent with how ticket *Native Color and Rect value types* already
treated a pre-alpha public-API break. Dependency inversion is already correct on the two axes
that matter for "different 2D games": graph representation (`Graph[Node]`) and heuristic
(`Heuristic[Node]`) are both `Protocol`-typed and swappable; the algorithm itself
(`AStarPathfinder`) stays concrete — no `Pathfinder` Protocol, since there's exactly one
algorithm implementation anywhere in the codebase and introducing one now would abstract
against a hypothetical, not a real second caller. `ai/navmesh.py`'s separate
`NavMeshPathfinder` (polygon-adjacency A* + string-pulling funnel over `Vector2` paths)
explicitly stays out of scope — doesn't map cleanly onto `Graph[Node]` without a much bigger
refactor; fogged for later. Execution: see [Adopt the generic ai/pathfinding
package](17-adopt-generic-pathfinding-package.md).

**`replay/` — wire now.** Genuine, well-built feature (1,070 LOC implementation, 440 LOC of
its own tests) that's simply never connected to `InputManager`/`Application`. Checked: it
doesn't currently do entity reconstruction via `copy.deepcopy` (the audit's "depends on ECS-5"
note was about what wiring would need, not current behavior), so ticket *ECS lifecycle
contract*'s `Entity.clone()` is exactly the primitive real playback reconstruction should use.
Execution: see [Wire replay into InputManager and
Application](18-wire-replay-recording-playback.md).

**`dev/` hot reload — defer.** Fully implemented and tested in isolation
(`HotReloadManager`, `PollingFileWatcher`, a `StatefulSystem` Protocol), but no integration
point anywhere, and — unlike `replay/` — not a player-facing feature; it's a dev-experience
tool CLAUDE.md's documented workflow doesn't mention. Whether a pre-alpha engine carries live
code reload is a product-scope question deserving its own deliberate answer, not one bundled
into dead-code cleanup. Fogged.

**`ecs/archetype.py` — delete.** Zero references anywhere including tests. Its docstring
claims "cache-friendly contiguous arrays," but `component_arrays: Dict[Type[Component],
List[Component]]` is a Python list of object references, not packed memory — the cache-locality
payoff archetype storage delivers in Unity DOTS/Bevy/EnTT doesn't transfer to plain Python
objects, so this file doesn't actually deliver what it claims. Adopting real archetype storage
would also mean entities stop owning their own `_components` dict — a different foundational
model from what ticket *ECS lifecycle contract* already locked in (keeping and fixing
`QueryCache` over inverted indexes). Not "finish an unfinished feature" the way
`ai/pathfinding/` was — this would relitigate a decision made elsewhere on this map. Fogged: a
NumPy-backed columnar store (NumPy is already a core dependency, currently used only for
ModernGL vertex-buffer prep) applied selectively to hot, purely-numeric components — real
contiguous memory and vectorizable ops, opt-in per system rather than a wholesale ECS storage
rewrite — is the idea worth revisiting later, not this file as it stands.

**`error/` — delete.** Zero references anywhere including tests — `EngineException`/
`ErrorCategory`/`ErrorSeverity`/`safe_execute`/`retry`/`RetryPolicy` are never raised, applied,
or imported outside the package itself. (Confirmed this isn't secretly load-bearing via
`ErrorHandlingStrategy` — that's an unrelated enum defined separately in `events/types.py` and
`di/types.py`.) Fogged: if structured error-handling conventions are needed later, design them
against real call sites rather than resurrecting speculative, never-adopted infrastructure.

**`games/XXX_scenes/` — delete.** No fog note — unlike the other islands, no design idea is
being preserved here, just an orphaned, placeholder-named demo (243 LOC) never wired into
`validate_demos.py` or anything else.

**`backends/headless_renderer.py` (`HeadlessBackend`) — wire as the test backend.** Implements
the real `IRenderer` protocol but is never registered; the current headless test path
(`games/validate_demos.py`, the bootstrap smoke test) goes through real pygame with
`SDL_VIDEODRIVER=dummy`/`SDL_AUDIODRIVER=dummy` instead. Wiring it in makes the integration
suite faster and removes the SDL-dummy-driver dependency. Explicitly test infrastructure, not
a third shipped backend — doesn't touch the map's two-backend (pygame + ModernGL) parity
requirement. Execution: see [Wire HeadlessBackend as the integration-suite test
backend](19-wire-headless-test-backend.md).

**Mechanical deletions bundled into one ticket** — see [Delete confirmed dead
code](20-delete-confirmed-dead-code.md) for `ecs/archetype.py`, `error/`, and
`games/XXX_scenes/`.
