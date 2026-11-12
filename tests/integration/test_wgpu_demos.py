"""Every demo the pygame backend draws, the wgpu backend draws the same.

`test_wgpu_pixels.py` holds the renderer to pygame one call at a time. This
holds it to pygame over whole frames of real games: each demo is rendered
on both backends and the frames compared, every pixel within 2/255.

A frame is only comparable if the scene is in the same state, so each
render pins the clock (see `_demo_frame.py`) and runs with a fixed hash
seed. The pygame frame is rendered twice, and a demo whose two pygame
frames differ fails as unreproducible, rather than being compared and
blamed on the renderer.

The demos built on the render graph -- lighting, post-processing -- are not
here. That is stage D of `project/backlog/active/next_engine_plan.md`; the
wgpu backend registers the same stand-in graph as pygame until then.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.test_demos_render import DEMOS_THAT_DRAW
from tests.integration.test_wgpu_graph_demos import GRAPH_DEMOS

# The demos that run on pygame. Those built on the render graph choose wgpu
# themselves, so both runs here would draw on wgpu and agree trivially; they
# are held to their golden frames in `test_wgpu_graph_demos.py` instead.
PYGAME_DEMOS = sorted(set(DEMOS_THAT_DRAW) - set(GRAPH_DEMOS))

_SCRIPT = Path(__file__).with_name("_demo_frame.py")

# Two renderers blending in floats and in bytes round differently by one.
TOLERANCE = 2


def _frame(demo: str, backend: str, out: Path) -> tuple[int, int, bytes]:
    """Render `demo` on `backend` in a fresh interpreter and read its frame."""
    completed = subprocess.run(  # noqa: S603 - our own interpreter and script
        [sys.executable, str(_SCRIPT), demo, str(out)],
        capture_output=True,
        text=True,
        timeout=300,
        env={
            **os.environ,
            "SDL_VIDEODRIVER": "dummy",
            "SDL_AUDIODRIVER": "dummy",
            "PYGUARA_BACKEND": backend,
            "PYTHONHASHSEED": "0",
        },
        check=False,
    )
    if completed.returncode != 0:
        tail = completed.stderr[-3000:]
        if backend == "wgpu" and "graphics device could not be opened" in tail:
            pytest.skip(f"no graphics adapter for wgpu: {tail.splitlines()[-1]}")
        raise AssertionError(f"{demo} on {backend} failed:\n{tail}")
    data = out.read_bytes()
    width = int.from_bytes(data[:4], "little")
    height = int.from_bytes(data[4:8], "little")
    return width, height, data[8:]


def _differing(first: bytes, second: bytes) -> int:
    """Count pixels whose channels differ by more than `TOLERANCE`."""
    import numpy as np

    a = np.frombuffer(first, dtype=np.uint8).reshape(-1, 3).astype(np.int16)
    b = np.frombuffer(second, dtype=np.uint8).reshape(-1, 3).astype(np.int16)
    return int((np.abs(a - b).max(axis=1) > TOLERANCE).sum())


@pytest.mark.integration
@pytest.mark.parametrize("demo", PYGAME_DEMOS)
def test_the_demo_draws_the_same_frame_on_wgpu(demo: str, tmp_path: Path) -> None:
    """The wgpu frame matches the pygame frame of the same demo."""
    reference = _frame(demo, "pygame", tmp_path / "pygame.rgb")
    again = _frame(demo, "pygame", tmp_path / "pygame-again.rgb")
    assert _differing(reference[2], again[2]) == 0, (
        f"{demo} draws a different frame each run on pygame alone, so a "
        f"difference on wgpu could not be told from it"
    )

    drawn = _frame(demo, "wgpu", tmp_path / "wgpu.rgb")
    assert drawn[:2] == reference[:2], "the frames are not the same size"
    differing = _differing(reference[2], drawn[2])
    assert differing == 0, (
        f"{demo}: {differing} pixels differ from the pygame frame. Reproduce "
        f"with tests/integration/_demo_frame.py on each backend"
    )
