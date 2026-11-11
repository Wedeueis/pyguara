"""The heat haze's ground heat is where its `horizon` says: below it.

`horizon` runs from 0.0 at the top of the frame to 1.0 at the bottom, and
heat builds from it downwards, towards the ground. The shader read GL's
`v_uv.y`, which runs up from the bottom, so for as long as the effect
existed the heat built towards the *top* of the frame instead -- found
porting it to WGSL, where both conventions have to be spelled out.

Measured through the sun glow alone, since that is the shader's `ground`
term made visible: no refraction, no dust.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color
from pyguara.graphics.pipeline.device import ModernGLDevice
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.vfx.effects.heat_haze import HeatHazeEffect

pytestmark = pytest.mark.integration

_WIDTH, _HEIGHT = 32, 64


def glow_by_row(gl_ctx: Any, horizon: float) -> np.ndarray:
    """Return how much the haze brightened each row, top row first."""
    manager = FramebufferManager(gl_ctx, _WIDTH, _HEIGHT)
    source = manager.get_or_create("_haze_in", dtype="f1")
    target = manager.get_or_create("_haze_out", dtype="f1")
    try:
        source.clear(Color(60, 60, 60, 255))
        target.clear(Color(0, 0, 0, 255))
        effect = HeatHazeEffect(haze=0.0, horizon=horizon, dust=0.0, sun=1.0)
        effect.apply(ModernGLDevice(gl_ctx), source, target)
        raw = np.frombuffer(target.fbo.read(components=3), dtype=np.uint8)
        # GL rows run bottom-up; flipped so row 0 is the top of the frame.
        image = np.flipud(raw.reshape((_HEIGHT, _WIDTH, 3))).astype(int)
        return (image - 60).mean(axis=(1, 2))
    finally:
        manager.release_all()


def test_above_the_horizon_the_ground_term_is_zero(gl_ctx: Any) -> None:
    glow = glow_by_row(gl_ctx, horizon=0.5)

    assert np.abs(glow[: _HEIGHT // 2 - 1]).max() <= 1


def test_the_heat_builds_towards_the_bottom(gl_ctx: Any) -> None:
    glow = glow_by_row(gl_ctx, horizon=0.5)

    assert glow[-1] > 5
    assert glow[-1] > glow[_HEIGHT * 3 // 4] > glow[_HEIGHT // 2]
