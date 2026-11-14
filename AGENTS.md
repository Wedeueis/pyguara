# AGENTS.md

Instructions for coding agents working in this repository.

This is the canonical file. `CLAUDE.md`, `GEMINI.md` and
`.cursor/rules/pyguara.mdc` import it rather than repeating it.

**Keep it short.** It is read at the start of every session. A rule
belongs here; its reasons, numbers and history belong in the page it
points to under `docs/`.

## What this is

PyGuara is a code-first 2D game engine for Python 3.12+, with a Rust
extension for the platform layer and the hot paths. **Alpha, version
0.6.0**: it runs a real game (Reclaimer), and its APIs still change.

**This checkout is `pyguara-next`, a temporary fork.** Work lands on the
`next` branch. It merges back into `Wedeueis/pyguara` after the Steam
playtest (workstream 5e), and issues live there already. See
`project/backlog/active/next_engine_plan.md`.

## What is being worked on

| File in `project/backlog/active/` | What it holds |
| --- | --- |
| `engine_completion_roadmap.md` | **Start here.** What is left, in order |
| `next_engine_plan.md` | Workstreams 1 to 7, their measurements, and the live status of each |
| `network_multiplayer.md` | The networking plan, by phase |
| `repo_cleanup_plan.md` | What moves, is archived or is deleted at true alpha |

`REFACTOR_STATE.md` and `.scratch/engine-remediation/` record two
**finished** efforts. Do not resume either.

## Setup

```bash
uv sync            # compiles the Rust extension; needs rustup (stable)
make native        # rebuild it in place after editing Rust
```

On Linux a source build also needs `sudo apt install libudev-dev
pkg-config`. Without them: `maturin develop --release
--no-default-features`, which runs with no gamepads and a silent mixer.

`make native` is `maturin develop --release`. Plain `maturin develop` is
a debug build and slower than the Python it replaces; a bare `cargo
build` is not picked up while an installed library exists.

## Before you call something done

```bash
uv run pytest && uv run ruff check . && uv run mypy pyguara
```

All three must pass. With several commits, each must pass alone.

- `pytest -m unit`, `-m integration`, `-m performance`, `-m slow` and
  `-m cli` select by marker. The Makefile wraps the common runs; `make
  help` lists the targets.
- **The native parity suites skip when the extension is not built**, so
  a green run without it has tested none of the accelerator.
- `tests/visual/` snapshots record the renderer's call stream. Update
  with `--snapshot-update` and **read the diff**: a changed snapshot is
  a changed frame.
- Reproduce a suspected defect with a throwaway probe before fixing it,
  and keep the probe as the regression test.

## Branching

- This fork: commit to `next`. After the merge-back, every independent
  branch is cut from `main`.
- **Merge commits**, never squash or rebase-and-merge.
- **A branch is frozen once its PR is open.** Follow-up work goes on a
  new branch; check `gh pr view <branch> --json state` before pushing to
  an old one.
- Stack a branch on another only for a real dependency, and say so in
  the PR.
- Commit or push only when asked.

Reasons and the full procedure: `docs/agents/branching.md`.

## Where things are

| Path | What it is |
| --- | --- |
| `pyguara/ecs/`, `di/`, `events/` | **The core. Ask before changing these**; everything depends on them |
| `pyguara/application/` | The frame loop (`application.py`) and service wiring (`bootstrap.py`) |
| `pyguara/scene/`, `systems/` | Scenes, each owning its own `EntityManager` and `SystemManager` |
| `pyguara/graphics/` | Render pipeline; backends are `wgpu` (GPU) and `pygame` (software reference) |
| `pyguara/physics/`, `audio/`, `input/`, `ui/`, `ai/`, `animation/`, `tilemap/`, `resources/`, `persistence/`, `replay/`, `prefabs/` | Subsystems, each behind a protocol |
| `pyguara/net/` | Opt-in multiplayer: transport, replication, prediction |
| `pyguara/kits/` | Gameplay building blocks: combat, movement, loot, procgen |
| `pyguara/studio/` | The editor and the agent operation surface |
| `pyguara/native.py`, `rust/src/` | The extension loader and the Rust crate |
| `games/` | Tutorials and capstone demos. Tests use the capstones as a pixel corpus |
| `docs/adr/` | Decisions that still constrain the code. Read the relevant one first |
| `docs/guides/performance.md` | Every measured number |

ModernGL is **retired**: `display.backend: moderngl` raises at startup.
`display.backend` still defaults to `pygame`; Studio and the render
graph need `wgpu`.

## Rules the code does not enforce

The generated block below has the engine conventions. In addition:

- **Type hints everywhere**, Google-style docstrings on public API,
  absolute imports. Mypy is strict on `pyguara/`.
- **Protocols, not ABCs**, for a new interface.
- **Emit with `queue_event()` from a background thread**, never
  `dispatch()`.
- **A scene has no container until `resolve_dependencies()` has run**,
  so resolve services in `on_enter()` or later.
- **A guard must not return a plausible wrong value.** `x or 1`, `if d
  != 0 else 0` and a bare `except: pass` have each hidden a real defect
  here; raising is easier to diagnose.
- **Every performance claim carries a before and after number**, added
  to `docs/guides/performance.md`.

## Seeing and hearing the engine

An agent cannot look at a window or listen to a speaker.

