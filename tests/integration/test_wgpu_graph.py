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
from typing import Any

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


# An HDR buffer is compared in its own units. Half floats carry about three
# decimal digits, and two GPUs evaluating `pow` and `smoothstep` round
# differently in the last of them: 1% of the value, or 0.004 near zero,
# which is a little over one 8-bit step.
HDR_ABSOLUTE = 0.004
HDR_RELATIVE = 0.01


def _worst(reference: bytes, actual: bytes) -> tuple[int, float, Any]:
    """How many pixels differ beyond tolerance, the largest gap, and the image."""
    import numpy as np

    if len(reference) == WIDTH * HEIGHT * 8:
        a = np.frombuffer(reference, dtype="<f2").reshape(-1, 4).astype(np.float32)
        b = np.frombuffer(actual, dtype="<f2").reshape(-1, 4).astype(np.float32)
        gap = np.abs(a - b)
        bad = (gap > HDR_ABSOLUTE + HDR_RELATIVE * np.abs(a)).any(axis=1)
        return int(bad.sum()), float(gap.max()), a
    a8 = np.frombuffer(reference, dtype=np.uint8).reshape(-1, 4).astype(np.int16)
    b8 = np.frombuffer(actual, dtype=np.uint8).reshape(-1, 4).astype(np.int16)
    gap8 = np.abs(a8 - b8).max(axis=1)
    return int((gap8 > TOLERANCE).sum()), float(gap8.max()), a8


@pytest.mark.integration
@pytest.mark.parametrize("case", list(CASES))
def test_the_pass_matches_moderngl(case: str, tmp_path: Path) -> None:
    import numpy as np

    reference = _run("moderngl", case, tmp_path / "gl.rgba")
    actual = _run("wgpu", case, tmp_path / "wgpu.rgba")

    assert len(reference) == len(actual)
    assert len(reference) in (WIDTH * HEIGHT * 4, WIDTH * HEIGHT * 8)
    differing, largest, image = _worst(reference, actual)
    # Not a blank pass compared with a blank pass.
    assert len(np.unique(image, axis=0)) > 20, f"{case} drew almost nothing"
    assert differing == 0, f"{case}: {differing} pixels differ, by up to {largest}"
