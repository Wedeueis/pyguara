# PyGuara Showcase & Tutorials

This directory contains the iterative tutorial series and future capstone projects.

## Tutorial Series (The Learning Path)

These modules correspond to the "Tutorial Series Roadmap".

### [boot_process](./boot_process) - Module 1: The Boot Process
* **Goal:** Initialize the engine and open a window.
* **Key Concepts:** `DIContainer`, `Application`, Lifecycle.
* **Status:** ✅ Implemented
* **Run:** `uv run python games/boot_process/main.py`

### [ecs_mental_model](./ecs_mental_model) - Module 2: The ECS Mental Model
* **Goal:** Render a moving square using Components and Systems.
* **Key Concepts:** `EntityManager`, `Component`, `System`, `QueryCache`.
* **Status:** ✅ Implemented
* **Run:** `uv run python games/ecs_mental_model/main.py`

### [asset_pipeline](./asset_pipeline) - Module 3: The Asset Pipeline
* **Goal:** Load sprites with metadata and render them.
* **Key Concepts:** `ResourceManager`, `Texture`, `.meta` files.
* **Status:** ✅ Implemented
* **Run:** `uv run python games/asset_pipeline/main.py`

### [input_events](./input_events) - Module 4: Input & Events
* **Goal:** Bind keys to actions and trigger game logic via events.
* **Key Concepts:** `InputManager`, `OnActionEvent`, `EventDispatcher`.
* **Status:** ✅ Implemented
* **Run:** `uv run python games/input_events/main.py`

### [physics_integration](./physics_integration) - Module 5: Physics Integration
* **Goal:** Simulate gravity and collision.
* **Key Concepts:** `PhysicsSystem`, `RigidBody`, `Collider`, `fixed_update`.
* **Status:** ✅ Implemented
* **Run:** `uv run python games/physics_integration/main.py`

### [ui_scene_graph](./ui_scene_graph) - Module 6: UI & Scene Graph
* **Goal:** Create a main menu with buttons and scene transitions.
* **Key Concepts:** `UIManager`, `BoxContainer`, `SceneManager`.
* **Status:** ✅ Implemented
* **Run:** `uv run python games/ui_scene_graph/main.py`

## Future Capstone Projects

* **True Coral** (Puzzle)
* **Guará & Falcão** (Platformer)
* **Protocolo Bandeira** (Shooter)
