# PyGuara Engine: Developer Onboarding Guide

Welcome to the PyGuara Engine! This guide provides an in-depth overview of the engine's architecture, systems, and design patterns. Its purpose is to help new developers understand how to use the engine effectively and consistently, embracing the core philosophies that make it powerful and maintainable.

---

## 1. Core Architecture Principles

Before diving into individual systems, it's crucial to understand the three core principles that govern the entire engine. You will see these patterns everywhere.

### 1.1. Dependency Injection (DI)

*   **Architecture:** The engine is built around a central DI Container (`pyguara/di/container.py`). At startup the composition root (`pyguara/application/bootstrap.py`, reached through `create_application()`) registers every engine service with this container. When a class is created, the container automatically provides (injects) the dependencies it asks for in its `__init__` method.
*   **Design Pattern (Inversion of Control):** Instead of a class creating its own dependencies (e.g., `self.resource_manager = ResourceManager()`), it declares them in its constructor (`def __init__(self, resource_manager: ResourceManager):`). This decouples the class from its dependencies, making the system modular, testable, and easier to manage.
*   **How to Use:** When creating a new service, add the registered services it needs as arguments to `__init__`; the container handles the rest. A scene resolves services with `self.container.get(...)`, in `on_enter()` or later: a scene has no container before the engine has resolved it.

    ```python
    # Before DI: Tightly Coupled
    class MySystem:
        def __init__(self):
            # Bad: This system is permanently tied to a specific resource manager
            self.resource_manager = ResourceManager()

    # After DI: Decoupled and Testable
    class MySystem:
        def __init__(self, resource_manager: ResourceManager):
            # Good: Receives any object that acts like a ResourceManager.
            self.resource_manager = resource_manager
    ```

### 1.2. Backend Abstraction

*   **Architecture:** Systems that touch hardware or an external library (graphics, physics, audio, input) are split into:
    1.  A `protocols.py` file defining the interface (e.g., `IRenderer`, `IPhysicsEngine`, `IAudioSystem`, `IInputBackend`).
    2.  A `backends/` directory with the concrete implementations.
    3.  A high-level manager or system that game code talks to.
*   **What ships:**

    | Subsystem | Default | Alternative |
    | --- | --- | --- |
    | Rendering and window | **wgpu** and winit, in the Rust extension. Needs a GPU | **pygame**, a software renderer (`display.backend: pygame`). No lighting or post-processing |
    | Input | `NativeInputBackend` (winit, gamepads on gilrs) with wgpu | `PygameInputBackend` with pygame |
    | Audio | The native mixer | pygame's mixer (`PYGUARA_AUDIO_BACKEND=pygame`) |
    | Physics | pymunk (`PymunkEngine`) | none |

    On a machine with no usable GPU the default renderer stops at startup with `NoGraphicsAdapterError`. It does not switch to the software renderer, because the two look different.
*   **Design Pattern (Strategy/Bridge):** The `PhysicsSystem` does not know about pymunk; it knows `IPhysicsEngine`. The same game code runs on either renderer.
*   **How to Use:** Code against the protocol or the manager (`IRenderer`, `AudioManager`, `InputManager`), resolved from the container. Never import a backend, and never `import pygame` in game code.

### 1.3. Event-Driven Communication

*   **Architecture:** The engine uses a global `EventDispatcher` (`pyguara/events/dispatcher.py`) to allow systems to communicate without direct references to each other.
*   **Design Pattern (Observer/Pub-Sub):** One system "dispatches" an event, and other systems can "subscribe" to that type of event.
*   **How to Use:** When a significant event occurs, dispatch an event instead of calling another system directly. For example, the `CollisionSystem` dispatches an `OnCollisionBegin` event; it does not know what a "Player" or "ScoreSystem" is. The `ScoreSystem` can then subscribe to `OnCollisionBegin` and update the score if needed.

    ```python
    # In your system/scene that needs to react to events
    def __init__(self, event_dispatcher: EventDispatcher):
        self.event_dispatcher = event_dispatcher
        self.event_dispatcher.subscribe(OnCollisionBegin, self.on_collision)

    def on_collision(self, event: OnCollisionBegin):
        print(f"Collision between {event.entity_a} and {event.entity_b}!")
    ```

---

