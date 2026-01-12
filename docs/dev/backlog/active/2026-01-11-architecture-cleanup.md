# Implementation Plan: Architecture Cleanup (P2-013)

## 1. Context & Motivation
The architectural review identified several inconsistencies and legacy patterns that need addressing to ensure a stable, scalable foundation. Key issues include inconsistent ECS query patterns ("Push" vs "Pull"), hardcoded hardware dependencies preventing testing, and minor type-safety gaps.

## 2. Goals
- **Standardize ECS Pattern:** Move all Systems to a "Pull" architecture (System queries Manager) for consistency.
- **Abstract Input Backend:** Decouple `pygame` from `InputManager` to allow headless testing.
- **Harden Type Safety:** Remove reliance on `__getattr__` magic in components.
- **Improve Error Handling:** Ensure resource loading failures are explicit and robust.

## 3. Implementation Tasks

### Task A: ECS Pattern Standardization (PhysicsSystem)
**Current State:** `PhysicsSystem.update(entities, dt)` follows a "Push" pattern (Pure System), requiring the caller to query entities. This creates a critical architectural conflict with `SystemManager`, which expects a uniform `update(dt)` interface (Self-Sufficient System) for orchestration. Currently, `PhysicsSystem` cannot be managed by `SystemManager` without a wrapper or manual orchestration in the Scene.
**Target State:** "Pull" pattern (Self-Sufficient System) for all Systems by injecting dependencies.

1.  **Refactor `PhysicsSystem.__init__` (Dependency Injection)**:
    -   Inject `entity_manager: EntityManager` into the constructor.
    -   Store `self._entity_manager` for internal querying.
    -   *Rationale:* This enables the system to be self-contained and managed generically by `SystemManager`.
2.  **Refactor `PhysicsSystem.update`**:
    -   Change signature to `update(self, dt: float) -> None`.
    -   Implement internal query: `entities = self._entity_manager.get_entities_with(Transform, RigidBody)`.
    -   (Future optimization: Use Cached Query from P1-008 here).
3.  **Update Call Sites**:
    -   Refactor `Scene` or `Application` code to stop manually querying entities for physics.
    -   Call `physics_system.update(dt)` directly or via `SystemManager`.

### Task B: Input Backend Abstraction
**Current State:** `InputManager` calls `pygame.joystick.init()` directly in `__init__`, causing crashes in headless environments (CI/CD).
**Target State:** Protocol-based backend.

1.  **Create Protocol `IInputBackend`**:
    -   Methods: `init_joysticks()`, `get_joystick_count()`, `get_joystick(id)`.
2.  **Implement `PygameInputBackend`**:
    -   Wraps existing `pygame.joystick` calls.
3.  **Refactor `InputManager`**:
    -   Inject `IInputBackend` in `__init__`.
    -   Remove direct `pygame` calls.

### Task C: Component Type Safety
**Current State:** `AISystem` uses `entity.ai_component` which relies on `Entity.__getattr__` magic. This hides type errors from static analysis tools.
**Target State:** Explicit component retrieval.

1.  **Refactor `AISystem`**:
    -   Change `entity.ai_component` to `entity.get_component(AIComponent)`.
2.  **Review other Systems**: Ensure `RenderSystem`, `PhysicsSystem` also use `get_component()`.

### Task D: Resource Error Handling
**Current State:** `load_atlas` relies on `json.load` raising generic exceptions.
**Target State:** Domain-specific exceptions.

1.  **Define Exceptions**: `ResourceLoadError`, `InvalidMetadataError`.
2.  **Update `load_atlas`**:
    -   Wrap JSON parsing in `try/except`.
    -   Raise `InvalidMetadataError` with clear message (filename, line number) on failure.

## 4. Acceptance Criteria
- [ ] `PhysicsSystem.update(dt)` takes only delta time.
- [ ] Tests can instantiate `InputManager` with a Mock Backend (no Pygame dependency).
- [ ] `mypy` check passes with strict settings (no implicit `Any` from `__getattr__`).
- [ ] Invalid JSON in atlas metadata raises a helpful error message.
