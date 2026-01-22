# PyGuara Engine: Developer Onboarding Guide

Welcome to the PyGuara Engine! This guide provides an in-depth overview of the engine's architecture, systems, and design patterns. Its purpose is to help new developers understand how to use the engine effectively and consistently, embracing the core philosophies that make it powerful and maintainable.

---

## 1. Core Architecture Principles

Before diving into individual systems, it's crucial to understand the three core principles that govern the entire engine. You will see these patterns everywhere.

### 1.1. Dependency Injection (DI)

*   **Architecture:** The engine is built around a central DI Container (`pyguara/di/container.py`). At startup (`main.py`), systems and managers are "registered" with this container. When a class is created, the container automatically provides (injects) the dependencies it asks for in its `__init__` method.
*   **Design Pattern (Inversion of Control):** Instead of a class creating its own dependencies (e.g., `self.resource_manager = ResourceManager()`), it declares them in its constructor (`def __init__(self, resource_manager: ResourceManager):`). This decouples the class from its dependencies, making the system modular, testable, and easier to manage.
*   **How to Use:** When creating a new `System` or `Manager`, simply add other registered systems you need as arguments to `__init__`. The DI container will handle the rest.

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

### 1.2. Backend Abstraction (Hardware Abstraction Layer - HAL)

*   **Architecture:** Systems that interact with low-level hardware or external libraries (Graphics, Physics, Audio, Input) are split into two parts:
    1.  A high-level `Manager` or `System` that game code interacts with.
    2.  A `protocol.py` file defining an interface (e.g., `IRenderer`, `IPhysicsEngine`).
    3.  A `backends/` directory containing concrete implementations of that interface (e.g., `PygameRenderer`, `PymunkEngine`).
*   **Design Pattern (Strategy/Bridge):** This decouples the engine's logic from any specific library. The `PhysicsSystem` doesn't know about "Pymunk"; it only knows about the `IPhysicsEngine` interface. This allows backends to be swapped (e.g., from Pygame to a future OpenGL renderer) without rewriting any game logic.
*   **How to Use:** Always code against the high-level `Manager` or `System` (e.g., `AudioManager`, `RenderSystem`). Never interact directly with a backend implementation.

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

1.  **Define Components:** Create new `dataclass`es in a `components.py` file for your feature.

    ```python
    from dataclasses import dataclass
    from pyguara.common.types import Vector2

    @dataclass
    class Transform:
        position: Vector2 = field(default_factory=Vector2.zero)

    @dataclass
    class PlayerInput:
        move_speed: float = 100.0
    ```

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

                # ... apply movement logic ...
    ```

3.  **Create Entities:** In your scene, get the `EntityManager` and create entities.

    ```python
    # In your GameplayScene's on_enter method
    player_entity = self.entity_manager.create_entity()
    self.entity_manager.add_component(player_entity, Transform(position=Vector2(100, 100)))
    self.entity_manager.add_component(player_entity, PlayerInput())
    self.entity_manager.add_component(player_entity, Sprite(texture=...))
    ```

---

## 3. Graphics System

*   **Location:** `pyguara/graphics/`
*   **Architecture:** A backend-agnostic, pipeline-based rendering system.
    *   **Protocols (`IRenderer`)**: Define the abstract drawing commands.
    *   **Backend (`PygameRenderer`)**: Implements the drawing commands using Pygame.
    *   **RenderSystem (`pipeline/render_system.py`)**: The main system that orchestrates the rendering process. It collects all `Renderable` objects, sorts them for 2D layering, batches them for performance, and sends them to the backend.
*   **Features:**
    *   Sprite rendering with position, rotation, and scale.
    *   Layering and Z-sorting for correct 2D depth.
    *   High-performance sprite batching (`pygame.Surface.blits`).
    *   Camera and viewport support.
    *   Basic primitive drawing (rects, circles, lines) for debugging.
*   **How to Use:**
    1.  Create an entity with a `Transform` component and a `Sprite` component. The `Sprite` component holds the texture, layer, and other render-specific data.
    2.  The `RenderSystem` (which is managed by the `SystemManager`) will automatically find and draw this entity each frame. You do not need to call a `draw` method yourself.

    ```python
    from pyguara.common.components import Transform
    from pyguara.graphics.components import Sprite

    # In a scene's on_enter method
    texture = self.resource_manager.load("sprites/my_sprite.png", Texture)
    my_entity = self.entity_manager.create_entity()
    self.entity_manager.add_component(my_entity, Transform(position=Vector2(50, 50)))
    self.entity_manager.add_component(my_entity, Sprite(texture=texture, layer=10))
    ```

---

## 4. Physics System

*   **Location:** `pyguara/physics/`
*   **Architecture:** A backend-agnostic, three-part system.
    *   **Backend (`PymunkEngine`)**: Implements the `IPhysicsEngine` protocol using the Pymunk library. It does the heavy lifting.
    *   **PhysicsSystem**: The ECS system that synchronizes data between the game world (`Transform` components) and the physics world (`Pymunk.Body`).
    *   **CollisionSystem**: Receives callbacks from the backend and dispatches high-level `OnCollisionBegin`, `OnTriggerEnter`, etc., events.
*   **Features:**
    *   Static, Kinematic, and Dynamic rigid bodies.
    *   Circle and Box colliders.
    *   Physics materials (friction, restitution).
    *   Triggers (non-solid colliders).
    *   A rich set of joints (Pin, Spring, Slider).
    *   Raycasting.
*   **How to Use:**
    1.  Add a `RigidBody` component to an entity to give it physics properties.
    2.  Add a `Collider` component to give it a physical shape.
    3.  The `PhysicsSystem` will automatically create the body in the Pymunk world.
    4.  For dynamic bodies, the `PhysicsSystem` will update the entity's `Transform` component each frame based on the simulation.

    ```python
    from pyguara.physics.components import RigidBody, Collider
    from pyguara.physics.types import BodyType, ShapeType

    # Create a dynamic, falling box
    box = self.entity_manager.create_entity()
    self.entity_manager.add_component(box, Transform())
    self.entity_manager.add_component(box, RigidBody(body_type=BodyType.DYNAMIC))
    self.entity_manager.add_component(box, Collider(shape_type=ShapeType.BOX, dimensions=[32, 32]))
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
    *   **Steering Behaviors:** For dynamic movement (seek, flee, arrive).
    *   **Pathfinding:** A* pathfinding on a navigation mesh.
