"""Render one demo and write its last frame as raw RGB. Run as a script.

    python tests/integration/_demo_frame.py <demo> <out.rgb>

The backend is whatever `PYGUARA_BACKEND` names. `test_wgpu_demos.py` runs
this once per backend, each in a process of its own, because the wgpu
device and the ModernGL tests' OpenGL context cannot share one.

**The clock is pinned to 1/60 s.** Every demo moves by elapsed time, and
the wgpu backend's headless frames are slower than pygame's (each is read
back from the GPU), so on a real clock the two backends draw different
moments of the same scene. The first comparison of `ecs_mental_model`
found its hero 4 px apart for exactly that reason.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))


def main() -> None:
    """Render the demo named on the command line and write its frame."""
    import pygame

    from pyguara.application.clock import WallClock
    from pyguara.graphics.backends.pygame.clock import PygameClock

    # Both backends' wall clocks, pinned: each frame is exactly 1/60 s.
    for clock in (PygameClock, WallClock):
        clock.tick = lambda self, target_fps=0: 1000.0 / 60.0  # type: ignore[method-assign]

    import test_demos_render

    demo, out = sys.argv[1], sys.argv[2]
    surface = test_demos_render.render_demo(demo)
    width, height = surface.get_size()
    Path(out).write_bytes(
        width.to_bytes(4, "little")
        + height.to_bytes(4, "little")
        + pygame.image.tobytes(surface, "RGB")
    )


if __name__ == "__main__":
    main()
