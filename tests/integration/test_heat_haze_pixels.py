"""The heat haze's ground heat is where its `horizon` says: below it.

`horizon` runs from 0.0 at the top of the frame to 1.0 at the bottom, and
heat builds from it downwards, towards the ground. The shader read GL's
`v_uv.y`, which runs up from the bottom, so for as long as the effect
existed the heat built towards the *top* of the frame instead -- found
porting it to WGSL, where both conventions had to be spelled out. The
WGSL still computes in that y-up convention, so its noise matches what
was approved; this pins the direction on top of it.

Measured through the sun glow alone, since that is the shader's `ground`
term made visible: no refraction, no dust.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color
from pyguara.graphics.pipeline.device import WgpuDevice
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.vfx.effects.heat_haze import HeatHazeEffect

pytestmark = pytest.mark.integration

_WIDTH, _HEIGHT = 32, 64


def glow_by_row(wgpu_frame: Any, horizon: float) -> np.ndarray:
    """Return how much the haze brightened each row, top row first."""
    frame = wgpu_frame(_WIDTH, _HEIGHT)
    manager = FramebufferManager(WgpuDevice(frame), _WIDTH, _HEIGHT)
    source = manager.get_or_create("_haze_in", dtype="f1")
    target = manager.get_or_create("_haze_out", dtype="f1")
    try:
        source.clear(Color(60, 60, 60, 255))
        target.clear(Color(0, 0, 0, 255))
        effect = HeatHazeEffect(haze=0.0, horizon=horizon, dust=0.0, sun=1.0)
        effect.apply(WgpuDevice(frame), source, target)
        frame.gpu.end_frame()
        raw = np.frombuffer(target.read_rgba(), dtype=np.uint8)
        image = raw.reshape((_HEIGHT, _WIDTH, 4))[..., :3].astype(int)
        return (image - 60).mean(axis=(1, 2))
    finally:
        manager.release_all()


def test_above_the_horizon_the_ground_term_is_zero(wgpu_frame: Any) -> None:
    glow = glow_by_row(wgpu_frame, horizon=0.5)

    assert np.abs(glow[: _HEIGHT // 2 - 1]).max() <= 1


def test_the_heat_builds_towards_the_bottom(wgpu_frame: Any) -> None:
    glow = glow_by_row(wgpu_frame, horizon=0.5)

    assert glow[-1] > 5
    assert glow[-1] > glow[_HEIGHT * 3 // 4] > glow[_HEIGHT // 2]
