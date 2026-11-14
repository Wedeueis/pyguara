# Project Structure

How to lay out a game built on PyGuara. The engine does not enforce any of
this, and there is no project scaffold command yet; this is the shape the
demos under `games/` use, and it separates the three things an ECS game is
made of: **data** (components), **logic** (systems) and **composition**
(scenes and prefabs).

## 1. Directory layout

```text
my_game/
├── assets/                  # Loaded through ResourceManager
│   ├── textures/            # .png, .jpg
│   ├── audio/               # .wav, .ogg
│   ├── fonts/               # .ttf, .otf
│   ├── prefabs/             # .prefab.json / .prefab.yaml
│   └── maps/                # .tmx (Tiled), .ldtk
├── config/
│   └── game_config.json     # Read at startup; see docs/core/configuration.md
├── my_game/                 # The game package
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── bootstrap.py         # Builds the container; adds the game's services
│   ├── components.py        # Data only
│   ├── systems.py           # Logic
│   ├── events.py            # The game's own event types
│   └── scenes.py            # Composition: what exists and what runs
├── tests/
├── pyproject.toml
└── README.md
```

A small game keeps `components.py` and `systems.py` as single files, as the
demos do. Split them into packages when they grow; nothing else changes.

`config/game_config.json` is found relative to the working directory, so run
the game from the project root.

## 2. The pieces

### The bootstrap (`bootstrap.py`)

`create_application()` wires the whole engine and returns an `Application`.
A game that needs to add its own services, or change the configuration
before the window is built, uses `create_container()` instead: it returns
the same container before the `Application` exists.

```python
# bootstrap.py
from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig
from pyguara.di.container import DIContainer

from my_game.services import Leaderboard


def _configure(config: GameConfig) -> None:
    config.display.title = "My Game"
    config.display.screen_width = 1280
    config.display.screen_height = 720


def configure_game_container() -> DIContainer:
    container = create_container(_configure)
    container.register_singleton(Leaderboard, Leaderboard)
    return container
```

```python
# main.py
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher

from my_game.bootstrap import configure_game_container
from my_game.scenes import GameplayScene


def main() -> None:
    container = configure_game_container()
    app = container.get(Application)
    app.run(GameplayScene("gameplay", container.get(EventDispatcher)))


if __name__ == "__main__":
    main()
```

The container holds **services**: things with one instance for the whole
game, like a leaderboard client or a save manager. Systems are not
registered there. Each scene owns its systems (see below).

### Components (`components.py`)

Pure data: a dataclass that inherits from `BaseComponent`.

- **No methods.** `BaseComponent` raises `TypeError` when the class is
  defined if it declares one. A method that only reads the component's own
  fields can be marked `@pure_query`.
- **One of each type per entity.**
- Keep fields serialisable (numbers, strings, bools, `Vector2`, `Color`)
  if the component should round-trip through prefabs and saves.

```python
# components.py
from dataclasses import dataclass

from pyguara.ecs.component import BaseComponent


@dataclass(slots=True)
class Stamina(BaseComponent):
    current: float = 100.0
    maximum: float = 100.0
    regen_rate: float = 10.0
```

### Systems (`systems.py`)

A system is any object with `update(dt)`. It queries entities through the
`EntityManager` it was given and writes the results back.

```python
# systems.py
from pyguara.ecs.manager import EntityManager

from my_game.components import Stamina


class StaminaSystem:
    def __init__(self, entity_manager: EntityManager) -> None:
        self._entities = entity_manager

    def update(self, dt: float) -> None:
        for entity in self._entities.get_entities_with(Stamina):
            stamina = entity.get_component(Stamina)
            stamina.current = min(
                stamina.maximum, stamina.current + stamina.regen_rate * dt
            )
            self._entities.notify_component_changed(entity.id, Stamina)
```

After writing a field, call `notify_component_changed`. Anything that
mirrors the component (physics bodies, render batches, the spatial index)
keeps the old value otherwise.

### Scenes (`scenes.py`)

A scene owns its own `EntityManager` and `SystemManager`; there is no
global one. The scene creates the starting entities and registers the
systems that run on them.

```python
# scenes.py
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.scene.base import Scene

from my_game.components import Stamina
from my_game.systems import StaminaSystem


class GameplayScene(Scene):
    def on_enter(self) -> None:
        self.system_manager.register(
            StaminaSystem(self.entity_manager), priority=500
        )

        player = self.entity_manager.create_entity("hero")
        player.add_component(Transform(position=Vector2(100, 100)))
        player.add_component(Stamina())

    def update(self, dt: float) -> None:
        pass

    def on_exit(self) -> None:
        pass
```

- The engine's own systems take priorities 100 to 399. Use **500 or above**
  for game systems; lower numbers run earlier.
- **A scene has no container until the engine has resolved it**, so reach
  for `self.container` in `on_enter()` or later, never in `__init__`.
- Game logic that must be reproducible (physics, AI decisions) belongs in
  `fixed_update(fixed_dt)`; anything that should look smooth belongs in
  `update(dt)`.

See [Scenes](../core/scenes.md) for switching, stacking and persistent
layers.

### Prefabs (`assets/prefabs/`)

An entity that is created in more than one place should be a prefab: a
data file naming its components and their field values, with optional
inheritance and children.

```python
enemy = self.prefab_factory.create(prefab_data)
```

Every scene has a `prefab_factory` bound to its `EntityManager`. See
[Prefabs](../systems/prefabs.md) for the file format. A plain factory
function that calls `add_component` is fine for a small game.

## 3. Adding a feature

To add stamina to the example above:

1. **Data:** add the `Stamina` component to `components.py`.
2. **Logic:** add `StaminaSystem` to `systems.py`.
3. **Composition:** register the system in the scene's `on_enter()`, and
   add `Stamina` to the player (in code or in its prefab).
4. **Test:** cover the system with a test that builds an `EntityManager`
   directly. No window is needed.

## 4. Do and do not

| | Do | Do not |
| --- | --- | --- |
| **Rendering** | Draw through `IRenderer` and `UIRenderer` | `import pygame` in game code |
| **Queries** | `entity_manager.get_entities_with(A, B)` | Iterate every entity and test it |
| **State** | Keep game state in components | Hide it in fields of a system |
| **Services** | Resolve from the container in `on_enter()` | Module-level singletons |
| **Assets** | Load through `ResourceManager` | Hardcode absolute file paths |
| **Physics** | `RigidBody` with `PhysicsSystem` for simulated bodies; `CharacterBody` with `CharacterMover` for characters | Write `transform.position` on a simulated body |
| **Tuning** | Put numbers in config or prefabs | Scatter literals through systems |

## 5. Testing

A system takes its `EntityManager` as an argument, so a test builds one and
calls `update` directly:

```python
from pyguara.ecs.manager import EntityManager

from my_game.components import Stamina
from my_game.systems import StaminaSystem


def test_stamina_regenerates() -> None:
    entities = EntityManager()
    player = entities.create_entity()
    player.add_component(Stamina(current=50.0, regen_rate=10.0))

    StaminaSystem(entities).update(1.0)

    assert player.get_component(Stamina).current == 60.0
```

For a test that needs the whole engine wired without a window,
`create_headless_application()` in `pyguara.application.bootstrap` swaps
the window and renderers for no-op equivalents.
