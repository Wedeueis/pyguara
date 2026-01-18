# PyGuara Engine: Learning Path & Implementation Roadmap

**Goal:** To provide a progressive, hands-on mastery of the PyGuara architecture, moving from foundational architectural patterns to complex, genre-specific implementations.

---

## Phase 1: Foundations – "The Engine Tour"

**Objective:** Build a mental model of how PyGuara fits together. Transition the user from "Python script" thinking to "Engine Architecture" thinking.

### Module 1: The Boot Process

* **Topic:** Lifecycle & Dependency Injection.
* **Theory:** Understanding Inversion of Control (IoC). Why we don't use global variables.
* **Key Components:**
* `pyguara.di.container.DIContainer`
* `pyguara.application.application.Application`


* **Implementation Steps:**
1. **Container Setup:** Initialize `DIContainer`.
2. **Registration:** Register core services (`Window`, `EventDispatcher`, `SceneManager`) using `register_singleton`.
3. **The Entry Point:** create `main.py` and call `Application.run()`.


* **Outcome:** A window opens, initializes systems, logs startup via `logging`, and closes cleanly without errors.

### Module 2: The ECS Mental Model

* **Topic:** Data-Oriented Design in Python.
* **Theory:** Composition over Inheritance. Why `Systems` contain logic and `Components` contain data.
* **Key Components:**
* `pyguara.ecs.manager.EntityManager`
* `pyguara.ecs.query_cache.QueryCache`
* `pyguara.ecs.component.Component`


* **Implementation Steps:**
1. **Define Components:** Create `Transform(Component)` and `Sprite(Component)`.
2. **Create Systems:** Implement a `MovementSystem` that iterates over entities with `Transform`.
3. **Query Optimization:** Explain and implement `QueryCache` to avoid  lookup costs in Python.
4. **Entity Creation:** Use `EntityManager.create_entity()` to spawn a test object.


* **Outcome:** A colored square renders on screen and moves automatically across the window.

### Module 3: The Asset Pipeline

* **Topic:** Managing Resources & Metadata.
* **Theory:** The Flyweight pattern (caching) and separating import logic from raw data.
* **Key Components:**
* `pyguara.resources.manager.ResourceManager`
* **Concept:** `.meta` sidecar files.


* **Implementation Steps:**
1. **Meta Files:** Create `hero.png.meta` defining texture filters (Nearest/Linear).
2. **Loading:** Use `ResourceManager.load("hero.png", Texture)` to fetch assets.
3. **Ref Counting:** Demonstrate `acquire()` and `release()` to show automatic memory management.


* **Outcome:** The moving square is replaced by a sprite. The texture acts crisp (pixel art) due to correct meta settings.

---

## Phase 2: Core Systems – "The Toolbox"

**Objective:** Master the specific tools required to build actual gameplay mechanics.

### Module 4: Input & Events

* **Topic:** Decoupled Communication.
* **Theory:** The Observer Pattern. Preventing "Event Death Spirals" with time budgets.
* **Key Components:**
* `pyguara.events.dispatcher.EventDispatcher`
* `pyguara.input.manager.InputManager`


* **Implementation Steps:**
1. **Binding:** Map hardware keys to abstract actions: `InputMap.bind("jump", Key.SPACE)`.
2. **Dispatching:** Create a custom `JumpEvent`.
3. **Listening:** Subscribe `PlayerSystem` to `JumpEvent`.


* **Outcome:** The player sprite jumps only when the spacebar is pressed, using decoupled events rather than direct polling in the update loop.

### Module 5: Physics Integration

* **Topic:** The Pymunk Bridge & Simulation.
* **Theory:** Fixed Timesteps (`fixed_update`) vs. Variable Rendering (`update`).
* **Key Components:**
* `pyguara.physics.physics_system.PhysicsSystem`
* `pyguara.physics.components.RigidBody` (Dynamic/Kinematic)
* `pyguara.physics.components.Collider`


* **Implementation Steps:**
1. **Components:** Attach `RigidBody` and `Collider` to the hero entity.
2. **Gravity:** Configure `PhysicsSystem` gravity vector.
3. **Synchronization:** Observe how the `PhysicsSystem` automatically syncs the ECS `Transform`.


* **Outcome:** The player falls under gravity and lands on a static ground entity. Debug gizmos visualize the collision shapes.

### Module 6: UI & Scene Graph

* **Topic:** Interfaces and Layouts.
* **Theory:** The Scene Graph, Anchors, and Raycasting for input.
* **Key Components:**
* `pyguara.ui.manager.UIManager`
* `pyguara.ui.layout.BoxContainer`


* **Implementation Steps:**
1. **Layout:** Use `BoxContainer` (Vertical) to stack "Start" and "Quit" buttons.
2. **Event Routing:** Handle `OnMouseEvent` within the UI layer.
3. **Scene Switching:** Transition from `MenuScene` to `GameScene`.


* **Outcome:** A functional main menu that correctly routes clicks and transitions to the gameplay scene.

---

## Phase 3: Capstone Projects (Game Demos)

**Objective:** Stress-test the engine with complete, genre-specific production workflows.

### Demo 1: "True Coral" (Puzzle Game)

* **Genre:** Grid-based logic (Sokoban/2048 style).
* **Focus:** Logic, Sequencing, Audio.
* **Engine Features Highlight:**
* **Scripting:** heavily use `pyguara.scripting.coroutines` (`yield WaitForSeconds`) to sequence block movements.
* **Animation:** Use `Tween` for smooth sliding effects between grid cells.
* **Audio:** Manage sound effects (`AudioSystem`) via resource counting.


* **Key Challenge:** Implementing a deterministic `GridSystem` that snaps `Transform` components to integer coordinates.

### Demo 2: "Guará & Falcão" (Platformer)

* **Genre:** Metroidvania-lite.
* **Focus:** Physics, State Machines, Camera Control.
* **Engine Features Highlight:**
* **Physics:** Advanced use of `PlatformerController`, `Raycast` (ground checks), and `TriggerVolume` (zone transitions).
* **Graphics:** `Camera2D` with smoothing, deadzones, and parallax layers (`Batcher`).
* **State:** `AnimationSystem` driven by a Finite State Machine (Idle -> Run -> Jump -> Fall).


* **Key Challenge:** Implementing "Game Feel" features like Coyote Time and Jump Buffering via `InputManager`.

### Demo 3: "Protocolo Bandeira" (Top-Down Shooter)

* **Genre:** Twin-stick arena shooter.
* **Focus:** AI, Performance, Particle Systems.
* **Engine Features Highlight:**
* **AI:** `BehaviorTree` implementation with `Selector` and `Sequence` nodes (Patrol -> Chase -> Attack).
* **Rendering:** Stress-testing `ModernGL` hardware instancing with 1000+ bullets/enemies.
* **Particles:** `ParticleSystem` for explosions and trails.


* **Key Challenge:** Managing memory and Garbage Collection spikes using Object Pooling for projectiles.
