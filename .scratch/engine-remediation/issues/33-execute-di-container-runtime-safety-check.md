# Execute the DIContainer runtime safety check

Type: task
Status: open
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
