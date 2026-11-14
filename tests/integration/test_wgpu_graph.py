"""The render graph's passes on wgpu, against their golden images.

Each case in `_graph_frame.py` runs in a process of its own, from a known
picture, and its output is compared with the image approved for it -- the
wgpu output at the commit where every case matched ModernGL, pass by pass,
before that backend was retired. See `tests/integration/golden.py`.

Two things a case can get wrong that this catches: the arithmetic of a
shader, and the orientation. The picture has a marker in its top-left
corner so a pass that turned the image upside down cannot pass.
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
        if "could not be opened" in tail:
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
    # Colour only. A buffer's own alpha is a known, deliberate divergence:
    # GL blends alpha with the colour's factors, so drawing something
    # translucent into a buffer lowers the buffer's alpha (and the final
    # blit then lets the window's last frame through); wgpu blends alpha as
    # `one, one - src_alpha` and keeps an opaque buffer opaque. See the
    # stage D entries in `.claude/decision-log.md`.
    a8 = np.frombuffer(reference, dtype=np.uint8).reshape(-1, 4)[:, :3].astype(np.int16)
    b8 = np.frombuffer(actual, dtype=np.uint8).reshape(-1, 4)[:, :3].astype(np.int16)
    gap8 = np.abs(a8 - b8).max(axis=1)
    return int((gap8 > TOLERANCE).sum()), float(gap8.max()), a8


@pytest.mark.integration
@pytest.mark.parametrize("case", list(CASES))
def test_the_pass_matches_its_golden(
    case: str, tmp_path: Path, update_golden: bool
) -> None:
    """The wgpu output against the image approved when it matched ModernGL.

    What guards the render graph once ModernGL is gone; see
    `tests/integration/golden.py`. The tolerances are the cross-backend
    ones above, which leave room for a different GPU's rounding.
    """
    import numpy as np

    from tests.integration import golden

    actual = _run("wgpu", case, tmp_path / "wgpu.rgba")
    hdr = len(actual) == WIDTH * HEIGHT * 8
    image = np.frombuffer(actual, dtype="<f2" if hdr else np.uint8).reshape(
        HEIGHT, WIDTH, 4
    )
    if update_golden:
        golden.save("graph", case, image)
        return
    stored = golden.load("graph", case, hdr)
    assert stored is not None, golden.missing("graph", case, hdr)
    differing, largest, _ = _worst(stored.astype(image.dtype).tobytes(), actual)
    assert differing == 0, (
        f"{case}: {differing} pixels differ from the golden image, by up to "
        f"{largest}. If the change is intended, rerun with --update-golden "
        f"and review {golden.path_for('graph', case, hdr)}"
    )
