# Zero to Hero: Making your First PyGuara Game

Welcome to the **Zero to Hero** tutorial series for the **PyGuara Game Engine**! This guide takes you step-by-step through the structure and concepts of PyGuara by utilizing the five educational modules located under the `games/` folder of the repository.

By the end of this guide, you will understand how the engine boots up, how to design code around the Entity-Component-System (ECS) mindset, how to hook up input maps and handle events, how to integrate physical simulation via Pymunk, how to construct constraint-based UI scene graphs, and finally, how to compile and distribute your game as a standalone binary.

---

## 🗺️ Tutorial Roadmap

The tutorial is structured into six progressive modules:
1. **The Boot Sequence** (`games/boot_process`): Initializing the engine, Dependency Injection, and starting your first Scene.
2. **The ECS Mindset** (`games/ecs_mental_model`): Composing game objects using pure data components and executing logic with Systems.
3. **Input Mapping & Events** (`games/input_events`): Binding keyboard controls to logical actions and using the event queue for decoupled communication.
4. **Physical Simulation** (`games/physics_integration`): Adding rigid bodies, colliders, and collision listeners.
5. **UI & Scene graphs** (`games/ui_scene_graph`): Organizing menu layouts, panels, and responsive widgets.
6. **Standalone Compilation**: Building and packaging the final game executable using `pyguara build`.

---

## 🛠️ Part 1: The Boot Sequence (`games/boot_process`)

Before we can render characters or handle physics, we must initialize the engine. In PyGuara, this is done using **Dependency Injection (DI)** and a **bootstrap configuration** file.

The entry point of any PyGuara game performs the following core steps:
1. Configures logging.
2. Bootstraps the DI container.
3. Retrieves the global `Application` instance from the container.
4. Initializes the starting `Scene`.
5. Runs the game loop.

### The Entry Point (`main.py`)
```python
import logging
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher
from games.boot_process.bootstrap import configure_game_container
from games.boot_process.scenes import BootScene

def main():
    # 1. Configure logging
    logging.basicConfig(level=logging.INFO)

    # 2. Bootstrap Dependency Injection
    container = configure_game_container()

    # 3. Resolve the Application
    app = container.get(Application)

    # 4. Create the starting scene
    event_dispatcher = container.get(EventDispatcher)
    start_scene = BootScene(event_dispatcher)

    # 5. Run the Game Loop
    app.run(starting_scene=start_scene)

if __name__ == "__main__":
    main()
```

### The Bootstrap Wiring (`bootstrap.py`)
Inside `bootstrap.py`, we instantiate the central `DIContainer` and register our managers, window backends, and renderers. Because PyGuara is completely decoupled, we can register any concrete implementation that conforms to our protocols (e.g., `IRenderer` or `UIRenderer`):

```python
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.config.manager import ConfigManager
from pyguara.graphics.window import Window, WindowConfig
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.manager import InputManager
from pyguara.scene.manager import SceneManager
from pyguara.resources.manager import ResourceManager
from pyguara.ui.manager import UIManager
from pyguara.systems.manager import SystemManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.application.application import Application

def configure_game_container() -> DIContainer:
    container = DIContainer()
    container.register_instance(DIContainer, container)

    # Event System (The Backbone)
    event_dispatcher = EventDispatcher()
    container.register_instance(EventDispatcher, event_dispatcher)

    # Central Config
    config_manager = ConfigManager(event_dispatcher)
    config_manager.load()
    container.register_instance(ConfigManager, config_manager)

    # Window & Graphics Configuration
    win_config = WindowConfig(title="Module 1: Boot Process", screen_width=800, screen_height=600)
    window_backend = PygameWindow()
    window = Window(win_config, window_backend)
    window.create()
    container.register_instance(Window, window)

    # Renderer implementations conform to IRenderer & UIRenderer protocols
    renderer = PygameBackend(window.native_handle)
    container.register_instance(IRenderer, renderer)

    ui_renderer = PygameUIRenderer(window.native_handle)
    container.register_instance(UIRenderer, ui_renderer)

    # Core Systems registered as Singletons
    container.register_singleton(InputManager, InputManager)
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(ResourceManager, ResourceManager)
    container.register_singleton(UIManager, UIManager)
    container.register_singleton(SystemManager, SystemManager)
    container.register_singleton(CoroutineManager, CoroutineManager)
    container.register_singleton(Application, Application)

    return container
```

