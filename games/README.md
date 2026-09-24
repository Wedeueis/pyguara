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
  rendering behind a translucent scrim; a live `set_theme()` swap between
  Cerrado Dusk and Day that re-skins everything on screen; and the only
  **sprite animation** in the demo set — the guará is an `Animator` under an
  `AnimationStateMachine` with a clip per movement state, the falcão a plain
  `Animator` with one looping clip and nothing to decide
  ([`animation.py`](./guara_falcao/animation.py)).
* **Art:** the two characters are sprites; the world is not. Sky, mounds,
  trees, platforms and fruit are all renderer primitives — see
  [`art.py`](./guara_falcao/art.py) — and their look comes from layering,
  palette and light. The character frames are cut out of the project's
  contact sheet once by
  [`tools/slice_spritesheet.py`](../tools/slice_spritesheet.py), which keys
  the backdrop to alpha and stands every frame on one shared canvas, and
  checked in as PNGs; the demo loads files and knows nothing about sheets.
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
  feedback layer, hit-stop, behaviour-tree enemy AI, **single-agent A***
  (`pyguara.ai.pathfinding`) routing a chaser around the termite mounds
  when it cannot see the player — line-of-sight first, a cached path only
  when something is in the way — `kits/projectiles`,
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
  harvest loop on a static 12x8 plot, plus the PRD's **agroecological
  dilemma**: a pest outbreak arrives once the plot is established, and you
  answer it with slow, cheap, organic **compost** (keeps the 2.0x organic
  sale premium) or a fast, expensive chemical **spray** (clears it at
  once and grows the crop faster, but sells for 0.5x, degrades the soil
  and marks every plant it reaches for good). The game is **turn-based**: a day is the
  turn, nothing in the simulation moves while you are in one, and
  **stamina** (12 a day, spent per action) is what makes a day finite.
  Sleeping resolves the night — growth, drying, pests, the machines, the
  sky — and opens a **morning report** of what happened while you slept.
  A run also has a **calendar**: twelve days are three four-day spells of
  the Cerrado's own two seasons — dry, wet, dry — and the season decides
  what the sky can do (no rain at all in the *seca*, no cold front in the
  *águas*) and which crops sell 25% above the market rate.
  An icon dock names every tool, its price, its stamina cost and its
  keyboard shortcut. A **store** (a scene pushed over the
  frozen garden) sells a four-step automation tech tree — solar panel →
  drip irrigation → soil sensor → harvester drone — each unlocked by
  *placing* the one before it, and each doing its work overnight. The
  garden **saves and resumes** — every night, and whenever you leave it
  (which includes closing the window) — through `pyguara.persistence`; the
  title offers Continue / New Garden, Esc opens a pause menu, and a
  **twelve-day** session ends in an **evaluation**: an Agroecological Score
  from soil health, biodiversity, revenue and how much of it was sold
  organically. **Status: complete** (all five phases of the PRD).
* **Key Concepts:** the first real adopter of `pyguara.tilemap`
  (`Tilemap`/`TileLayer`/`Tileset`, built procedurally rather than from a
  `.tmx` — the plot is simulation state, not level art);
  `pyguara.ui.components.canvas.Canvas` as a clickable world surface,
  reusing `UIManager`'s existing mouse routing; the first real adopter of
  `pyguara.ai.fsm` (`State`/`StateMachine`, driven for free by the
  engine's own `AISystem`) in **two** places — each plant's
  seedling→growing→mature→harvestable lifecycle (with `infested`/`dying`
  branches, since `AIComponent` has one FSM slot), and a singleton
  `garden_conditions` machine (`stable → outbreak → resolved_* → stable`)
  that paces outbreaks; a companion-planting/shade simulation
  (`systems/shade_system.py`, `systems/syntropic_system.py`) matching the
  PRD's own example — an understory plant only gets its bonus once an
  adjacent canopy tree has matured enough to cast shade; a pest simulation
  (`systems/pest_system.py`) where pressure spreads between plants (faster
  through a monoculture), decays with organic matter, dies off without a
  host, and is suppressed by a grown Pequi; soil moisture that evaporates
  and gates growth; the first real adopter of `pyguara.persistence` by any
  demo (`persistence_schema.py`) — the serializer does not round-trip
  dataclasses, so the payload is hand-built plain data, and loading is
  *parse, then apply* so a corrupt or hand-edited save is refused without
  ever half-loading the plot; a turn loop (`turn.py`,
  `systems/day_resolver.py`) where the simulation runs only when the player
  sleeps, in a few sub-steps so the non-linear pest maths and the plant
  FSMs stay honest; a two-season calendar (`seasons.py`) that re-weights
  the same six weather conditions and prices each crop's own harvest
  window, rolled *per day ahead* so a forecast crossing a season boundary
  shows the season it will land in; a hover cell inspector built from stock
  `ProgressBar`s; the automation tree (`structures.py`,
  `systems/automation_system.py`), where one solar panel powers three
  devices handed out in placement order, drip irrigation fills its cells overnight
  so they are never dry in the morning, a sensor prints
  moisture/humus/pest bars on the tiles it reaches, and a drone sells a
  couple of ready crops a night through the same
  `economy.sell_harvest` the harvest tool uses; a small economy (`economy.py`, `treatments.py`) where
  seeds and treatments cost Sementes and a harvest pays them back; and a
  `juice.Motes`/`juice.FloatingLabels` pair (adapted from
  `pyguara.graphics.vfx.sparks.Sparks` and `floating_text.FloatingText` for
  a camera-less, UI-drawn world) giving every action its own burst, plus
  idle sway, moisture/degradation tints on the soil, crawling pest marks,
  a red outbreak flash and a pulsing "ready" ring on harvestable plants.
* **Art:** none. Soil tiles and plants are renderer primitives, the same
  house style as `guara_falcao`.
* **Run:** `uv run python games/quintal_cerrado/main.py`
* **Look at it headlessly:** `uv run python tools/agent_view.py quintal_cerrado`
* **Spec:** [`project/demos/quintal_do_cerrado_PRD.md`](../project/demos/quintal_do_cerrado_PRD.md)