## 2. The Entity-Component-System (ECS) Framework

*   **Location:** `pyguara/ecs/`
*   **Architecture:** PyGuara uses a high-performance ECS architecture.
    *   **Entity:** A simple ID. It is not an object; it is just a number that "owns" a collection of components.
    *   **Component:** Pure data. A component is a `dataclass` that holds data, but no logic (e.g., `Transform`, `RigidBody`).
    *   **System:** Pure logic. A system contains all the logic that operates on entities possessing a certain set of components (e.g., `PhysicsSystem` operates on entities with `Transform` and `RigidBody`).
*   **Design Pattern (Composition over Inheritance):** Instead of creating a `Player` class that inherits from `GameObject`, you create an entity and compose it by adding components: `Transform`, `Sprite`, `PlayerInput`, `Health`.

### How to Use

1.  **Define Components:** Create dataclasses in a `components.py` file for your feature.

    ```python
    from dataclasses import dataclass

    from pyguara.common.types import Vector2
    from pyguara.ecs.component import BaseComponent

    @dataclass(slots=True)
    class Velocity(BaseComponent):
        value: Vector2 = Vector2(0, 0)

    @dataclass(slots=True)
    class PlayerInput(BaseComponent):
        move_speed: float = 100.0
    ```

    A component inherits from `BaseComponent` and declares no methods; the
    class raises `TypeError` at definition time if it does. `Transform`
    already exists, in `pyguara.common.components`.

2.  **Create Systems:** Create a class that operates on entities with those components.

    ```python
    class PlayerMovementSystem:
        def __init__(self, entity_manager: EntityManager):
            self.entity_manager = entity_manager

        def update(self, dt: float):
            # Query for all entities that have BOTH Transform and PlayerInput
            for entity in self.entity_manager.get_entities_with(Transform, PlayerInput):
                transform = entity.get_component(Transform)
                player_input = entity.get_component(PlayerInput)

                # ... apply movement logic, then tell the engine the
                # component changed, or anything mirroring it keeps the
                # old value:
                self.entity_manager.notify_component_changed(entity.id, Transform)
    ```

    Register it on the scene, which owns its own `SystemManager`:
    `self.system_manager.register(PlayerMovementSystem(self.entity_manager), priority=500)`.
    Each scene also owns its own `EntityManager`; there is no global one.

3.  **Create Entities:** In your scene, get the `EntityManager` and create entities.

    ```python
    # In your GameplayScene's on_enter method
    player_entity = self.entity_manager.create_entity()
    player_entity.add_component(Transform(position=Vector2(100, 100)))
    player_entity.add_component(PlayerInput())
    player_entity.add_component(Sprite(texture=...))
    ```

---

## 3. Graphics System

*   **Location:** `pyguara/graphics/`
*   **Architecture:** A backend-agnostic, pipeline-based rendering system.
    *   **Protocols (`IRenderer`, `UIRenderer`)**: The drawing commands game code uses.
    *   **Backends**: `wgpu` (the default, GPU) and `pygame` (software, the reference the pixel tests compare against).
    *   **RenderSystem (`pipeline/render_system.py`)**: One per scene. It collects the submitted renderables, sorts them for 2D layering, batches them and sends them to the backend.
    *   **RenderGraph (`pipeline/graph.py`)**: The multi-pass pipeline on wgpu: world, light, composite, post-process, final.
*   **Features:**
    *   Sprite rendering with position, rotation, scale and per-sprite tint.
    *   Layering, Z-sorting and Y-sorting for 2D depth.
    *   Sprite batching: one draw call per batch on wgpu.
    *   Camera and viewport support.
    *   Primitive drawing (rects, circles, lines, polygons).
    *   On wgpu only: 2D lighting, post-processing (bloom, vignette and others) and sprite materials in WGSL. On pygame the same calls are accepted and the scene renders fully lit with no effects.