---

## 🧩 Part 2: The ECS Mindset (`games/ecs_mental_model`)

Instead of writing classic Object-Oriented inheritance trees (like a `Player` class that inherits from `PhysicsObject` which inherits from `GameObject`), PyGuara leverages a strict **Entity-Component-System (ECS)** composition architecture.

- **Entity**: A lightweight ID container (simply an identification number).
- **Component**: Pure data container with no logic whatsoever. Inherits from `Component` and uses `__slots__` for cache/RAM optimization.
- **System**: Pure logic execution. Systems query entities containing specific components and manipulate their data.

### 1. Defining Components (`components.py`)
```python
from dataclasses import dataclass
from pyguara.ecs.component import Component
from pyguara.common.types import Vector2, Color

@dataclass
class Transform(Component):
    __slots__ = ("position",)
    position: Vector2

@dataclass
class Sprite(Component):
    __slots__ = ("color", "size")
    color: Color
    size: Vector2
```

### 2. Creating a System (`systems.py`)
To process movement logic, we create a `MovementSystem`. In its constructor, we register our query to enable high-performance $O(1)$ query caching:

```python
from pyguara.ecs.manager import EntityManager
from pyguara.common.types import Vector2
from games.ecs_mental_model.components import Transform

class MovementSystem:
    def __init__(self, entity_manager: EntityManager):
        self._em = entity_manager
        # Speed up lookups from O(N) to O(1) by caching this query
        self._em.register_cached_query(Transform)

    def update(self, dt: float) -> None:
        # Loop through entities possessing the Transform component
        for entity in self._em.get_entities_with_cached(Transform):
            transform = entity.get_component(Transform)

            # Update coordinate state (diagonal movement at 100 px/sec)
            speed = 100.0
            new_x = transform.position.x + speed * dt
            new_y = transform.position.y + speed * dt

            # Wrap around boundaries
            if new_x > 800: new_x = 0
            if new_y > 600: new_y = 0

            transform.position = Vector2(new_x, new_y)
```

### 3. Assembling the Scene (`scenes.py`)
In the scene's `on_enter` method, we register the system, spawn an entity, and attach components to it:

```python
from pyguara.scene.base import Scene
from pyguara.common.types import Vector2, Color, Rect
from games.ecs_mental_model.components import Transform, Sprite
from games.ecs_mental_model.systems import MovementSystem

class ECSScene(Scene):
    def on_enter(self) -> None:
        self.movement_system = MovementSystem(self.entity_manager)

        # Spawn our visual entity
        hero = self.entity_manager.create_entity("hero")
        hero.add_component(Transform(position=Vector2(100, 100)))
        hero.add_component(Sprite(color=Color(255, 0, 0), size=Vector2(50, 50)))

    def update(self, dt: float) -> None:
        self.movement_system.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        world_renderer.clear(Color(30, 30, 30))

        # Custom immediate rendering loop (Usually handled by RenderSystem)
        for entity in self.entity_manager.get_entities_with(Transform, Sprite):
            transform = entity.get_component(Transform)
            sprite = entity.get_component(Sprite)

            rect = Rect(transform.position.x, transform.position.y, sprite.size.x, sprite.size.y)
            world_renderer.draw_rect(rect, sprite.color)
```

---

## 🎮 Part 3: Input Mapping & Events (`games/input_events`)

