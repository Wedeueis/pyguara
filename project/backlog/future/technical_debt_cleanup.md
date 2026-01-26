# Technical Debt & Cleanup Roadmap

This document outlines technical debt and lower-priority features identified during the Beta phase assessment (PEP-2026.01) that are scheduled for future clean-up.

## 1. Shape Rendering Completeness (ModernGL)

**Priority:** Medium
**Location:** `pyguara/graphics/backends/moderngl/renderer.py`

**Current State:**
The `ModernGLRenderer` focuses on sprite batching (Textured Quads). It currently lacks dedicated shaders and logic for rendering geometric primitives (Circles, Rectangles, Polygons) which are available in the Pygame fallback backend.

**Recommendation:**
- Implement a `ShapeRenderer` class or extend the current renderer.
- Create a specific shader for efficient primitive rendering (e.g., using SDFs for anti-aliased circles).
- Ensure parity with the Pygame backend's `draw_circle`, `draw_rect`, etc.

## 2. MessagePack Serialization

**Priority:** Medium
**Location:** `pyguara/persistence/serializer.py`

**Current State:**
The `SerializerType.MESSAGEPACK` enum exists, but selecting it raises `NotImplementedError`. MessagePack offers a significant performance and size advantage over JSON for save files without the security risks of Pickle.

**Recommendation:**
- Add `msgpack` as an optional dependency (extras).
- Implement `MessagePackSerializer` matching the `ISerializer` protocol.
- Ensure custom types (Vector2, Rect) are handled via extension types or dict conversion.

## 3. Dynamic Component Registry

**Priority:** Medium
**Location:** `pyguara/scene/serializer.py`

**Current State:**
The scene serializer currently has a hardcoded list of supported component types (e.g., `Transform`, `Sprite`). Adding a new component requires modifying the engine core serializer.

**Recommendation:**
- Implement a `ComponentRegistry` singleton.
- Decorator `@register_component` for auto-registration.
- Update serializer to lookup classes by string name from the registry dynamically.

## 4. Editor Undo/Redo System

**Priority:** Low
**Location:** `pyguara/editor/`

**Current State:**
The editor is basic. Modifications to entities (moving, changing properties) are destructive and immediate.

**Recommendation:**
- Implement the **Command Pattern**.
- Create `IEditorCommand` interface with `execute()` and `undo()`.
- Maintain a `CommandStack` with a pointer to the current state.
- Actions like `MoveEntityCommand`, `ChangePropertyCommand` should encapsulate the "before" and "after" states.

## 5. Thread-Safety Verification

**Priority:** Low
**Location:** `tests/`

**Current State:**
The DI Container and Event Dispatcher are designed to be thread-safe, but this is not rigorously verified by tests.

**Recommendation:**
- Create a suite of concurrency tests using `threading` or `concurrent.futures`.
- Stress test `EventDispatcher.queue_event` from multiple threads.
- Stress test `DIContainer.resolve` for Scoped/Singleton lifetimes under high concurrency.
- Use `race` detectors if possible.

## 6. Advanced Audio Features (3D & Effects)

**Priority:** Low
**Location:** `pyguara/audio/`

**Current State:**
The audio system supports basic 2D panning (stereo). It lacks true 3D spatialization (Doppler effect, environmental reverb) and DSP effects.

**Recommendation:**
- Investigate `OpenAL` or advanced Pygame Mixer features.
- Implement `AudioEffect` chain (Reverb, Echo, LowPass).
- Add `AudioZone` triggers that modify audio settings (e.g., entering a cave adds reverb).