*   **How to Use:**
    1.  Create an entity with a `Transform` and a `Sprite`. The `Sprite` holds the texture, layer and other render data.
    2.  The scene's default `render()` submits every visible `Sprite` each frame. Override `render()` only to add manual draws, and call `super().render(...)` first.

    ```python
    from pyguara.common.components import Transform
    from pyguara.graphics.components import Sprite
    from pyguara.resources.manager import ResourceManager
    from pyguara.resources.types import Texture

    # In a scene's on_enter method
    resources = self.container.get(ResourceManager)
    texture = resources.load("sprites/my_sprite.png", Texture)
    my_entity = self.entity_manager.create_entity()
    my_entity.add_component(Transform(position=Vector2(50, 50)))
    my_entity.add_component(Sprite(texture=texture, layer=10))
    ```

    See `docs/graphics/rendering.md` for lighting, materials and the render graph.

---

## 4. Physics System

*   **Location:** `pyguara/physics/`
*   **Architecture:** A backend-agnostic, three-part system.
    *   **Backend (`PymunkEngine`)**: Implements the `IPhysicsEngine` protocol using the Pymunk library. It does the heavy lifting.
    *   **PhysicsSystem**: The ECS system that synchronizes data between the game world (`Transform` components) and the physics world (`Pymunk.Body`).
    *   **CollisionSystem**: Receives callbacks from the backend and dispatches high-level `OnCollisionBegin`, `OnTriggerEnter`, etc., events.
*   **Features:**
    *   Static, Kinematic, and Dynamic rigid bodies, with per-body sleeping.
    *   Circle and Box colliders; one-way (pass-through) platforms.
    *   Physics materials (friction, restitution).
    *   Triggers (non-solid colliders).
    *   A rich set of joints (Pin, Spring, Slider).
    *   Spatial queries: `raycast` / `raycast_all`, `point_query`,
        `overlap_box` / `overlap_box_all`, `overlap_circle`, `region_query`.
    *   `CharacterMover` / `CharacterBody` for kinematic character control
        (see `docs/physics/character-movement.md`).
*   **How to Use:**
    1.  Add a `RigidBody` component to an entity to give it physics properties.
    2.  Add a `Collider` component to give it a physical shape.
    3.  The `PhysicsSystem` will automatically create the body in the Pymunk world.
    4.  For dynamic bodies, the `PhysicsSystem` will update the entity's `Transform` component each frame based on the simulation.
    5.  For a player or NPC, prefer `CharacterBody` driven by `CharacterMover`
        instead of a dynamic `RigidBody` — it gives responsive, non-bouncy
        movement with ground/wall probes. See
        `docs/physics/character-movement.md`.

    `PhysicsSystem` is not registered by `bootstrap.py`; a scene creates it
    and calls `PhysicsSystem.update()` (or routes it through the
    `SystemManager`) itself.

    ```python
    from pyguara.physics.components import RigidBody, Collider
    from pyguara.physics.types import BodyType, ShapeType

    # Create a dynamic, falling box
    box = self.entity_manager.create_entity()
    box.add_component(Transform())
    box.add_component(RigidBody(body_type=BodyType.DYNAMIC))
    box.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[32, 32]))
    ```

---

## 5. UI System

*   **Location:** `pyguara/ui/`
*   **Architecture:** A powerful, retained-mode, constraint-based UI framework.
    *   **UIManager:** Manages the UI tree, processes input, and orchestrates rendering.
    *   **UIElement:** The base class for all UI components. Provides a state machine (normal, hover, pressed), event handling, and layout hooks.
    *   **Components:** A rich library of widgets (`Button`, `Panel`, `Slider`, etc.).
    *   **Layout & Constraints:** A declarative system for positioning and sizing elements using anchors, margins, and percentages. This is the heart of the UI system's power.
    *   **Theming:** A centralized theme file (`theme.py`) defines colors, fonts, and styles, allowing for easy reskinning.
*   **Features:**
    *   Full suite of standard UI widgets.
    *   Stateful components with automatic state changes on interaction.
    *   Declarative, responsive layout system that avoids manual pixel positioning.
    *   Centralized styling and theming.
*   **How to Use:**
    1.  Get the `UIManager` from the DI container.
    2.  Instantiate UI components, setting their text, size, etc.
    3.  Define layout rules using `LayoutConstraints`.
    4.  Assign callbacks to interaction events like `on_click`.
    5.  Add the element to the `UIManager`.

    ```python
    from pyguara.common.types import Vector2
    from pyguara.ui.components import Button
    from pyguara.ui.constraints import create_centered_constraints

    def on_my_button_click(button: Button):
        print("Button clicked!")

    # In a scene's on_enter method
    ui_manager = self.container.get(UIManager)

    my_button = Button(text="Click Me", position=Vector2(0,0)) # Position is controlled by layout
    my_button.constraints = create_centered_constraints(width_percent=0.2, height_percent=0.1)
    my_button.on_click = on_my_button_click

    ui_manager.add_element(my_button)
    ```

