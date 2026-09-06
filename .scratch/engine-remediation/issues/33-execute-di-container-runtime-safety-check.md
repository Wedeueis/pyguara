# Execute the DIContainer runtime safety check

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: fog graduation, follows from Decide whether to harden DIContainer's generic
signatures, ticket 30

## Question

Nothing to decide — execute the decision recorded in [Decide whether to harden
DIContainer's generic signatures](30-di-container-generic-safety-decision.md).

**Mark 10 protocols `@runtime_checkable`:**
- `IRenderer`, `IWindowBackend`, `UIRenderer`, `TextureFactory`
  (`pyguara/graphics/protocols.py`)
- `IPhysicsBody`, `IPhysicsEngine` (`pyguara/physics/protocols.py`)
- `IAudioSystem` (`pyguara/audio/audio_system.py`)
- `StorageBackend` (`pyguara/persistence/types.py`)
- `Graph`, `Heuristic` (`pyguara/ai/pathfinding/core.py`)

**`pyguara/di/container.py`:**
- `register_instance(interface, instance)`: after the existing arg validation, assert
  `isinstance(instance, interface)`. On failure, raise `DIException` naming both
  `interface.__name__` and `type(instance).__name__`.
- `register_singleton`/`register_transient`/`register_scoped` are **not** touched --
  the decision scoped the check to `register_instance()` only (see the ticket's Answer
  for why `issubclass()` doesn't generalize safely to the class-based methods).

## Done when

- All 10 protocols carry `@runtime_checkable`.
- `register_instance(IFoo, WrongType())` raises `DIException` (not a silent pass,
  not a `TypeError` from `isinstance()` itself) for a `WrongType` missing a required
  method, verified by a regression test.
- `register_instance(IFoo, CorrectImpl())` still succeeds, verified by a regression
  test (no false positives).
- Existing `register_instance()` calls across `bootstrap.py` and all 9
  `games/*/bootstrap.py` still succeed unchanged -- every one of them is either a
  concrete class or an already-`@runtime_checkable` protocol, confirmed during the
  grilling session, but verify empirically anyway (full suite + `games/validate_demos.py`).
- `register_singleton`/`register_transient`/`register_scoped` are unchanged.
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

## Resolution

Executed as specified, with one necessary scope correction found via the full suite,
not anticipated during grilling. Commit `361ac14`.

All 10 protocols marked `@runtime_checkable` exactly as named. `register_instance()`
gained the `isinstance()` assert, raising the existing `DIException`.

**Scope correction: the check only fires when `interface` is itself a Protocol**
(`getattr(interface, "_is_protocol", False)`), not for every `register_instance()` call
as originally implemented. Running the full suite after an unconditional `isinstance()`
check immediately broke `bootstrap.py`'s `register_instance(RenderGraph,
pygame_render_graph)` — `RenderGraph` is a concrete class, not a Protocol, and
`PygameRenderGraph` *deliberately* does not subclass it (BOOT-1's fix, ticket 02:
`Application` branches on `isinstance(candidate, RenderGraph)` specifically so the
Pygame stub is resolvable but not treated as a real one). The grilling session's
"verified this covers 100% of current risk" check had confirmed every `register_
instance()` interface was either a protocol or a concrete class, but assumed "concrete
class → isinstance() always works" without checking that every concrete-class
registration's instance is actually a real subclass — false for this one deliberate
exception. Restricting the check to Protocol interfaces only was the correct fix
(matches the decision's actual intent — it was never about nominal concrete-class
matching) rather than special-casing `RenderGraph`.

**Also found via the full suite, not anticipated:** three pre-existing test fixtures in
`tests/integration/test_app_flow.py` registered bare `MagicMock()` (no `spec=`) against
`UIRenderer`/`IRenderer`/`IAudioSystem`. A bare `MagicMock` turns out to *fail*
`isinstance()` against a `@runtime_checkable` protocol despite `hasattr()` succeeding
for every individual method (confirmed empirically) — Python's protocol runtime check
apparently doesn't rely on simple `hasattr()`. Fixed by adding `spec=<protocol>` to
those three mocks, which correctly makes them satisfy `isinstance()` — a natural
improvement to test fidelity (the mocks now genuinely resemble what they stand in for),
not a workaround.

Three new tests in `tests/test_di.py`: a structurally-mismatched instance raises
`DIException`; a real match still registers and resolves (no false positive); a
concrete-class interface is never isinstance-checked, reproducing the `RenderGraph`
scenario directly (a nominally-unrelated instance registers and resolves without
error). Full suite green (1123 passed, up from 1120 -- the 3 new tests), all 4 demos
verified booting clean via `games/validate_demos.py`. `ruff check .`, `ruff format
--check`, and `mypy pyguara` (217 files) all clean.
