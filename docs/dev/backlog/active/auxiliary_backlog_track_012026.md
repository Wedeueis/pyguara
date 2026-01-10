# Auxiliary Backlog Tracker
**Status:** Active
**Purpose:** Tracks valid architectural improvements, optimizations, and tooling feedback not covered in the main Roadmap (PEP-2026.01).

---

## 1. Architecture & ECS Hardening

### 1.1 Logic Orchestration (SystemManager)
**Source:** 2026-01-05-architectural-review, TODO.md
- **Context:** Currently, `Scene.update()` manually instantiates and calls systems (Physics, AI). This risks making the Scene a "God Object."
- **Task:** Implement a `SystemManager` class to:
  - Automate the execution order of systems.
  - Handle system dependency injection automatically.
  - Standardize the `System` protocol (e.g., `on_update(dt)`, `on_render()`).

### 1.2 Strict Component Typing
**Source:** 2026-01-08-engine-and-editor-audit
- **Context:** Components are currently plain Python classes. Users can accidentally add logic to them, violating ECS purity.
- **Task:** Enforce "Data-Only" semantics.
  - Add a meta-check or base class that validates subclasses are `dataclasses` or `pydantic` models.
  - Consider adding `__slots__` to components for memory optimization.

### 1.3 Optimized Component Iteration
**Source:** TODO.md
- **Context:** `get_entities_with(A, B)` performs set intersections every frame. Iterating the result involves dictionary lookups.
- **Task:** Implement `EntityManager.query_components(T1, T2)` returning a generator of **tuples** (e.g., `(transform, rigidbody)`) to bypass repetitive `entity.get_component()` lookups inside loops.

### 1.4 RenderSystem Hot-Loop Optimization
**Source:** feedback_repport.md
- **Context:** The `RenderSystem.submit` method currently uses `getattr` to retrieve rotation and scale, which is slow in Python.
- **Task:**
  - Enforce these fields in the `Renderable` protocol.
  - Or, query the `Transform` component directly to avoid the overhead of `__getattr__`.

---

## 2. Rendering Enhancements

### 2.1 Smart Batching Logic
**Source:** feedback_repport.md
- **Context:** Naive batching breaks if texture atlases switch frequently (e.g., Draw A(Tex1) -> Draw B(Tex2) -> Draw C(Tex1)).
- **Task:** Implement sorting in the `Batcher`:
  1. Sort by Z-Index (Layer).
  2. Sort by Texture ID (minimize state changes).

### 2.2 Multi-Camera / Viewport Support
**Source:** TODO.md
- **Context:** The current renderer assumes a single full-screen view.
- **Task:** Update `RenderSystem` to handle multiple `Viewport` configurations (e.g., for split-screen multiplayer or mini-maps).

---

## 3. Editor & Tooling Safety

### 3.1 Data Safety (Atomic Writes)
**Source:** 2026-01-09-editor-tooling-review
- **Context:** The Inspector's "Save to Source" writes directly to the JSON file. A crash during write will corrupt the asset.
- **Task:** Implement **Atomic Writes**:
  1. Write to a temporary file (e.g., `asset.json.tmp`).
  2. Validate the write was successful.
  3. Rename/Move the temp file to overwrite the original.
  - *Bonus:* Create a `.bak` copy before overwriting.

### 3.2 Gizmos & Visual Handles
**Source:** 2026-01-09-editor-tooling-review
- **Context:** Users can change values in the Inspector but cannot drag objects in the scene.
- **Task:** Implement a `GizmoSystem` using `UIRenderer`:
  - Draw translation/rotation handles.
  - Intercept mouse input on handles before it reaches the game world.

### 3.3 Redundancy Consolidation
**Source:** 2026-01-09-editor-tooling-review
- **Context:** There are two inspectors: the native Pygame one (`pyguara.tools.inspector`) and the new ImGui one (`pyguara.editor`).
- **Task:** Deprecate `EntityInspector` as an interactive tool. Repurpose it as a lightweight "Stats Overlay" (FPS, Entity Count, Memory) for production builds where ImGui is disabled.

### 3.4 Serialization Robustness
**Source:** 2026-01-09-editor-tooling-review
- **Context:** The `SceneSerializer` may fail on complex Python types.
- **Task:** Audit the serializer for:
  - Circular reference handling.
  - Support for Enums and nested Dataclasses.
