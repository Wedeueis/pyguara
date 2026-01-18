# Development Backlog

## Phase 1: Decoupling & Abstraction

- [ ] **Task: Remove Pygame from Scenes**
  - Refactor `GameplayScene.render` to use a `DebugDrawer` service.
  - Remove `import pygame` from `pyguara/game/scenes.py`.
- [ ] **Task: Implement `SystemManager`**
  - Create `pyguara/ecs/system.py` defining the `System` protocol.
  - Implement `SystemManager` to automate the execution of Physics, AI, and Animation.
- [ ] **Task: Move Physics logic to a System**
  - Physics should not be manually called by the Scene; it should be a background system that queries the ECS.

## Phase 2: Performance & DX

- [ ] **Task: Optimized Component Iteration**
  - Implement `EntityManager.query_components(T1, T2)` returning a generator of tuples to bypass repetitive dictionary lookups.
- [ ] **Task: Type-Safe Component Accessors**
  - Add `__slots__` to Components.
  - Provide a generator-based alternative to `Entity.__getattr__` for better IDE support.

## Phase 3: Graphics Evolution

- [ ] **Task: Batching Optimization**
  - Implement automatic texture batching in the `Batcher` class.
- [ ] **Task: Multi-Camera Support**
  - Update `RenderSystem` to handle multiple Viewports/Cameras for UI overlays and Split-screen.

# Feedbacks
1. Renderer Optimization: Ensure Batcher handles texture atlas switching smartly. If you draw Sprite A (Tex1) -> Sprite B (Tex2) -> Sprite C (Tex1), you break batching. Sorting by Z-Index then by Texture ID is a common optimization.
2. Input Mapping: I saw InputManager but on_mouse_event in UI used raw strings ("MOUSE_DOWN"). Consider using an Enum for internal event types to avoid stringly-typed errors.
3. Editor Tools: Since you have a di system and inspector in the file list, your next big leap is an In-Game Editor/Console. With DI, you can easily inject a "DebugRenderer" or "PropertyInspector" to tweak Component values at runtime.
4. The submit method in RenderSystem manually extracts rotation and scale with getattr. Ideally, Renderable protocol should enforce these, or you should query the Transform component directly to avoid getattr overhead in the hot loop.
