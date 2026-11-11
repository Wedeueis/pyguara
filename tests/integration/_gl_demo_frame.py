"""Capture one frame of a demo on a chosen backend. Run as a script.

    python tests/integration/_gl_demo_frame.py <moderngl|wgpu> <demo> <out_dir>

`test_wgpu_gl_demos.py` runs this once per backend, each in a process of
its own. It drives `tools/agent_view.py`, with three things pinned so the
two backends draw the same moment of the same scene:

- the backend, set after the demo's own configure, which chooses one;
- the clock, at 1/60 s, since demos move by elapsed time and the two
  backends' headless frames take different times;
- every unseeded `RandomStream`, at seed 0 -- `true_coral`'s storm is
  unseeded by design.

ModernGL needs a real GL context, so it runs under SDL's offscreen driver
(`--gl`); wgpu runs under the dummy driver and copies its frame out.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

FRAME = 39


def main() -> None:
    """Capture the frame and exit."""
    backend, demo, out = sys.argv[1], sys.argv[2], sys.argv[3]
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from pyguara.common import random as engine_random
    from pyguara.graphics.backends.pygame.clock import PygameClock

    PygameClock.tick = lambda self, target_fps=0: 1000.0 / 60.0  # type: ignore[method-assign]
    seeded = engine_random.RandomStream.__init__

    def seed_zero(self: object, seed: int | None = None) -> None:
        seeded(self, 0 if seed is None else seed)  # type: ignore[arg-type]

    engine_random.RandomStream.__init__ = seed_zero  # type: ignore[method-assign]

    from pyguara.application import bootstrap
    from pyguara.config.types import RenderingBackend

    create = bootstrap.create_container

    def forced(configure=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        def wrapped(config):  # type: ignore[no-untyped-def]
            if configure is not None:
                configure(config)
            config.display.backend = RenderingBackend(backend)

        return create(wrapped, *args, **kwargs)

    bootstrap.create_container = forced  # type: ignore[assignment]
    sys.argv = [
        "tools/agent_view.py",
        demo,
        "--frames",
        str(FRAME + 1),
        "--shot",
        str(FRAME),
        "--out",
        out,
        *(["--gl"] if backend == "moderngl" else []),
    ]
    runpy.run_path("tools/agent_view.py", run_name="__main__")


if __name__ == "__main__":
    main()
