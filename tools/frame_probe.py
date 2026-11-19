"""Where each demo's frame goes, and how much of it is building sprites.

    uv run python tools/frame_probe.py                 # every demo
    uv run python tools/frame_probe.py net_horde --frames 600

Boots a demo headlessly on the wgpu renderer, runs it uncapped with the
engine's own `FrameProfiler`, and also times the base `Scene.render`: the
sprite loop, the sort, the batching and the hand-over to the GPU, which is
the part drawing from columns replaces. Prints means over the frames after
a warm-up, in milliseconds, and the sprites submitted per frame.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.demo_list import DEMO_ROOT, DEMOS, load_demo  # noqa: E402

WARM_UP = 60


def probe(demo: str, frames: int) -> dict[str, float]:
    """Run one demo and return its mean phase times and sprite figures."""
    from pyguara.application.application import Application
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.graphics.pipeline.render_system import RenderSystem
    from pyguara.scene.base import Scene

    configure, scene_class = load_demo(demo)
    container = configure()
    app = container.get(Application)

    sprite_time = 0.0
    submitted = 0
    original_render = Scene.render
    original_submit = RenderSystem.submit

    def timed_render(self: Scene, *args: Any) -> None:
        nonlocal sprite_time
        start = time.perf_counter()
        original_render(self, *args)
        sprite_time += time.perf_counter() - start

    def counted_submit(self: RenderSystem, *args: Any, **kwargs: Any) -> None:
        nonlocal submitted
        submitted += 1
        original_submit(self, *args, **kwargs)

    Scene.render = timed_render  # type: ignore[method-assign]
    RenderSystem.submit = counted_submit  # type: ignore[method-assign]

    tick = 0
    totals = {"sprites_ms": 0.0, "sprites_per_frame": 0.0}
    original_frame_render = app._render

    def render_and_count() -> None:
        nonlocal tick, sprite_time, submitted
        tick += 1
        app._target_fps = 0  # read from config when `run()` starts
        sprite_time, submitted = 0.0, 0
        original_frame_render()
        if tick > WARM_UP:
            totals["sprites_ms"] += sprite_time * 1e3
            totals["sprites_per_frame"] += submitted
        if tick >= frames + WARM_UP:
            app._is_running = False

    app._render = render_and_count  # type: ignore[method-assign]
    profiler = app.enable_frame_profiler(visible=False)
    dispatcher = (
        container.get(EventDispatcher)
        if EventDispatcher in container._services
        else app._event_dispatcher
    )
    try:
        app.run(starting_scene=scene_class(dispatcher))
    finally:
        Scene.render = original_render  # type: ignore[method-assign]
        RenderSystem.submit = original_submit  # type: ignore[method-assign]

    stats = profiler.stats()
    result = {key: value / frames for key, value in totals.items()}
    if stats is not None:
        for phase in stats.phases:
            result[phase.name] = phase.mean_ms
        result["work"] = stats.work_mean_ms
    return result


def main() -> None:
    """Probe the named demo, or every demo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("demo", nargs="?")
    parser.add_argument("--frames", type=int, default=300)
    arguments = parser.parse_args()
    os.chdir(DEMO_ROOT)
    demos = [arguments.demo] if arguments.demo else list(DEMOS)
    header = f"{'demo':<22}{'work':>8}{'fixed':>8}{'update':>8}{'render':>8}{'sprites':>9}{'count':>8}"
    print(header)
    for demo in demos:
        try:
            row = probe(demo, arguments.frames)
        except Exception as error:  # noqa: BLE001 - one demo failing is a row
            print(f"{demo:<22}failed: {type(error).__name__}: {error}")
            continue
        print(
            f"{demo:<22}{row.get('work', 0):8.2f}{row.get('fixed', 0):8.2f}"
            f"{row.get('update', 0):8.2f}{row.get('render', 0):8.2f}"
            f"{row['sprites_ms']:9.3f}{row['sprites_per_frame']:8.0f}",
            flush=True,
        )


if __name__ == "__main__":
    main()
