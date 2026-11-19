"""Run a wgpu demo with pygame made unimportable, for `test_wgpu_without_pygame`.

    python _without_pygame.py <demo> <frames>

Prints `RAN <n>` on success. Any `import pygame` raises, so a failure names
the module that tried.
"""

from __future__ import annotations

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
    from tools.demo_list import DEMO_ROOT, load_demo

    configure, scene = load_demo(demo)
    os.chdir(DEMO_ROOT)
    container = configure()
    app = container.get(Application)
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