---

## 6. AI System

*   **Location:** `pyguara/ai/`
*   **Architecture:** A suite of high-level AI tools integrated into the ECS.
    *   **AISystem:** The main ECS system that ticks the AI components.
    *   **AIComponent:** A component that holds the AI logic for an entity (e.g., an FSM or a Behavior Tree instance).
*   **Features:**
    *   **Finite State Machines (FSMs):** For simple, state-based AI.
    *   **Behavior Trees (BTs):** A professional-grade BT implementation for complex, hierarchical AI logic. Includes all standard node types (Sequence, Selector, Parallel, Decorators).
    *   **Steering Behaviors:** For dynamic movement. `SteeringSystem` drives
        an entity's `SteeringAgent` each frame; `behavior` is a
        `SteeringBehaviorType` (`SEEK`, `ARRIVE`, `FLEE`, `WANDER`, `PURSUIT`,
        `EVADE`). `PURSUIT`/`EVADE` lead a moving target, so keep
        `SteeringAgent.target_velocity` up to date alongside `target`.
    *   **Pathfinding:** A generic A* solver (`AStarPathfinder`) over any
        `Graph`, a concrete `GridGraph` with heuristics and path smoothing, and
        a polygon `NavMesh` (`NavMeshPathfinder` returns polygon-center
        waypoints; funnel string-pulling is not yet implemented).
*   **How to Use (Behavior Tree):**
    1.  Define simple functions that will act as your leaf nodes.
    2.  Compose these functions into a tree using `SequenceNode`, `SelectorNode`, etc.
    3.  Create a `BehaviorTree` instance with your root node.
    4.  Add an `AIComponent` to your entity and assign the tree to it.

    Leaf callables receive the tick `context`. Under `AISystem` that is an
    `AIContext` with `.entity`, `.dt`, and `.blackboard` -- pass `dt` on,
    because `WaitNode` (and any timing node) reads `context.dt`.

    ```python
    from pyguara.ai import AIComponent
    from pyguara.ai.behavior_tree import (
        ActionNode, BehaviorTree, ConditionNode, NodeStatus, SelectorNode, SequenceNode,
    )

    def find_player(context) -> NodeStatus:
        # ... logic to find player ...
        if found:
            context.blackboard.set("player_pos", player_position)
            return NodeStatus.SUCCESS
        return NodeStatus.FAILURE

    def move_towards_player(context) -> NodeStatus:
        target = context.blackboard.get("player_pos")
        # ... move using context.dt ...
        if close_enough:
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING  # Still moving

    def patrol(context) -> NodeStatus:
        return NodeStatus.RUNNING

    # In your scene: leaves must be wrapped in ActionNode/ConditionNode.
    attack_sequence = SequenceNode([
        ActionNode(find_player),
        ActionNode(move_towards_player),
    ])
    root_node = SelectorNode([attack_sequence, ActionNode(patrol)])

    ai_comp = AIComponent(behavior_tree=BehaviorTree(root=root_node))

    my_enemy = self.entity_manager.create_entity()
    my_enemy.add_component(ai_comp)  # AISystem ticks it each frame
    ```

---

## 7. Support Systems Quick Reference

The following systems provide critical infrastructure for the rest of the engine. They follow the same high-quality design patterns.

