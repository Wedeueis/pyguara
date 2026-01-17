# PyGuara Engine

**PyGuara** is a production-grade, 2D game engine for Python 3.12+. It combines the clean architecture of enterprise software with the fun of game development, featuring a high-performance **Entity-Component-System (ECS)**, a native **Dependency Injection (DI)** container, and a suite of professional tools.

> **Status:** Alpha (Feature Complete Core). APIs are stable but subject to refinement.

[![CI](https://github.com/Wedeueis/pyguara/actions/workflows/ci.yml/badge.svg)](https://github.com/Wedeueis/pyguara/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Wedeueis/pyguara/graph/badge.svg?token=YOUR_CODECOV_TOKEN)](https://codecov.io/gh/Wedeueis/pyguara)
[![Python versions](https://img.shields.io/pypi/pyversions/pyguara.svg)](https://pypi.org/project/pyguara/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/github/license/Wedeueis/pyguara)](https://github.com/Wedeueis/pyguara/blob/main/LICENSE)

## 🌟 Why PyGuara?

Most Python game libraries (like Pygame) give you a window and a loop, leaving you to build the "engine" yourself. PyGuara provides that structure out of the box.

*   **Structure, not Spaghetti:** Built on Dependency Injection and ECS, your code remains decoupled and testable, even as your project grows.
*   **Batteries Included:** Physics, UI, Pathfinding, Behavior Trees, Tweening, and Tilemaps are all built-in.
*   **Developer Experience:** Includes a live **in-game editor**, hot-reloadable config, and robust logging.

## 🚀 Key Features

*   **⚡ Performance-First ECS**:
    *   Optimized `EntityManager` using **Inverted Indexes** for $O(1)$ queries.
    *   Memory-efficient component storage.
*   **🛠️ Professional Tooling**:
    *   **Live Editor**: Press `F12` to open the hierarchy inspector, modify components in real-time, and save scenes.
    *   **Debug Tools**: Visual gizmos, performance profilers, and event monitors.
*   **🎨 Advanced Rendering**:
    *   Backend-agnostic pipeline (currently `pygame-ce`) with automatic **Batching** and **Z-sorting**.
    *   Camera system with zoom, shake, and multiple viewports.
*   **⚛️ Physics & AI**:
    *   Native **Pymunk** integration for rigid bodies, joints, and raycasting.
    *   **Behavior Trees**, Finite State Machines (FSM), and **A* Pathfinding**.
*   **🖥️ UI System**:
    *   Constraint-based layout engine (Flexbox-like).
    *   Declarative widget composition with theming support.
*   **🎬 Animation & Scripting**:
    *   Powerful **Tweening** engine for smooth value transitions.
    *   **Coroutine** system for writing sequential, timed game logic.

## 📚 Documentation

*   **[Developer Onboarding Guide](docs/dev/ONBOARDING.md)**: Start here! A comprehensive guide to the engine's architecture and systems.
*   **[Core Architecture](docs/core/architecture.md)**: ECS, DI, and Events deep dive.
*   **[API Reference](docs/index.md)**: Detailed documentation for all subsystems.

## 🛠️ Installation

PyGuara requires **Python 3.12** or higher.

### Using `uv` (Recommended)

```bash
# Clone the repository
git clone https://github.com/Wedeueis/pyguara
cd pyguara

# Sync dependencies and install
uv sync
```

### Using `make`

```bash
# Clone and enter the repository
git clone https://github.com/Wedeueis/pyguara
cd pyguara

# One command to sync everything (core, dev, docs, benchmarks)
make install
```

### Using `pip`

```bash
pip install -e .[dev]
```

## 🎮 Quick Start

To run the engine sandbox and see the features in action:

```bash
python main.py
```

### Code Example: A Simple Scene

```python
from pyguara.scene.base import Scene
from pyguara.common.components import Transform
from pyguara.graphics.components import Sprite
from pyguara.physics.components import RigidBody, Collider
from pyguara.common.types import Vector2
from pyguara.graphics.components import Texture

class GameScene(Scene):
    def on_enter(self) -> None:
        # 1. Load Assets
        texture = self.resource_manager.load("player.png", Texture)

        # 2. Create Entity
        player = self.entity_manager.create_entity("Hero")

        # 3. Add Components (Data)
        player.add_component(Transform(position=Vector2(100, 100)))
        player.add_component(Sprite(texture=texture))

        # 4. Add Physics
        player.add_component(RigidBody(body_type=BodyType.DYNAMIC))
        player.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[32, 32]))
```

## 🤝 Contributing

Contributions are welcome! Please ensure you adhere to the project's code quality standards.

1.  **Run tests**: `pytest`
2.  **Lint**: `ruff check .`
3.  **Type Check**: `mypy pyguara`

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ✍️ Author

Developed by **Wedeueis Braz**.