*   **How to Use (Behavior Tree):**
    1.  Define simple functions that will act as your leaf nodes.
    2.  Compose these functions into a tree using `SequenceNode`, `SelectorNode`, etc.
    3.  Create a `BehaviorTree` instance with your root node.
    4.  Add an `AIComponent` to your entity and assign the tree to it.

    ```python
    from pyguara.ai.behavior_tree import BehaviorTree, ActionNode, SequenceNode, SelectorNode, NodeStatus

    def find_player(context) -> NodeStatus:
        # ... logic to find player ...
        if found:
            context.blackboard['player_pos'] = player_position
            return NodeStatus.SUCCESS
        return NodeStatus.FAILURE

    def move_towards_player(context) -> NodeStatus:
        # ... logic to move towards context.blackboard['player_pos'] ...
        if close_enough:
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING # Still moving

    # In your scene
    attack_sequence = SequenceNode([find_player, move_towards_player])
    patrol_action = ActionNode(...)
    root_node = SelectorNode([attack_sequence, patrol_action])

    tree = BehaviorTree(root=root_node)
    ai_comp = AIComponent()
    ai_comp.behavior_tree = tree # The AISystem will tick this

    my_enemy = self.entity_manager.create_entity()
    self.entity_manager.add_component(my_enemy, ai_comp)
    ```

---

## 7. Support Systems Quick Reference

The following systems provide critical infrastructure for the rest of the engine. They follow the same high-quality design patterns.

*   **Animation (`pyguara/animation`):** A powerful tweening engine for animating any numeric property over time with easing functions. Use `TweenManager` to create and manage `Tween` objects for UI effects, camera movement, etc.
*   **Input (`pyguara/input`):** A robust action-based input mapping system. Use the `InputManager` to `register_action` (e.g., "jump") and `bind_input` (e.g., spacebar to "jump"). Game code should listen for `OnActionEvent` and check the `action_name`, not for raw key presses.
*   **Persistence (`pyguara/persistence`):** A complete save/load system. Use the `PersistenceManager`'s `save_data` and `load_data` methods. It automatically handles serialization, data integrity checksums, and versioning.
*   **Resources (`pyguara/resources`):** A professional-grade asset management pipeline. Use the `ResourceManager` to `load` assets. It handles caching, type-safe loading, and automatic memory management via reference counting. The `index_directory` feature allows loading by simple name (e.g., `"player_idle"`).
*   **Scripting (`pyguara/scripting`):** A coroutine system for writing sequential, time-based logic without complex state machines. Write a generator function and use `yield` with helpers like `wait_for_seconds()` and `wait_until()`. Start it with `CoroutineManager.start_coroutine()`.
*   **Editor (`pyguara/editor`):** A powerful, live, in-game editor built with Dear ImGui. Press F12 to toggle. Provides a scene hierarchy, a component inspector that automatically reflects `dataclass` components, and scene saving/loading.
*   **Config (`pyguara/config`):** A centralized manager for `game_config.json`. It provides type-safe access to settings via the `GameConfig` dataclass, validates data on load, and fires events on changes.
*   **Error (`pyguara/error`):** A structured exception hierarchy. All engine errors inherit from `EngineException` and carry a rich `ErrorContext` object for easier debugging.
*   **Log (`pyguara/log`):** A clean configuration wrapper around Python's standard `logging` module. Use `setup_logging` once at startup, then get a logger in any module with `get_logger(__name__)`.
*   **Systems (`pyguara/systems`):** The `SystemManager` orchestrates the execution order of all ECS systems based on a priority number. Systems are registered with the manager, which then calls their `update` method in the correct order each frame.
*   **Tools (`pyguara/tools`):** The infrastructure for managing developer tools like the Editor. The `ToolManager` handles visibility, input routing, and shortcuts for all registered tools.

This guide should provide a solid foundation for getting started with the PyGuara Engine. By understanding and using these core patterns, you can build complex, maintainable, and high-performance games.
