# PyGuara

**PyGuara** is a modern, modular, and high-performance 2D game engine for Python 3.12+. It features a robust Entity-Component-System (ECS) architecture, a native Dependency Injection (DI) container, and a decoupled event-driven design, making it suitable for scalable and maintainable game development.

> **Note:** This project is currently in **Pre-Alpha**. APIs are subject to change.

[![CI](https://github.com/Wedeueis/pyguara/actions/workflows/ci.yml/badge.svg)](https://github.com/Wedeueis/pyguara/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Wedeueis/pyguara/graph/badge.svg?token=YOUR_CODECOV_TOKEN)](https://codecov.io/gh/Wedeueis/pyguara)
[![PyPI version](https://badge.fury.io/py/pyguara.svg)](https://badge.fury.io/py/pyguara)
[![Python versions](https://img.shields.io/pypi/pyversions/pyguara.svg)](https://pypi.org/project/pyguara/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/github/license/Wedeueis/pyguara)](https://github.com/Wedeueis/pyguara/blob/main/LICENSE)

## 🚀 Key Features

*   **⚡ Performance-First ECS**:
    *   Optimized `EntityManager` using **Inverted Indexes** for $O(1)$ component queries.
    *   Cache-friendly data layout designed to minimize Python overhead.
*   **💉 Native Dependency Injection**:
    *   Built-in `DIContainer` supporting **Singleton**, **Transient**, and **Scoped** lifetimes.
    *   Automatic dependency resolution via Python type hints.
*   **🎨 Decoupled Rendering Pipeline**:
    *   Backend-agnostic design (currently supporting `pygame-ce`).
    *   Support for **Z-sorting**, **Batching**, and efficient draw call management.
*   **📢 Event-Driven Architecture**:
    *   Protocol-based event system for loose coupling between subsystems (Input, Physics, AI).
*   **🤖 Integrated AI & Physics**:
    *   Built-in Finite State Machines (FSM), Steering Behaviors, and Blackboard patterns.
    *   Physics integration via `pymunk`.

## 🛠️ Installation

PyGuara requires **Python 3.12** or higher.

### Using `uv` (Recommended)

```bash
# Clone the repository
git clone https://github.com/Wedeueis/pyguara
cd pyguara

# Sync dependencies
uv sync
```

### Using `pip`

```bash
pip install -e .[dev]
```

## 🎮 Quick Start

To run the default example scene included with the engine:

```bash
python main.py
```

### Creating a Basic Scene

Here is a minimal example of how to define a scene using PyGuara's ECS:

```python
from pyguara.scene.base import Scene
from pyguara.common.components import Transform
from pyguara.graphics.components.sprite import Sprite
from pyguara.common.types import Vector2

class MyGameScene(Scene):
    def on_enter(self) -> None:
        print("Welcome to PyGuara!")

        # Create an entity
        player = self.entity_manager.create_entity("player")

        # Add components
        player.add_component(Transform(position=Vector2(100, 100)))
        player.add_component(Sprite(texture_path="assets/player.png"))

    def update(self, dt: float) -> None:
        # Game logic goes here
        pass
```

## 🏗️ Architecture Overview

The codebase is organized to enforce separation of concerns:

*   `pyguara/ecs/`: The core Entity-Component-System implementation.
*   `pyguara/di/`: The Dependency Injection container.
*   `pyguara/events/`: The event dispatching system.
*   `pyguara/graphics/`: Rendering protocols, pipelines, and backends.
*   `pyguara/physics/`: Physics engine integration (Pymunk).
*   `pyguara/application/`: Application lifecycle and bootstrapping.

## 🤝 Contributing

Contributions are welcome! Please ensure you adhere to the project's code quality standards.

1.  **Install development dependencies**:
    ```bash
    uv sync --extra dev
    ```
2.  **Run tests**:
    ```bash
    pytest
    ```
3.  **Run linters**:
    ```bash
    ruff check .
    mypy pyguara
    ```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ✍️ Author

Developed by **Wedeueis Braz**.