PyGuara decouples player input from the engine loop using semantic action bindings and a pub/sub event dispatcher.

1. **InputManager**: Maps keyboard, mouse, or gamepad inputs (e.g. `SPACE`) to virtual actions (e.g. `"jump"`).
2. **EventDispatcher**: Broadcasts event payloads across systems. Systems can subscribe to actions without holding references to windows or input devices.

### 1. Registering Action Bindings
Inside your scene's `on_enter`:
```python
from pyguara.input.manager import InputManager
from pyguara.input.types import InputDevice, ActionType
from pyguara.input.keys import SPACE

input_manager = self.container.get(InputManager)
# Register a digital action "jump" that triggers on PRESS
input_manager.register_action("jump", ActionType.PRESS)
# Bind keyboard SPACE key to trigger "jump"
input_manager.bind_input(InputDevice.KEYBOARD, SPACE, "jump")
```

### 2. Translating Inputs to Events (`systems.py`)
We create an `InputBridgeSystem` that intercepts input mappings and dispatches game-specific actions (like a `JumpEvent`):

```python
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.events import OnActionEvent
from games.input_events.events import JumpEvent

class InputBridgeSystem:
    def __init__(self, dispatcher: EventDispatcher, player_id: str):
        self._dispatcher = dispatcher
        self._player_id = player_id
        # Subscribe to standard engine action events
        self._dispatcher.subscribe(OnActionEvent, self.on_action)

    def on_action(self, event: OnActionEvent) -> None:
        # Check if the "jump" key action has been triggered
        if event.action_name == "jump" and event.value > 0.5:
            # Broadcast our gameplay-specific event
            self._dispatcher.dispatch(JumpEvent(self._player_id, force=400.0))
```

### 3. Handling Gameplay Events in PlayerSystem
The `PlayerSystem` listens for `JumpEvent` and applies gravity:

```python
class PlayerSystem:
    def __init__(self, entity_manager: EntityManager, dispatcher: EventDispatcher):
        self._em = entity_manager
        dispatcher.subscribe(JumpEvent, self.on_jump)

    def on_jump(self, event: JumpEvent) -> None:
        entity = self._em.get_entity(event.entity_id)
        if entity and entity.has_component(Velocity):
            vel = entity.get_component(Velocity)
            # Instantly apply upward force (negative Y is up in 2D coordinate system)
            vel.value = Vector2(vel.value.x, -event.force)

    def update(self, dt: float) -> None:
        gravity = 800.0
        floor_y = 500.0

        for entity in self._em.get_entities_with(Transform, Velocity):
            trans = entity.get_component(Transform)
            vel = entity.get_component(Velocity)

            # Apply gravity acceleration to velocity
            vel.value = Vector2(vel.value.x, vel.value.y + gravity * dt)
            # Update coordinate position
            trans.position = trans.position + (vel.value * dt)

            # Simple ground alignment check
            if trans.position.y > floor_y:
                trans.position = Vector2(trans.position.x, floor_y)
                vel.value = Vector2(vel.value.x, 0)
```

---

## 🏃 Part 4: Physical Simulation (`games/physics_integration`)

For advanced simulation, PyGuara wraps the **Pymunk** rigid body library. Rather than calculating gravity manually, physical objects register `RigidBody` and `Collider` components. The `PhysicsSystem` automatically simulates rigid body calculations and mirrors the resulting coordinates back onto `Transform` components.

### 1. Attaching Physical Components
```python
from pyguara.physics.components import RigidBody, Collider
from pyguara.physics.types import BodyType, ShapeType

# Create a dynamic falling circle
ball = self.entity_manager.create_entity("ball")
ball.add_component(Transform(position=Vector2(400, 100)))
# RigidBody declares dynamic mass, friction, and moment parameters
ball.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=1.0))
# Collider sets up the geometry bounds for collision resolver
ball.add_component(Collider(shape_type=ShapeType.CIRCLE, radius=20.0))
```

