# Architectural Review - January 5, 2026

## Executive Summary
The PyGuara engine demonstrates high-maturity architectural patterns, specifically in its use of Dependency Injection and optimized ECS querying. However, there is a "coupling creep" in the Scene layer where engine abstractions are being bypassed for convenience.

---

## 1. Core Strengths

### 1.1 Dependency Injection (`pyguara.di`)
- **Implementation:** Uses a thread-safe container with support for `SINGLETON`, `TRANSIENT`, and `SCOPED` lifetimes.
- **Verdict:** Highly robust. The use of `inspect.signature` and `typing.get_type_hints` for auto-wiring is idiomatic and clean. The scoping mechanism allows for excellent resource management (e.g., textures/buffers tied to scene lifetimes).

### 1.2 ECS Optimization (`pyguara.ecs`)
- **Implementation:** Employs an **Inverted Index** (`Dict[Type[Component], Set[str]]`) in the `EntityManager`.
- **Verdict:** Critical for Python performance. By using set intersections for multi-component queries, the engine avoids $O(N)$ entity scanning, ensuring frame times remain stable as world complexity increases.

### 1.3 Render Pipeline (`pyguara.graphics.pipeline`)
- **Implementation:** Separates submission from execution via `RenderQueue` and `Batcher`.
- **Verdict:** Follows modern GPU-friendly patterns. This structure supports future optimizations like sprite batching and multi-pass rendering (lighting/bloom) without refactoring the entity logic.

---

## 2. Identified Vulnerabilities

### 2.1 Abstraction Leakage (High Priority)
- **Problem:** `GameplayScene` and `TestScene` import `pygame` directly to perform debug drawing.
- **Impact:** This hard-codes the engine to Pygame. The `IRenderer` and `UIRenderer` protocols are ignored, making it impossible to switch backends (e.g., to ModernGL) without a total rewrite of game logic.
- **Evidence:** `pyguara/game/scenes.py` lines 86-115.

### 2.2 System Orchestration (Medium Priority)
- **Problem:** Logic systems (Physics, UI) are manually instantiated and updated within the `Scene`.
- **Impact:** The `Scene` class is trending toward a "God Object." It must know about every system's dependencies and update order.
- **Evidence:** `GameplayScene.update` manually calls `self.physics_system.update`.

### 2.3 Per-Frame Overhead (Low Priority)
- **Problem:** High frequency of `get_component` calls inside update/render loops.
- **Impact:** In Python, dictionary lookups inside loops are expensive.
- **Potential:** $O(F \times E)$ lookups where $F$ is frame and $E$ is entity count.

---

## 3. Recommended Roadmap

1. **Formalize the 'System' in ECS:** Create a `System` base class and a `SystemManager` to handle lifecycle and dependency injection for logic modules.
2. **Abstract Debug Drawing:** Implement a `DebugRenderer` service that accepts primitives (Circles, Rects) and submits them to the `RenderQueue` via the existing `IRenderer` protocol.
3. **Component Array Iteration:** Add methods to `EntityManager` to return joined component tuples (e.g., `zip_components(Transform, RigidBody)`) to minimize lookup overhead.


# Extra

1. Fix Rendering Injection: Split your rendering pipeline in Application.py.
     # Application.run
     self._scene_manager.render(self._world_renderer, self._ui_renderer)
       * In Application.py, you inject a UIRenderer and pass it to scene_manager.render().
       * In Scene.render(self, renderer: UIRenderer), the type hint forces a UI Renderer.
       * The Issue: A "World Renderer" (for sprites, tiles, particles) appears to be conflated with, or missing from, this pipeline. Usually, a Scene needs a WorldRenderer (with camera matrices, sorting layers) and a UIRenderer (screen space, no
         camera) separately. Currently, it seems you are forcing the Scene to render everything via the UI interface, or the naming is misleading.
2. Strict Type Guards: In ECS, add a check to ensure Components are actually data classes or Pydantic models. Python allows putting logic in classes easily; enforcing "Data Only" in components requires discipline or validation.
3. Documentation: Your docstrings are excellent. Keep this up. It is the single biggest differentiator between a "toy" engine and a usable tool.