# PyGuara

A code-first 2D game engine. Games are written in Python 3.12+; the
renderer, window, input, audio and the hot paths are a Rust extension
that ships inside the package.

[![CI](https://github.com/Wedeueis/pyguara/actions/workflows/ci.yml/badge.svg)](https://github.com/Wedeueis/pyguara/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/github/license/Wedeueis/pyguara)](LICENSE)

> **Status: alpha, 0.6.0.** It runs a real game in development, and its
> APIs still change between versions. It is not on PyPI yet.
>
> **This repository is `pyguara-next`,** a temporary fork where the
> renderer, platform layer and networking were rebuilt. It merges back
> into [`Wedeueis/pyguara`](https://github.com/Wedeueis/pyguara), where
> issues already live. Work is on the `next` branch.

## What it is

Most Python game libraries give you a window and a loop and leave the
engine to you. PyGuara is the engine: an Entity-Component-System world,
scenes, a fixed-step loop, and the subsystems a 2D game needs, each
behind a protocol so a backend can be replaced without touching game
code.

It is built for desktop games: Windows, Linux and macOS. There is no
web, mobile or console target.

## What is in it

| | |
| --- | --- |
| **Core** | ECS with indexed, deterministically ordered queries; components are data-only and the engine enforces it. Scenes with their own world. A fixed-step loop with interpolated rendering. An event bus and a service container |
| **Rendering** | A GPU renderer on [wgpu](https://wgpu.rs) (DX12, Metal, Vulkan, GL): sprite batching, a render graph, 2D lighting, post-processing, sprite materials in WGSL. A software renderer on pygame-ce is kept as the reference the GPU one is tested against |
| **Platform** | Window and input on winit, gamepads on gilrs, image decoding and hinted text in Rust. The wgpu path runs without pygame |
| **Audio** | A native mixer: buses, pitch, sample-exact loop regions, streamed music with fades |
| **Physics** | Rigid bodies, joints, triggers and queries through pymunk, plus a swept character mover |
| **Gameplay** | State machines, behaviour trees, steering, flocking, A*, flow fields and navmesh. Tweens, animation state machines, coroutines. Tilemaps from Tiled and LDtk. Prefabs, save files, replays |
| **UI** | A layout engine, a widget set, a declarative builder, themes, rich text |
| **Kits** | Building blocks to copy and change: action combat, top-down and platformer movement, projectiles, loot, progression, procedural generation |
| **Multiplayer** | Opt-in. An encrypted transport on a Rust thread, replication, client prediction, and hosting through Steam's relay |
| **Tooling** | PyGuara Studio, an editor over a running game, with the same operations exposed to coding agents. `pyguara build` for a standalone executable, `pyguara dist` for Steam and itch layouts |

**Measured, not claimed.** Every performance number, including the cases
where native code is slower, is in
[docs/guides/performance.md](docs/guides/performance.md).

## Install

From source, until there is a release on PyPI. You need Python 3.12 or
3.13, [uv](https://docs.astral.sh/uv/) and a stable Rust toolchain
([rustup](https://rustup.rs)), because the install compiles the
extension.

```bash
git clone -b next https://github.com/Wedeueis/pyguara-next
cd pyguara-next
uv sync
```

On Linux, gamepad support also needs udev's headers:

```bash
sudo apt install libudev-dev pkg-config
```

Wheels for Linux (x86_64, aarch64), macOS (x86_64, arm64) and Windows
(x64) are built in CI and need no toolchain; they are not published yet.

## A first scene

```python
from dataclasses import dataclass

from pyguara.application import create_application
from pyguara.common.components import Transform
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.scene.base import Scene


@dataclass(slots=True)
class Velocity(BaseComponent):
    """Components are data. Behaviour lives in the scene or a system."""

    value: Vector2 = Vector2(0, 0)


class Game(Scene):
    def on_enter(self) -> None:
        box = self.entity_manager.create_entity()
        box.add_component(Transform(position=Vector2(100, 300)))
        box.add_component(Velocity(Vector2(120, 0)))

    def fixed_update(self, fixed_dt: float) -> None:
        for entity in self.entity_manager.get_entities_with(Transform, Velocity):
            transform = entity.get_component(Transform)
            transform.position += entity.get_component(Velocity).value * fixed_dt

    def update(self, dt: float) -> None:
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        world_renderer.clear(Color(20, 24, 32))
        for entity in self.entity_manager.get_entities_with(Transform):
            position = entity.get_component(Transform).position
            world_renderer.draw_rect(
                Rect(position.x, position.y, 32, 32), Color(240, 180, 60)
            )

    def on_exit(self) -> None:
        pass


app = create_application()
app.run(Game("game", app.container.get(EventDispatcher)))
```

Save it as a file and run it with `uv run python your_file.py`.

## See it run

`games/` holds seven tutorial modules and seven larger demos.
[games/README.md](games/README.md) lists them.

```bash
uv run python games/guara_falcao/main.py      # a platformer, on wgpu
uv run python games/vinagre_matilha/main.py   # squad tactics
uv run python tools/studio_demo.py            # a demo with Studio attached
```

## Good to know before you start

- **The default renderer is still the software one.** Set
  `display.backend` to `wgpu` for the GPU renderer; the render graph,
  lighting and Studio need it.
- **Where it has been run.** CI tests on Linux. The wgpu renderer,
  native audio, gamepads and Steam have been run by hand on Windows.
  macOS wheels build but have not been run.
- **Not there yet:** packed asset archives, localisation, crash
  reporting, a project scaffold, and an Aseprite importer.

[The roadmap](project/backlog/active/engine_completion_roadmap.md) says
what is left and in what order.

## Documentation

- [Onboarding](docs/guides/ONBOARDING.md) and
  [Zero to Hero](docs/guides/zero_to_hero.md), a tutorial through the
  modules in `games/`
- [Architecture](docs/core/architecture.md), then the pages under
  `docs/core/` and `docs/systems/`
- [Rendering](docs/graphics/rendering.md),
  [Networking](docs/systems/networking.md),
  [Studio](docs/systems/studio.md)
- [Decision records](docs/adr/): why the engine is shaped the way it is

`make docs-serve` builds the site locally.

## Working on the engine

```bash
uv run pytest && uv run ruff check . && uv run mypy
```

All three must pass. `make native` rebuilds the Rust extension after an
edit. [AGENTS.md](AGENTS.md) has the rules for contributors, human or
otherwise.

## License

MIT. See [LICENSE](LICENSE).

Developed by **Wedeueis Braz**.