### 2. Managing Static Ground Boundaries
Static physics boundaries prevent entities from falling into the void:
```python
ground = self.entity_manager.create_entity("ground")
ground.add_component(Transform(position=Vector2(400, 500)))
# Static body does not move under gravity or collisions
ground.add_component(RigidBody(body_type=BodyType.STATIC))
# Box collider bounds
ground.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[800, 40]))
```

---

## 🖥️ Part 5: UI Scene Graphs & Layouts (`games/ui_scene_graph`)

Creating buttons, health bars, and overlay dialogs requires a layout-agnostic framework to handle resolution adjustments automatically. PyGuara provides a constraint-based UI layout system.

### 1. Building responsive buttons and panels
You instantiate UI widgets, attach declarative `LayoutConstraints`, and add
the roots to the `UIManager`. The manager runs a layout pass over every root
before it draws (and again after a window resize), so a constrained element's
`position`/`size` are placeholders -- the constraints decide the final rect.

```python
from pyguara.common.types import Vector2
from pyguara.ui.manager import UIManager
from pyguara.ui.components import Panel, Button
from pyguara.ui.constraints import LayoutConstraints
from pyguara.ui.types import UIAnchor

# 1. Grab UIManager from DI Container
ui_manager = self.container.get(UIManager)

# 2. A panel covering the centre 50% x 60% of the screen.
#    position/size are placeholders; the constraint wins.
panel = Panel(Vector2(0, 0), Vector2(10, 10))
panel.constraints = LayoutConstraints(
    anchor=UIAnchor.CENTER,
    width_percent=0.5,
    height_percent=0.6,
)
ui_manager.add_element(panel)

# 3. A button centred inside the panel's content rect.
button = Button("Start Game", Vector2(0, 0))
button.constraints = LayoutConstraints(
    anchor=UIAnchor.CENTER,
    width_percent=0.3,
    height_percent=0.1,
)

def on_click(btn: Button):
    print("Transitioning to main level scene...")
    # Scene transition command (via SceneManager)

button.on_click = on_click
panel.add_child(button)
```

> If you mutate something a layout depends on after the first frame -- a
> label's text, an element's `visible` flag -- call
> `ui_manager.invalidate_layout()` so the next render re-runs the pass.

---

## 📦 Part 6: Standalone Compilation (`pyguara build`)

Once your game is complete, you will want to share it with players without requiring them to install Python or Pip. PyGuara provides a packaging utility built directly into its Command Line Interface.

### How to Compile Your Game
The `pyguara build` command compiles your entry script, copies all associated assets (like images, sound clips, and configurations), resolves external dynamic libraries, and outputs a ready-to-run folder.

```bash
# Basic directory-based build
uv run pyguara build games/guara_falcao/main.py --output dist/guara_falcao

# Compact single-executable build
uv run pyguara build games/true_coral/main.py --onefile --output dist/true_coral
```

### Build Options Reference
- `-o`, `--output`: Specifies the destination directory for the package (default: `dist/`).
- `-n`, `--name`: Changes the final binary name (defaults to the entry script's filename).
- `--onefile`: Merges all resources and Python script libraries into a single file executable.
- `--windowed`: Suppresses the OS command shell terminal console on boot (default behavior).
- `--icon`: Bundles a custom application icon (e.g. `icon.ico` for Windows or `icon.icns` for macOS).
- `-a`, `--assets`: Explicitly specifies directories containing game assets (textures, music, shaders) to package with the executable.
- `--dry-run`: Prints the PyInstaller command that would run, without building.

See [Command-Line Tools](../systems/cli.md) for the full option list and for
`pyguara atlas`, the sprite-atlas packer.

Now you have all the knowledge required to bootstrap, design, script, and publish your own 2D games using the PyGuara game engine! Keep exploring the examples under the `games/` folder to study advanced scripts, spatial audio routing, and the in-engine debug overlays.
