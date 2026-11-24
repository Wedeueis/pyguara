"""Where a horde's frame goes, at several horde sizes.

    uv run python tools/horde_probe.py                       # 1,000, 5,000, 10,000
    uv run python tools/horde_probe.py --ants 2000 --frames 600

Boots the Correição demo headlessly on the wgpu renderer, once per size,
each in a fresh process. The calango walks its autopilot loop, so every run
sees the same world. Once the raid is full and has settled, it times each
frame's phases with the engine's `FrameProfiler`, and inside them the parts
a horde costs: building the sprites (`Scene.render`, through the sort and
the batching to the GPU), the flock, the animators and the combat pass.
It also counts the sprites submitted and how many of them were on screen.
Means in milliseconds: per frame for the frame, its render and the sprite
building, per fixed tick for the tick and the systems inside it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.demo_list import load_demo  # noqa: E402

SETTLE_FRAMES = 240
# Per frame: the whole frame's work, its render phase, the sprite building
# inside it, the sprites submitted and how many were on screen, and how many
# fixed ticks the frame ran. Per tick: a fixed tick, and the three systems
# inside it a horde costs. A slow frame runs several ticks to catch up, so
# per tick is what a change to a system moves.
COLUMNS = (
    "work",
    "render",
    "sprites",
    "submitted",
    "on_screen",
    "ticks",
    "tick",
    "flock",
    "animation",
    "combat",
)
SYSTEMS = ("flock", "animation", "combat")


def _timed(
    owner: type, name: str, totals: dict[str, float], calls: dict[str, int], key: str
) -> Any:
    """Wrap `owner.name` so each call adds its duration to `totals[key]`."""
    original = getattr(owner, name)

    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            totals[key] += time.perf_counter() - start
            calls[key] += 1

    setattr(owner, name, wrapper)
    return original


def probe(ants: int, frames: int) -> dict[str, float]:
    """Run the raid at `ants` and return its mean costs per frame."""
    from examples.correicao.bootstrap import SCREEN_HEIGHT, SCREEN_WIDTH
    from examples.correicao.systems import CombatSystem
    from pyguara.ai.flocking_system import FlockingSystem
    from pyguara.application.application import Application
    from pyguara.application.frame_profile import FrameProfiler
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.graphics.animation_system import AnimationSystem
    from pyguara.graphics.pipeline.render_system import RenderSystem
    from pyguara.scene.base import Scene

    configure, scene_class = load_demo("correicao")
    container = configure()
    app = container.get(Application)
    scene = scene_class(container.get(EventDispatcher), ants=ants)

    totals = dict.fromkeys(("sprites", "submitted", "on_screen", *SYSTEMS), 0.0)
    calls = dict.fromkeys(totals, 0)
    _timed(Scene, "render", totals, calls, "sprites")
    _timed(FlockingSystem, "update", totals, calls, "flock")
    _timed(AnimationSystem, "update", totals, calls, "animation")
    _timed(CombatSystem, "update", totals, calls, "combat")

    half_w, half_h = SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2
    original_submit = RenderSystem.submit

    def counted_submit(self: RenderSystem, item: Any, position: Any = None) -> None:
        totals["submitted"] += 1
        where = position if position is not None else item.position
        centre = scene.player.position
        if abs(where.x - centre.x) <= half_w and abs(where.y - centre.y) <= half_h:
            totals["on_screen"] += 1
        original_submit(self, item, position)

    RenderSystem.submit = counted_submit  # type: ignore[method-assign]

    since_full = 0
    measured = 0
    profiler: FrameProfiler | None = None
    original_render = app._render

    def render_and_measure() -> None:
        nonlocal since_full, measured, profiler
        app._target_fps = 0  # read from config when `run()` starts
        original_render()
        if profiler is not None:
            measured += 1
            if measured >= frames:
                app._is_running = False
            return
        if scene.spawner is not None and scene.spawner.alive >= ants:
            since_full += 1
        if since_full >= SETTLE_FRAMES:
            for key in totals:
                totals[key] = 0.0
                calls[key] = 0
            profiler = app.enable_frame_profiler(visible=False)

    app._render = render_and_measure
    app.run(starting_scene=scene)

    assert profiler is not None
    stats = profiler.stats()
    assert stats is not None
    ticks = calls["flock"]
    phases = {phase.name: phase.mean_ms for phase in stats.phases}
    result = {
        "work": stats.work_mean_ms,
        "render": phases["render"],
        "sprites": totals["sprites"] * 1e3 / frames,
        "submitted": totals["submitted"] / frames,
        "on_screen": totals["on_screen"] / frames,
        "ticks": ticks / frames,
        "tick": phases["fixed"] * frames / ticks,
    }
    for key in SYSTEMS:
        result[key] = totals[key] * 1e3 / ticks
    return result


def main() -> None:
    """Probe each size in its own process, and print one row per size."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ants", type=int, nargs="+", default=[1000, 5000, 10000])
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--one", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.one:
        print(json.dumps(probe(args.ants[0], args.frames)))
        return

    print("ants    " + "".join(f"{name:>13}" for name in COLUMNS))
    for ants in args.ants:
        output = subprocess.run(
            [sys.executable, __file__, "--one", "--ants", str(ants)]
            + ["--frames", str(args.frames)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        row = json.loads(output.strip().splitlines()[-1])
        print(
            f"{ants:<8}" + "".join(f"{row.get(name, 0.0):>13.2f}" for name in COLUMNS)
        )


if __name__ == "__main__":
    main()
