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
