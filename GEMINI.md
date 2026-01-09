# PyGuara Context for Gemini

This file provides a comprehensive overview of the **PyGuara** project to facilitate efficient and safe assistance by AI agents.

## 🔭 Project Overview

**PyGuara** is a modern, modular, and high-performance **2D Game Engine** built with Python 3.12+. It prioritizes a clean separation of concerns through a strict **Entity-Component-System (ECS)** architecture, **Event-Driven** communication, and native **Dependency Injection (DI)**.

The project is designed for scalability, allowing developers to build complex games without the "spaghetti code" often associated with rapid game prototyping.

### Core Philosophy
*   **Performance:** Optimized ECS queries using inverted indexes ($O(1)$ lookups / $O(K)$ queries).
*   **Modularity:** Systems are decoupled via events and DI; `pygame-ce` is just one swappable backend.
*   **Type Safety:** Heavy use of Python type hints, `mypy` strict mode, and runtime validation.

## 🏗️ Architecture & Key Components

The codebase follows a clear directory structure reflecting the architectural layers:

### 1. Entity-Component-System (`pyguara/ecs`)
*   **`EntityManager`**: The central database. Uses **Inverted Indexes** (Dictionary of Sets) to map `ComponentType -> Set[EntityID]`.
    *   **Optimization:** Queries like `get_entities_with(Transform, Sprite)` use fast set intersection, avoiding full entity iteration.
*   **`Entity`**: A lightweight ID container with a list of components. Notifies the manager on component changes.
*   **`Component`**: Pure data containers (dataclasses/pydantic-like).

### 2. Dependency Injection (`pyguara/di`)
*   **`DIContainer`**: Manages object lifecycles (Singleton, Transient, Scoped).
*   **Wiring**: Dependencies are typically resolved in `Application.__init__` or `Bootstrap` phases.

### 3. Application Lifecycle (`pyguara/application`)
*   **`Application`**: Manages the main game loop:
    1.  **Time**: Delta time calculation (`dt`).
    2.  **Input**: Polling via `InputManager`.
    3.  **Update**: Flushing event queues, updating UI, then updating Scenes.
    4.  **Render**: Clearing screen, rendering Scenes, rendering UI, swapping buffers.

### 4. Events (`pyguara/events`)
*   **`EventDispatcher`**: Central hub for pub/sub messaging. Supports queued events to handle safe inter-thread communication or deferred processing.

### 5. Graphics (`pyguara/graphics`)
*   **Backend Agnostic**: Uses protocols (`UIRenderer`, `Window`) to define interfaces.
*   **Current Backend**: `pygame-ce` (Community Edition).
*   **Features**: Sprite batching, Camera systems, Particle systems.

### 6. Physics (`pyguara/physics`)
*   **Integration**: Wraps `pymunk` for 2D rigid body physics.
*   **Synchronization**: Physics steps are synchronized with the game loop in `PhysicsSystem`.

## 🛠️ Development Tools & Conventions

The project uses modern Python tooling managed by `uv`.

### Build & Dependency Management
*   **Manager**: `uv` (Fast Python package installer/resolver).
*   **Dependencies**: Defined in `pyguara/pyproject.toml`.
*   **Lockfile**: `uv.lock`.

### Common Commands (via `Makefile`)
| Command | Description |
| :--- | :--- |
| `make play` | Run the main game (`main.py`). |
| `make test` | Run unit tests (skips slow/performance ones). |
| `make test-cov` | Run tests with coverage report (Target: 85%+). |
| `make lint` | Run `ruff` linter. |
| `make type-check` | Run `mypy` static type checker. |
| `make format` | Format code with `ruff format`. |
| `make dev-check` | Run formatting, linting, type-checking, and tests (recommended before commit). |

### Coding Standards
*   **Type Hints**: MANDATORY for all function arguments and return types.
*   **Docstrings**: Google-style docstrings for all modules, classes, and public methods.
*   **Imports**: Sorted automatically by `ruff`. Absolute imports preferred (`from pyguara.x import y`).
*   **Safety**: "Ask before changing" policy for core systems (ECS, Event Bus).

## 📂 Key File Map
*   `main.py`: Entry point. Bootstraps the DI container and starts the Application.
*   `pyguara/application/application.py`: Main loop logic.
*   `pyguara/ecs/manager.py`: Core ECS logic (read this to understand queries).
*   `pyguara/config/game_config.json`: Runtime configuration (resolution, fps, debug flags).
*   `config/game_config.json`: Default/Template config.

## 📝 Notes for AI Assistant
*   **ECS Usage**: When adding game logic, create a **System** (class) that queries entities via `EntityManager.get_entities_with(...)` in an `update(dt)` method. Do *not* put logic inside Components.
*   **UI vs World**: UI elements are managed by `UIManager` and rendered separately from the game world entities.
*   **State Management**: Use `Scene` classes for different game states (Menu, Gameplay, Pause).
