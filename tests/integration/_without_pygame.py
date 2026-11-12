"""Run a wgpu demo with pygame made unimportable, for `test_wgpu_without_pygame`.

    python _without_pygame.py <demo> <frames>

Prints `RAN <n>` on success. Any `import pygame` raises, so a failure names
the module that tried.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

sys.modules["pygame"] = None  # type: ignore[assignment]
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYGUARA_WINDOW", "offscreen")


def main() -> None:
    demo, frames = sys.argv[1], int(sys.argv[2])
    from pyguara.application.application import Application
    from pyguara.events.dispatcher import EventDispatcher
    from tools.demo_list import DEMOS

    bootstrap_module, scenes_module, scene_name = DEMOS[demo]
    container = importlib.import_module(bootstrap_module).configure_game_container()
    app = container.get(Application)
    scene = getattr(importlib.import_module(scenes_module), scene_name)
    ran = 0
    original = app._render

    def render() -> None:
        nonlocal ran
        original()
        ran += 1
        if ran >= frames:
            app._is_running = False

    app._render = render  # type: ignore[method-assign]
    dispatcher = (
        container.get(EventDispatcher)
        if EventDispatcher in container._services
        else app._event_dispatcher
    )
    app.run(starting_scene=scene(dispatcher))
    print(f"RAN {ran}")


if __name__ == "__main__":
    main()
