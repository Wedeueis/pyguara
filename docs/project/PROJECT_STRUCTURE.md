# PyGuara Project Structure Guide

PyGuara is not a typical scripting framework; it is an **ECS (Entity Component System)** engine built around **Dependency Injection (DI)**. This architecture requires a strict separation of concerns: **Data** (Components), **Logic** (Systems), and **Composition** (Scenes/Prefabs).

To maintain scalability and performance, developers should adhere to the following project structure.

## 1. Directory Layout

The root directory acts as a workspace. Your actual game code resides strictly within `src/`.

```text
my_game_project/
├── assets/                  # Runtime resources (Must be strictly organized)
│   ├── textures/            # .png, .jpg
│   ├── audio/               # .wav, .ogg
│   ├── fonts/               # .ttf, .otf
│   └── data/                # .json, .yaml (Game balance data, dialogue)
├── config/                  # Configuration files
│   ├── game.toml            # Main config (Resolution, Inputs, Debug flags)
│   └── logging.toml         # Logger configuration
├── src/                     # Source code root
│   └── my_game/             # Your game package (Rename this to your game name)
│       ├── __init__.py
│       ├── main.py          # Application Entry Point
│       ├── bootstrap.py     # DI Container & System Registration (CRITICAL)
│       ├── components/      # Pure Data (Dataclasses only)
│       ├── systems/         # Game Logic & Behavior
│       ├── prefabs/         # Entity Factories (Blueprints)
│       ├── scenes/          # Scene Definitions (Composition Roots)
│       └── ui/              # UI Widgets and Layouts
├── tests/                   # Unit and Integration tests
├── pyproject.toml           # Dependencies (uv/poetry/pip)
└── README.md

```

---

## 2. Core Modules Breakdown

### A. The Bootstrap (`src/my_game/bootstrap.py`)

Unlike simpler frameworks where you write logic in a global loop, PyGuara requires systems to be registered in a **Dependency Injection Container**.

* **Role:** configure the `DIContainer` with your game-specific systems.
* **Best Practice:** Never register systems inside `main.py`. Keep the entry point clean.

```python
# bootstrap.py
from pyguara.application.bootstrap import create_application_container
from my_game.systems.combat import CombatSystem
from my_game.systems.ai import AiSystem

def configure_game_container():
    # 1. Initialize Core Engine
    container = create_application_container()

    # 2. Register Game Systems (Singletons persist effectively)
    container.register_singleton(CombatSystem, CombatSystem)
    container.register_singleton(AiSystem, AiSystem)

    return container

```

### B. Components (`src/my_game/components/`)

This directory contains **pure data**.

* **Rule:** Components must be Python `@dataclass`.
* **Rule:** Components **must not** contain game logic (methods like `update()` or `shoot()`).
* **Rule:** Serializable fields only (ints, floats, strings, bools, Vector2).

```python
# components/gameplay.py
from dataclasses import dataclass

@dataclass
class Health:
    current: float
    max: float

```

### C. Systems (`src/my_game/systems/`)

This is the "Brain" of the game. Systems retrieve data, process it, and write it back.

* **Rule:** Systems are injected with `EntityManager` or `EventDispatcher`.
* **Rule:** Logic goes here. If an entity takes damage, the `CombatSystem` calculates it, not the Entity class.

```python
# systems/combat.py
class CombatSystem:
    def __init__(self, entity_manager: EntityManager):
        self._em = entity_manager

    def update(self, dt: float):
        # Query entities that have Health
        for entity in self._em.get_entities_with(Health):
            pass # Logic here

```

### D. Prefabs (`src/my_game/prefabs/`)

Since PyGuara creates entities via code, "Prefabs" are factory functions that assemble an entity from multiple components.

* **Role:** Centralize entity creation. Don't manually `add_component` inside your scenes; call a prefab instead.

```python
# prefabs/player.py
def create_player(manager: EntityManager, pos: Vector2):
    e = manager.create_entity("hero")
    e.add_component(Transform(position=pos))
    e.add_component(Health(100, 100))
    e.add_component(Sprite(texture="hero.png"))
    return e

```

### E. Scenes (`src/my_game/scenes/`)

Scenes are the **Composition Roots**. They do not contain heavy logic. Their job is to:

1. Resolve Systems from the Container.
2. Instantiate the initial World (using Prefabs).
3. Orchestrate the update loop order.

---

## 3. Workflow Example: Adding a Feature

To add a new feature (e.g., "Stamina") to your game, follow this strict flow:

1. **Define Data:** Create `src/my_game/components/stamina.py` (Dataclass: `val`, `regen_rate`).
2. **Define Logic:** Create `src/my_game/systems/stamina_system.py`.
    * Logic: Decrease on action, increase over time.
3. **Register Logic:** Add `StaminaSystem` to `bootstrap.py`.
4. **Update Prefab:** Add the `Stamina` component to `src/my_game/prefabs/player.py`.
5. **Execute:** Inject `StaminaSystem` into your `GameplayScene` and call `stamina_system.update(dt)` in the loop.

## 4. Best Practices

| Category | Do | Don't |
| --- | --- | --- |
| **Dependencies** | Use `container.get()` in Scenes. | Import global variables or singletons manually. |
| **State** | Store state in `Components`. | Store state in `System` classes (Systems should be stateless logic processors). |
| **Testing** | Write tests in `tests/` mocking the DI Container. | Test logic by running the game manually. |
| **Assets** | Load assets via `ResourceManager`. | Hardcode file paths (e.g., `"C:/Users/..."`). |
| **Physics** | Use `PhysicsSystem` for movement. | Manually update `transform.position` for physics objects. |

## 5. Testing Architecture

Because PyGuara uses Dependency Injection, your game logic is highly testable. You can test a system without opening a window.

**Example Test Structure (`tests/test_combat.py`):**

```python
def test_player_takes_damage():
    # Setup
    em = EntityManager()
    system = CombatSystem(em)
    player = create_player(em, Vector2(0,0))

    # Act
    system.apply_damage(player, 10)

    # Assert
    assert player.get_component(Health).current == 90

```
