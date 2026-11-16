# PyGuara

A code-first 2D game engine. Games are written in Python 3.12+; the
renderer, window, input, audio and the hot paths are a Rust extension
that ships inside the package.

**Alpha, 0.7.0.** It runs a real game in development, and its APIs still
change between versions.

## Start here

The [README](https://github.com/Wedeueis/pyguara#install) has the install
steps. Then:

```bash
uv run python games/boot_process/main.py     # the smallest module
uv run python games/guara_falcao/main.py     # a platformer
```

- **[Onboarding](guides/ONBOARDING.md)**: the three patterns everything
  else is built from (dependency injection, protocols over backends,
  events), then each subsystem in a paragraph.
- **[Zero to Hero](guides/zero_to_hero.md)**: a walk through the tutorial
  modules in `games/`.
- **[Project Structure](guides/PROJECT_STRUCTURE.md)**: how to lay out a
  game built on the engine.
- **[Architecture & Style](guides/Archictecture & Style Guide.md)**: the
  conventions the engine's own code follows.

## Core

- **[Architecture](core/architecture.md)**: the ECS, the container and
  the event bus in one page.
- **[Entity Component System](core/ecs.md)**: indexed queries, data-only
  components, deferred removal.
- **[Dependency Injection](core/dependency-injection.md)**,
  **[Events](core/events.md)**, **[Common Types](core/common-types.md)**.
- **[Application & Lifecycle](core/application.md)**: the fixed-step loop,
  the composition root, shutdown.
- **[Scenes](core/scenes.md)**: each scene owns its world; switching,
  stacking and persistent layers.
- **[Configuration](core/configuration.md)** and
  **[Logging](core/logging.md)**.

## Rendering

**[Rendering](graphics/rendering.md)** covers both backends:

- **wgpu**, the default: sprite batching, a render graph, 2D lighting,
  post-processing and sprite materials in WGSL. It needs a GPU; without
  one, startup stops with `NoGraphicsAdapterError`.
- **pygame**, chosen with `display.backend: pygame`: a software renderer
  that runs anywhere, with no lighting or post-processing. It is the
  reference the GPU renderer is tested against.

## Physics and AI

- **[Simulation](physics/simulation.md)**: rigid bodies, colliders,
  joints and triggers through pymunk.
- **[Spatial Queries](physics/queries.md)**: raycasts and overlaps.
- **[Character Movement](physics/character-movement.md)**: the swept
  kinematic mover for players and NPCs.
- **[Intelligence](ai/intelligence.md)**: state machines, behaviour
  trees, steering, flocking, A*, flow fields and navmesh.

## Systems

- **[Input](systems/input.md)**: action mapping over keyboard, mouse and
  gamepads.
- **[Audio](systems/audio.md)**: the native mixer, buses, loops and
  streamed music.
- **[Animation](systems/animation.md)**: tweens, sprite animation and
  animation state machines.
- **[Scripting](systems/scripting.md)**: coroutines for sequential logic.
- **[Resources](systems/resources.md)**: typed, cached asset loading.
- **[Prefabs](systems/prefabs.md)**: data-driven entity templates.
- **[Persistence](systems/persistence.md)** and
  **[Replay](systems/replay.md)**: save files, and deterministic input
  recording.
- **[UI Builder](systems/ui-builder.md)** and the
  **[UI Design System](systems/ui-design-system.md)**: widgets, layout
  and the Cerrado themes.
- **[Networking](systems/networking.md)**: opt-in multiplayer with
  replication, client prediction and Steam relay hosting.
- **[Kits](kits/index.md)**: gameplay building blocks to copy and change.

## Tooling

- **[Studio](systems/studio.md)**: the editor over a running game, with
  the same operations exposed to coding agents. It needs the wgpu backend.
- **[Editor Tools](systems/editor.md)** and
  **[Dev Tools](systems/dev.md)**: the diagnostic overlay (frame timing,
  event stream, collision wireframes) and hot reload. Authoring lives in
  Studio, not in the overlay.
- **[Command-Line Tools](systems/cli.md)**: `pyguara build`, `dist`,
  `atlas`, `sounds` and `studio`.
- **[Agent Integration](guides/agent-integration.md)** and
  **[Visual Inspection](guides/agent-visual-inspection.md)**: how a
  coding agent edits a scene and checks what the engine drew.

## Measurements and decisions

- **[Measured Limits](guides/performance.md)**: every performance number,
  including the cases where native code is slower.
- **[Decision records](adr/0001-one-mutation-seam-for-studio.md)**: why
  the engine is shaped the way it is. Start with
  [0004, the native boundary](adr/0004-the-native-boundary.md), and
  [0007, the networking model](adr/0007-networking-model.md).