```bash
uv run python tools/agent_view.py --list
uv run python tools/agent_view.py guara_falcao --frames 120 --shot 119
uv run python tools/audio_capture.py --asset <file.wav> --wav
```

Frames land in `.agent-view/`. **A capture proves the render or output
path works. It does not prove a window appeared or a speaker played**,
and those have diverged here before. See `docs/agents/capture-tools.md`
and `docs/guides/agent-visual-inspection.md` before reporting on either.

<!-- BEGIN GENERATED BY PYGUARA STUDIO -- edit outside this block -->
PyGuara is a code-first 2D game engine for Python 3.12+: an Entity-Component-System core with inverted-index queries, a reflection-based dependency-injection container, an event bus, and backend-agnostic rendering over pygame-ce and wgpu. This repository is the engine itself, not a game built on it -- `games/` holds the demos and tutorials.

## Commands

- Install dependencies: `uv sync --all-extras`
- Run the tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Type-check: `uv run mypy`

## Engine conventions

- **Components are data.** A component is a dataclass with no
  methods; behaviour lives in a system or in free functions
  beside it. `BaseComponent.__init_subclass__` raises at class
  definition time if a component declares a method.
- **Never import the rendering backend.** Game code uses the
  `IRenderer` / `UIRenderer` protocols through the DI container.
  A direct `import pygame` in game code is a layering break.
- **Query through the manager.** `entity_manager.get_entities_with(Transform, Sprite)`
  is an indexed lookup; iterating every entity and testing is not.
- **Mutating a component needs a notification.** After writing a
  field, call `entity_manager.notify_component_changed(entity_id, ComponentType)`,
  or anything mirroring it -- physics bodies, render batches, the
  spatial index -- keeps the old value.
- **One component of each type per entity.** Replacing one is a
  remove followed by an add.
- **Two kinds of parent.** `Transform` parenting is spatial;
  `ChildOf` is ownership and cascades on destroy. Set `ChildOf`
  through `entity_manager.set_parent()`, never `add_component`.
- **Fixed vs variable update.** Physics and game logic run in
  `fixed_update` at a constant rate; rendering and animation run
  in `update` at the display rate.

## Authoring through PyGuara Studio

Studio exposes the scene as a set of operations, so a scene can
be read and edited without a window. Two transports, the same
operations behind both:

```bash
# JSON lines on stdio -- no extra dependency.
pyguara studio ops

# Model Context Protocol -- needs the `studio` extra.
pyguara studio mcp
```

To wire the MCP server into an agent, point it at
`pyguara studio mcp` as a stdio server.

Working rules, which the operations themselves enforce:

- Call `project_overview` first in an unfamiliar project, then
  `scene_summary`. `scene_tree` is the full read and is large.
- Call `component_schema` before setting a field on a component
  type you have not used. It carries the field types, the
  defaults, and an enum field's valid members.
- Entities are named by id, and ids survive undo, redo and
  reload -- an id from one call still means the same entity in
  the next.
- Every edit returns the diff it produced. Check your own work
  from the reply rather than re-reading the scene.
- Every edit is undoable through `history`, and every action,
  including the failures, is in `journal`.
- An error names the alternative. A wrong component or field
  name comes back with the closest match, so correct from the
  message rather than listing everything again.
<!-- END GENERATED BY PYGUARA STUDIO -->

## The native extension

Rust implements the wgpu renderer, the window, input, images, text and
the audio mixer, plus an accelerated **store** for five things that also
keep a Python implementation: `FlowFieldService`, `ParticleSystem`,
`Sparks`, `FlockingSystem` and `SpatialHash`.

- The module is **`pyguara.pyguara_core_rs`**. `pyproject.toml` and
  `pyguara/native.py` both spell that name and must agree.
- **One engine-wide switch**: `PerformanceConfig.native_acceleration` is
  `off`, `auto` or `required`. `PYGUARA_NO_NATIVE=1` forces the Python
  stores. `pyguara.native.describe()` says which is in force.
- **That switch governs stores, not backends.** It does not reach audio
  (`PYGUARA_AUDIO_BACKEND=pygame`) or networking.
- **The two stores must agree**, and how exactly depends on the
  subsystem: the flow field and `SpatialHash` membership are bit-exact,
  the pools compare within a tolerance, flocking has one permitted cause
  of difference. Read the parity suite's docstring before touching one.
- **`SpatialHash` results have no defined order.** Pick by distance or
  id, never the first.
- **A test's reference must pin the Python store explicitly**
  (`accelerate=False`), or it compares native with itself.

Before editing anything under `rust/src/` or a two-store class, read
`docs/agents/native-extension.md` and ADR 0004.

## Networking

`pyguara.net` is opt-in and imports nothing into a single-player game.

- **Everything decoded from the network is untrusted**, including from
  an invited player. Bounds-check lengths, ids and enums, reject
  non-finite floats, never raise into the frame loop, never unpickle.
- **A host accepts commands from a client, never positions**, and one
  per tick.
- **`renet` and `renetcode` are pinned exactly**; both can be crashed
  remotely as shipped and `rust/src/net/core.rs` guards those versions.
  Run `tests/test_net_hostile.py` before moving either.
- **Do not test a stall with `time.sleep` or a Python busy loop.**
- After changing replication, capture `tools/agent_view.py net_horde`.

Details: `docs/agents/networking.md`, `docs/systems/networking.md` and
ADR 0007.
