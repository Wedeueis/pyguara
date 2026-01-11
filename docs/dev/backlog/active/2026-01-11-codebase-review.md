# Codebase Architectural Review
**Date:** 2026-01-11
**Status:** Complete

This document tracks a detailed review of all PyGuara subsystems to ensure adherence to established architectural patterns (DI, Events, Config, Logging, Error Handling).

## Legend
- ✅ **Pass**: Adheres to standards.
- ⚠️ **Warning**: Minor deviation or opportunity for improvement.
- ❌ **Fail**: Violation of core principles (e.g., hardcoded dependencies, skipped DI).
- ℹ️ **Note**: Observation or suggestion.

---

## 1. Domain: AI
*Status: Checked*
- **File:** `pyguara/ai/ai_system.py`
- ✅ **DI**: Correctly injects `EntityManager`.
- ⚠️ **Logic**: Direct property access `entity.ai_component` relies on `__getattr__` magic. Prefer `entity.get_component(AIComponent)` for explicit type safety.
- ℹ️ **Events**: No event emission. Could emit `AIStateChangedEvent`.
- ❌ **Logging**: No logging implementation.

## 2. Domain: Audio
*Status: Checked*
- **File:** `pyguara/audio/manager.py`
- ✅ **DI**: Correctly injects `IAudioSystem` and `ResourceManager`.
- ✅ **Events**: Ready for event integration.
- ❌ **Logging**: Uses `print()` in `_get_clip` and `_get_clip` error handling. Must use `logging` module.
- ⚠️ **Error Handling**: Catches generic `Exception` and prints it. Should log exception with traceback.

## 3. Domain: Input
*Status: Checked*
- **File:** `pyguara/input/manager.py`
- ✅ **DI**: Correctly injects `EventDispatcher`.
- ✅ **Events**: Dispatches `OnActionEvent` correctly.
- ❌ **Legacy**: `pygame.joystick.init()` called directly in `__init__`. Should be wrapped in an `IInputBackend` or similar to allow headless testing.
- ❌ **Logging**: Uses `print()` for controller detection.

## 4. Domain: Physics
*Status: Checked*
- **File:** `pyguara/physics/physics_system.py`
- ✅ **DI**: Correctly injects `IPhysicsEngine`.
- ⚠️ **API**: `update(entities: List[Entity])` signature requires caller to perform the query. Inconsistent with `AISystem` which holds `EntityManager` and queries internally. Suggest standardizing on System holding `EntityManager`.
- ℹ️ **Encapsulation**: Accesses `_body_handle` (protected) member. Acceptable for this specific bridge pattern.

## 5. Domain: Graphics
*Status: Checked*
- **File:** `pyguara/graphics/pipeline/render_system.py`
- ✅ **DI**: Correctly injects `IRenderer`.
- ✅ **Protocol**: Strictly uses `Renderable` protocol.
- ❌ **Logging**: No logging. Should log backend initialization or critical render failures.

## 6. Domain: UI
*Status: Checked*
- **File:** `pyguara/ui/manager.py`
- ✅ **DI**: Correctly injects `EventDispatcher`.
- ✅ **Events**: Subscribes to `OnMouseEvent` and maps to `UIEventType`.
- ❌ **Logging**: No logging.

## 7. Domain: Resources
*Status: Checked*
- **File:** `pyguara/resources/manager.py`
- ✅ **Type Safety**: Uses Generics `T` bounded to `Resource` for `load()` method.
- ❌ **Logging**: Excessive use of `print()` for loading/unloading status.
- ⚠️ **Error Handling**: `load_atlas` does not wrap JSON parsing in specific error handling context (relies on raw `json.load` exception).

## 8. Domain: Scene
*Status: Checked*
- **File:** `pyguara/scene/manager.py`
- ✅ **DI**: Uses Setter Injection (`set_container`) which is appropriate for its role as Scope Root.
- ✅ **Logic**: Clean state management.
- ❌ **Logging**: No logging of scene transitions.

---

## Summary & Action Plan

### Critical Issues
1.  **Systemic `print()` usage**: The codebase relies on `print()` for debugging info. This must be replaced with the standard `logging` module (`logger.info`, `logger.error`).
    - **Affected**: Audio, Input, Resources.
2.  **Inconsistent System API**: `PhysicsSystem` vs `AISystem` query responsibility.

### Recommended Actions
1.  **Refactor Logging**: Create a `pyguara.log` module to configure the root logger and replace all `print` statements.
2.  **Standardize Systems**: Refactor `PhysicsSystem` to take `EntityManager` in `__init__` and perform its own query in `update()`.
3.  **Refactor Input**: Abstract `pygame.joystick` calls into the backend interface to enable testing.