*   **Animation (`pyguara/animation`):** A tweening engine for animating any numeric property over time with easing functions (`TweenManager`, `Tween`), plus sprite animation clips and animation state machines.
*   **Audio (`pyguara/audio`):** A native mixer with buses, pitch, sample-exact loop regions and streamed music with fades. Use `AudioManager` from the container, or an `AudioSource` component on an entity.
*   **Input (`pyguara/input`):** A robust action-based input mapping system. Use the `InputManager` to `register_action` (e.g., "jump") and `bind_input` (e.g., spacebar to "jump"). Game code should listen for `OnActionEvent` and check the `action_name`, not for raw key presses.
*   **Persistence (`pyguara/persistence`):** A complete save/load system. Use the `PersistenceManager`'s `save_data` and `load_data` methods. It automatically handles serialization, data integrity checksums, and versioning.
*   **Resources (`pyguara/resources`):** A professional-grade asset management pipeline. Use the `ResourceManager` to `load` assets. It handles caching, type-safe loading, and automatic memory management via reference counting. The `index_directory` feature allows loading by simple name (e.g., `"player_idle"`).
*   **Scripting (`pyguara/scripting`):** A coroutine system for writing sequential, time-based logic without complex state machines. Write a generator function and use `yield` with helpers like `wait_for_seconds()` and `wait_until()`. Start it with `CoroutineManager.start_coroutine()`.
*   **Developer overlay (`pyguara/tools`):** An in-game *diagnostic* overlay drawn on the engine's own `UIRenderer`, so it runs on every backend. Press **F12** to toggle it, then **F1** frame timing, **F3** the event stream, **F4** collision wireframes, **F8** the help table. It reports; it does not author — selecting entities, editing components, dragging transform handles, editing the config and browsing resources used to live here and are now PyGuara Studio's, which has an undo stack and an audit journal to put them on. Studio needs the wgpu backend, so **on the Pygame backend this overlay is all there is**; `docs/systems/editor.md` has the whole trade, and #330 records the two capabilities Studio has not rebuilt yet.
*   **Config (`pyguara/config`):** A centralized manager for `config/game_config.json`. It provides type-safe access to settings via the `GameConfig` dataclass, validates data on load, and fires events on changes.
*   **Errors (`pyguara/errors.py`):** `ErrorHandlingStrategy` (`RAISE`, `LOG`, `IGNORE`) is the one policy for what happens when user-supplied code raises, shared by `EventDispatcher` and `DIContainer`. Each subsystem defines its own exceptions next to its code (for example `pyguara/di/exceptions.py`).
*   **Log (`pyguara/log`):** A wrapper around Python's standard `logging` that adds categories and structured fields. Get a logger in any module with `get_logger(__name__)`; `default_log_manager.configure(...)` sets level and outputs, and the bootstrap calls it for you from the config.
*   **Systems (`pyguara/systems`):** Each scene's `SystemManager` runs its systems in ascending priority order, calling `update` each frame. The engine's own systems use 100 to 399; register game systems at 500 or above.
*   **Tools infrastructure (`pyguara/tools`):** The `ToolManager` handles visibility, input routing, and keyboard shortcuts for every registered `Tool`. `SandboxApplication` registers the overlay above; a game can register its own `Tool` subclasses too.

*   **Prefabs (`pyguara/prefabs`):** Data-driven entity templates with inheritance and children. Every scene has a `prefab_factory`.
*   **Tilemaps (`pyguara/tilemap`):** Loaders for Tiled (`.tmx`) and LDtk, with collision rectangles merged from solid tiles.
*   **Replay (`pyguara/replay`):** Deterministic input recording and playback.
*   **Kits (`pyguara/kits`):** Opt-in gameplay building blocks: action combat, top-down and platformer movement, projectiles, loot, progression, procedural generation. Nothing in the core imports a kit.
*   **Networking (`pyguara/net`):** Opt-in multiplayer: an encrypted transport, replication, client prediction and Steam relay hosting. A single-player game imports none of it. See `docs/systems/networking.md`.
*   **Studio (`pyguara/studio`):** The editor over a running game, with the same operations exposed to coding agents over `pyguara studio ops` and `pyguara studio mcp`. See `docs/systems/studio.md`.
*   **Native extension (`pyguara/native.py`, `rust/src/`):** The Rust crate behind the wgpu renderer, the window, input, images, text and the mixer. It also holds `FlowFieldService`'s field and the `Sparks` pool, which have no Python implementation, and accelerates three things that keep one: `ParticleSystem`, `FlockingSystem` and `SpatialHash`. `PerformanceConfig.native_acceleration` (`off`, `auto`, `required`) picks between them, and `pyguara.native.describe()` says which is in force.

Every measured performance number is in `docs/guides/performance.md`, and the decisions that still constrain the code are in `docs/adr/`.
