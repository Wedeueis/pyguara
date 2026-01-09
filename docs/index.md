# Welcome to PyGuara

**PyGuara** is a modern, modular, and high-performance 2D game engine for Python 3.12+. It is built with a focus on clean architecture, decoupling, and developer productivity.

## 🏗️ Architectural Pillars

PyGuara is built on four core pillars:

1.  **Decoupled Logic**: Using a robust **Entity-Component-System (ECS)** and **Dependency Injection** to keep your game code clean and testable.
2.  **Flexible Rendering**: A multi-stage pipeline that supports batching and sorting, abstracted from the underlying hardware.
3.  **Physical Simulation**: Native integration with Pymunk for 2D physics.
4.  **Extensible Systems**: Comprehensive suites for AI (FSMs, Steering), UI, Audio, and Resource Management.

## 📚 Documentation Sections

### [Core Architecture](core/architecture.md)
Understand the foundational systems:
*   **ECS**: High-performance entity management with inverted indexing.
*   **Dependency Injection**: Auto-wired service management.
*   **Event System**: Thread-safe, decoupled communication.

### [Application & Lifecycle](core/application.md)
How the engine starts and runs:
*   **Bootstrapping**: The Composition Root pattern.
*   **Configuration**: Validated JSON-based settings.
*   **Error Handling**: Exception hierarchy and recovery strategies.

### [Graphics & UI](graphics/rendering.md)
Bringing your game to life:
*   **Render Pipeline**: Sorting, Batching, and Drawing.
*   **Camera & Viewports**: Managing coordinates and screen regions.
*   **UI System**: Flexible, themeable widget system.

### [Physics & Simulation](physics/simulation.md)
Interactions and Intelligence:
*   **Physics**: Rigid bodies, colliders, and raycasting.
*   **AI**: Finite State Machines, Steering behaviors, and Pathfinding.

### [Engine Systems](systems/resources.md)
Essential utilities:
*   **Resources**: Caching and type-safe asset loading.
*   **Audio**: SFX and Music management.
*   **Persistence**: Secure and versioned Save/Load logic.

## 🚀 Quick Start

If you haven't already, check the [README](https://github.com/yourusername/pyguara) for installation instructions. To run the default example, simply execute:

```bash
python main.py
```
