# Dead-code disposition

Type: grilling
Status: open
Blocked by: —
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
