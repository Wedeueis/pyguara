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

## Capstone Projects

### [guara_falcao](./guara_falcao) — Guará & Falcão
* **Genre:** Platformer, and the engine's **UI showcase**. A title screen, an
  in-game HUD, a pause menu and an options panel, all over a Cerrado at the
  amber hour.
* **Key Concepts:** the `pyguara.ui.design_system` Cerrado theme skinning
  every stock component; `UILayer` (the HUD on `HUD`, the menus on `OVERLAY`);
  `LayoutConstraints` anchoring each HUD cluster to a corner; the focus ring
  and Enter/Space activation; `Slider`/`Checkbox` `on_change`; a scene-stack
  pause (`push_scene(..., pause_below=True)`) that leaves the frozen game
  rendering behind a translucent scrim; and a live `set_theme()` swap between
  Cerrado Dusk and Day that re-skins everything on screen.
* **Art:** none. Every pixel of the world is a renderer primitive — see
  [`art.py`](./guara_falcao/art.py). The demo ships no textures on purpose:
  the subject is the UI, and an asset pipeline beside it would be the thing
  everyone looked at instead.
* **Run:** `uv run python games/guara_falcao/main.py`
* **Look at it headlessly:** `uv run python tools/agent_view.py guara_falcao --gl`
  (the `--gl` flag is required — SDL's dummy driver has no OpenGL at all).
  Walk the screens with
  `--click 640,314@20 --click 1199,681@60 --click 640,358@100`.

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
  and the 1-of-3 upgrade pick (the first real consumer of `UIManager`'s focus
  ring), and the shared `SpatialHash` for the tongue's target search.
* **Scale:** 700 interactive flocking insects plus a 1,400-strong decorative
  layer, in one instanced draw call. The 700 is measured, not chosen — see the
  table in `swarm.py`.
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

### [quintal_cerrado](./quintal_cerrado) — Quintal do Cerrado
* **Genre:** Cozy agroforestry. The full till → seed → water → grow →
  harvest loop, on a static 12x8 plot, viewed head-on, with a clickable
  tool bar (till, one plant tool per species, water, harvest -- every tool
  also has a keyboard shortcut, but the bar is what makes them
  discoverable). **Status: Phase 2 of 5** (see the PRD) — the core loop is
  playable end to end; the chemical-vs-organic pest fork, automation and
  real persistence land in later phases. Harvesting frees a cell to
  replant immediately but grants no currency yet -- there is no
  `PlayerEconomy` until a later phase.
* **Key Concepts:** the first real adopter of `pyguara.tilemap`
  (`Tilemap`/`TileLayer`/`Tileset`, built procedurally rather than from a
  `.tmx` — the plot is simulation state, not level art) for anything beyond
  `physics.tilemap.merge_tile_rects`; `pyguara.ui.components.canvas.Canvas`
  as a clickable world surface, reusing `UIManager`'s existing mouse
  routing instead of a second `InputManager` mouse path; the first real
  adopter of `pyguara.ai.fsm` (`State`/`StateMachine`, driven for free by
  the engine's own `AISystem`) for a plant's seedling→growing→mature→
  harvestable lifecycle; a companion-planting/shade simulation
  (`systems/shade_system.py`, `systems/syntropic_system.py`) matching the
  PRD's own example almost exactly — an understory plant only gets its
  growth bonus once an adjacent canopy tree has actually matured enough to
  cast shade; soil moisture (`systems/soil_system.py`) that evaporates
  over time and gates growth below a threshold, so watering is a real,
  revisit-worthy action rather than a cosmetic tool; a small `juice.Motes`
  particle pool (adapted from `pyguara.graphics.vfx.sparks.Sparks` for a
  camera-less, UI-drawn world) giving tilling, watering, harvesting and
  every growth-stage change its own burst-and-pop beat, plus idle sway, a
  moisture tint on the soil itself, and a pulsing "ready" ring on
  harvestable plants.
* **Art:** none. Soil tiles and plants are renderer primitives, the same
  house style as `guara_falcao`.
* **Run:** `uv run python games/quintal_cerrado/main.py`
* **Look at it headlessly:** `uv run python tools/agent_view.py quintal_cerrado`
* **Spec:** [`project/demos/quintal_do_cerrado_PRD.md`](../project/demos/quintal_do_cerrado_PRD.md)
