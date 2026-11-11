"""The render graph's passes on wgpu, against the same passes on ModernGL.

pygame has no render graph, so for everything the graph does -- compositing,
lighting, post-processing -- ModernGL is the only reference there is. Each
case in `_graph_frame.py` runs once per backend, each in its own process,
from the same picture, and the outputs are compared.

Two things a case can get wrong that this catches: the arithmetic of the
shader port, and the orientation. GL's texture rows run bottom-up and
wgpu's top-down, so a WGSL port that copied a GLSL shader's use of `y`
literally would come out upside down. The picture has a marker in its
top-left corner for that reason.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration._graph_frame import CASES, HEIGHT, WIDTH

_SCRIPT = Path(__file__).with_name("_graph_frame.py")

# A blend in floats on one side and in bytes on the other rounds differently.
TOLERANCE = 2


def _run(backend: str, case: str, out: Path) -> bytes:
    completed = subprocess.run(  # noqa: S603 - our own interpreter and script
        [sys.executable, str(_SCRIPT), backend, case, str(out)],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "SDL_VIDEODRIVER": "dummy"},
        check=False,
    )
    if completed.returncode != 0:
        tail = completed.stderr[-3000:]
        if "could not be opened" in tail or "create_standalone_context" in tail:
            pytest.skip(f"no {backend} device here: {tail.splitlines()[-1]}")
        raise AssertionError(f"{case} on {backend} failed:\n{tail}")
    return out.read_bytes()


def _worst(reference: bytes, actual: bytes) -> tuple[int, int]:
    """How many pixels differ by more than `TOLERANCE`, and the largest gap."""
    import numpy as np

    a = np.frombuffer(reference, dtype=np.uint8).reshape(-1, 4).astype(np.int16)
    b = np.frombuffer(actual, dtype=np.uint8).reshape(-1, 4).astype(np.int16)
    gap = np.abs(a - b).max(axis=1)
    return int((gap > TOLERANCE).sum()), int(gap.max())


@pytest.mark.integration
@pytest.mark.parametrize("case", list(CASES))
def test_the_pass_matches_moderngl(case: str, tmp_path: Path) -> None:
    reference = _run("moderngl", case, tmp_path / "gl.rgba")
    actual = _run("wgpu", case, tmp_path / "wgpu.rgba")

    assert len(reference) == len(actual) == WIDTH * HEIGHT * 4
    differing, largest = _worst(reference, actual)
    assert differing == 0, f"{case}: {differing} pixels differ, by up to {largest}"
