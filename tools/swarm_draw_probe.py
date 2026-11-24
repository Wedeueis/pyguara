"""Drawing and animating a horde: entities through `Scene.render`, or a swarm.

    uv run python tools/swarm_draw_probe.py                  # 10,000 ants
    uv run python tools/swarm_draw_probe.py --ants 5000 --frames 600

Boots the engine headlessly on the wgpu renderer with Correição's
configuration and ant art, once per way, each in a fresh process. The ants
stand still, scattered so about a fifth are on screen, facing their
headings and walking their two-frame clip, so both ways draw the same
picture. `entities` is a `Transform`, `Sprite` and `Animator` per ant,
drawn by the base `Scene.render` and advanced by `AnimationSystem`;
`swarm` is one `Swarm` kind with a `SwarmLook`, submitted before the base
render. Means in milliseconds per frame: drawing is from the scene's render
call to the hand-over to the GPU, animation is `AnimationSystem.update`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGUARA_WINDOW", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SETTLE_FRAMES = 60
WAYS = ("entities", "swarm")


def probe(way: str, ants: int, frames: int) -> dict[str, float]:
    """Run one way and return its mean costs per frame."""
    from examples.correicao.bootstrap import configure_game_container
    from examples.correicao.scenes import ASSETS
    from pyguara.ai.swarm import Swarm, SwarmKind, SwarmLook
    from pyguara.application.application import Application
    from pyguara.common.components import Transform
    from pyguara.common.random import RandomStream
    from pyguara.common.types import Vector2
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.graphics.animation_system import AnimationSystem
    from pyguara.graphics.components.animation import (
        AnimationClip,
        Animator,
        add_clip,
        play_clip,
    )
    from pyguara.graphics.components.sprite import Sprite
    from pyguara.resources.manager import ResourceManager
    from pyguara.resources.types import Texture
    from pyguara.scene.base import Scene

    container = configure_game_container()
    app = container.get(Application)
    totals = {"drawing": 0.0, "animation": 0.0}

    class _Probe(Scene):
        def on_enter(self) -> None:
            assert self.container is not None and self.camera is not None
            resources = self.container.get(ResourceManager)
            walk = tuple(
                resources.load(f"{ASSETS}/ant_{i}.png", Texture)  # type: ignore[type-abstract]
                for i in range(2)
            )
            self.camera.position = Vector2(0, 0)
            # A square about five screens in area, centred on the camera.
            half = math.sqrt(5 * 1280 * 720) / 2
            rng = RandomStream(11)
            points = [
                Vector2(rng.uniform(-half, half), rng.uniform(-half, half))
                for _ in range(ants)
            ]
            headings = [rng.uniform(0, math.tau) for _ in range(ants)]
            self.swarm: Swarm | None = None
            if way == "swarm":
                swarm = Swarm(cell_size=26.0)
                kind = swarm.add_kind(SwarmKind(max_speed=0.0))
                swarm.set_look(
                    kind,
                    SwarmLook(frames=walk, frame_rate=9.0, layer=10, face_heading=True),
                )
                swarm.spawn(
                    kind,
                    points,
                    [Vector2(math.cos(h), math.sin(h)) for h in headings],
                )
                self.swarm = swarm
                return
            self.animation = AnimationSystem(self.entity_manager, EventDispatcher())
            for point, heading in zip(points, headings, strict=True):
                entity = self.entity_manager.create_entity()
                entity.add_component(Transform(position=point))
                sprite = Sprite(
                    texture=walk[0], layer=10, rotation=math.degrees(heading)
                )
                entity.add_component(sprite)
                animator = Animator(sprite)
                add_clip(
                    animator,
                    AnimationClip(name="walk", frames=list(walk), frame_rate=9.0),
                )
                play_clip(animator, "walk")
                entity.add_component(animator)

        def on_exit(self) -> None:
            pass

        def update(self, dt: float) -> None:
            if self.swarm is not None:
                self.swarm.update(dt)  # advances the clip clock; no agent moves
                return
            start = time.perf_counter()
            self.animation.update(dt)
            totals["animation"] += time.perf_counter() - start

        def render(self, world_renderer: Any, ui_renderer: Any) -> None:
            start = time.perf_counter()
            if self.swarm is not None:
                assert self.render_system is not None
                self.swarm.submit(self.render_system)
            super().render(world_renderer, ui_renderer)
            totals["drawing"] += time.perf_counter() - start

    scene = _Probe("probe", container.get(EventDispatcher))
    drawn = 0
    original_render = app._render

    def render_and_count() -> None:
        nonlocal drawn
        app._target_fps = 0
        original_render()
        drawn += 1
        if drawn == SETTLE_FRAMES:
            for key in totals:
                totals[key] = 0.0
        if drawn >= SETTLE_FRAMES + frames:
            app._is_running = False

    app._render = render_and_count  # type: ignore[method-assign]
    app.run(starting_scene=scene)
    return {key: value * 1e3 / frames for key, value in totals.items()}


def main() -> None:
    """Probe each way in its own process, and print one row per way."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ants", type=int, default=10000)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--one", choices=WAYS, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.one:
        print(json.dumps(probe(args.one, args.ants, args.frames)))
        return

    print(f"{'way':<10}{'drawing':>10}{'animation':>11}")
    for way in WAYS:
        output = subprocess.run(
            [sys.executable, __file__, "--one", way, "--ants", str(args.ants)]
            + ["--frames", str(args.frames)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        row = json.loads(output.strip().splitlines()[-1])
        print(f"{way:<10}{row['drawing']:>10.2f}{row['animation']:>11.2f}")


if __name__ == "__main__":
    main()
