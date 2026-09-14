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

* **Guará & Falcão** (Platformer)

## Capstone Projects

### [vinagre_matilha](./vinagre_matilha) — Vinagre: Matilha
* **Genre:** Real-time squad tactics. Lead a bush-dog pack running a jaguar down a riverbed.
* **Key Concepts:** boid flocking (`FlockingSystem`), shared-blackboard behaviour trees, flow-field navigation, `TriggerVolume` currents and a pack-weighted pressure plate, `kits/action_combat`.
* **Run:** `uv run python games/vinagre_matilha/main.py`
* **Spec:** [`project/demos/vinagre_matilha_GDD.md`](../project/demos/vinagre_matilha_GDD.md)

### [mourisco_ressonancia](./mourisco_ressonancia) — Mourisco: Ressonância
* **Genre:** Stealth exploration in a pitch-black cave, lit only by echolocation.
* **Key Concepts:** the **ModernGL** backend and the full lighting pipeline
  (`WorldPass → LightPass → PulsePass → CompositePass → PostProcessPass → FinalPass`),
  a custom wavefront-ring shader, DDA ray occlusion, `kits/echolocation`.
* **Run:** `uv run python games/mourisco_ressonancia/main.py`
* **Look at it headlessly:** `uv run python tools/agent_view.py mourisco_ressonancia --gl`
  (the `--gl` flag is required — SDL's dummy driver has no OpenGL at all)
* **Spec:** [`project/demos/mourisco_ressonancia_GDD.md`](../project/demos/mourisco_ressonancia_GDD.md)

### [protocolo_bandeira](./protocolo_bandeira) — Protocolo Bandeira
* **Genre:** Twin-stick wave arena. A giant anteater holds a cerrado clearing against a swarm.
* **Key Concepts:** the **ModernGL** backend with lighting and post-processing
  (`WorldPass → LightPass → CompositePass → PostProcessPass → FinalPass`), the
  engine's `HeatHazeEffect` shader for the afternoon shimmer and its dust, an
  HDR light map, `Sparks`/`Shaker`/`FloatingText`/`ScreenFlash` for the
  feedback layer, hit-stop, behaviour-tree enemy AI, `kits/projectiles`,
  `kits/action_combat`, `kits/spawn` and `ecs/pool` for the waves.
* **Run:** `uv run python games/protocolo_bandeira/main.py`
* **Look at it headlessly:** `uv run python tools/agent_view.py protocolo_bandeira --gl`
  (the `--gl` flag is required — SDL's dummy driver has no OpenGL at all)

### [tamandua_murundus](./tamandua_murundus) — Tamanduá: O Guardião dos Murundus
* **Genre:** Horde survivor / density showcase. A giant anteater holds one
  cerrado clearing from dusk to dawn against a rising swarm.
* **Key Concepts:** the **ModernGL** backend with lighting and post-processing
  (`WorldPass → LightPass → CompositePass → PostProcessPass → FinalPass`),
  **per-instance sprite tint** on the GL sprite path (one texture, N colours,
  one draw call), the **ambient day/night cycle**, a genuine `SPOT` light for
  the anteater's cone and `flicker_enabled` mounds, `kits/progression` for XP
  and the 1-of-3 upgrade pick, and the shared `SpatialHash` for the tongue's
  target search.
* **Run:** `uv run python games/tamandua_murundus/main.py`
* **Look at it headlessly:** `uv run python tools/agent_view.py tamandua_murundus --gl`
  (the `--gl` flag is required — SDL's dummy driver has no OpenGL at all)
* **Spec:** [`project/demos/tamandua_murundus_GDD.md`](../project/demos/tamandua_murundus_GDD.md)

### [true_coral](./true_coral) — True Coral
* **Genre:** Snake, on a rain-soaked forest floor at night.
* **Key Concepts:** the **ModernGL** backend with lighting and post-processing
  (`WorldPass → LightPass → CompositePass → PostProcessPass → FinalPass`),
  the engine's `StormEffect` shader driving rain and forked lightning, an HDR
  light map, `kits/trail` for the body, `kits/action_combat` for lives,
  `kits/stats` + `kits/effects` for the star's speed boost, `kits/loot` and
  `kits/spawn` for the prey.
* **Run:** `uv run python games/true_coral/main.py`
* **Look at it headlessly:** `uv run python tools/agent_view.py true_coral --gl`
  (the `--gl` flag is required — SDL's dummy driver has no OpenGL at all)
* **Spec:** [`project/demos/true_coral_GDD.md`](../project/demos/true_coral_GDD.md)
