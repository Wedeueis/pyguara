"""Real-GL pixel readback for the bloom composite's tonemap.

The chain is 16-bit float end to end (`pipeline/buffers.py`), so an
additive bloom genuinely leaves values above 1.0 at the composite -- a 2.0
scene pixel comes out near 4.0. Until the tonemap was re-enabled nothing
brought them back: `FinalPass` blits to an 8-bit target and hard-clips
every one of them to flat white, so the brightest part of the frame lost
all its detail at exactly the moment the bloom was meant to be doing
something.

That is invisible to a mock -- `test_bloom_effect.py` counts GL objects
against a `MagicMock` and cannot see a single pixel -- and invisible to a
test that reads back through an 8-bit buffer, because the clip has already
happened by then. So this renders the real composite pass into a real `f2`
framebuffer and reads floats out of it.

Two properties, and the second is the load-bearing one:

- below the knee, the curve is the identity, so anything lit against the
  old clamped pipeline is untouched;
- above it, two different over-bright inputs stay *distinguishable* and
  both land under 1.0. A hard clip satisfies "under 1.0" and fails
  "distinguishable", which is the whole defect.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from pyguara.graphics.pipeline.buffers import HDR_DTYPE
from pyguara.graphics.pipeline.framebuffer import Framebuffer, FramebufferManager
from pyguara.graphics.vfx.effects.bloom import BloomEffect

pytestmark = pytest.mark.integration

_SIZE = 8

# `bloom_composite.frag`'s own constant. Duplicated rather than imported
# because it lives in GLSL; if one moves and the other does not, the
# identity test below is what notices.
_KNEE = 0.8


@pytest.fixture
def composite(
    gl_ctx: Any,
) -> Iterator[tuple[Any, BloomEffect, Framebuffer, Framebuffer]]:
    """A bloom effect between two HDR framebuffers of its own."""
    manager = FramebufferManager(gl_ctx, _SIZE, _SIZE)
    manager.declare("_tonemap_in", dtype=HDR_DTYPE)
    manager.declare("_tonemap_out", dtype=HDR_DTYPE)
    source = manager.get_or_create("_tonemap_in")
    target = manager.get_or_create("_tonemap_out")
    effect = BloomEffect(gl_ctx, manager, threshold=0.8, intensity=1.0, blur_passes=1)
    try:
        yield gl_ctx, effect, source, target
    finally:
        effect.release()
        manager.release_all()


def _composite_of(
    scene: tuple[Any, BloomEffect, Framebuffer, Framebuffer], value: float
) -> float:
    """Fill the source with `value`, run bloom, read the centre back.

    Args:
        scene: The fixture's context, effect and framebuffers.
        value: The flat linear value to fill every scene channel with.

    Returns:
        The red channel of the composited centre pixel, as a float -- read
        out of the `f2` target, so before any 8-bit clip.
    """
    ctx, effect, source, target = scene
    source.bind()
    ctx.clear(value, value, value, 1.0)
    target.bind()
    ctx.clear(0.0, 0.0, 0.0, 1.0)

    effect.apply(ctx, source, target)

    raw = np.frombuffer(target.fbo.read(components=4, dtype="f4"), dtype="f4")
    return float(raw.reshape((_SIZE, _SIZE, 4))[_SIZE // 2, _SIZE // 2][0])


@pytest.mark.parametrize("value", [0.25, 0.5])
def test_below_the_knee_the_tonemap_is_the_identity(
    composite: tuple[Any, BloomEffect, Framebuffer, Framebuffer], value: float
) -> None:
    """A dim scene composites to exactly itself.

    Both demos that use bloom were lit against a pipeline that clamped at
    1.0, so their mid-tones are already at the brightness they are meant to
    be shown at. A plain Reinhard would have pulled 0.5 down to 0.333 and
    re-graded every one of those pixels; this is the assertion that says it
    does not.

    Below the bloom threshold of 0.8 there is also no bloom to add, so the
    composite is the scene alone -- which is what makes the expected value
    exact rather than approximate.
    """
    assert value < _KNEE, "this test is only meaningful below the knee"

    assert _composite_of(composite, value) == pytest.approx(value, abs=1e-3)


def test_an_over_bright_scene_is_rolled_off_rather_than_clipped(
    composite: tuple[Any, BloomEffect, Framebuffer, Framebuffer],
) -> None:
    """Values above 1.0 arrive in range, and still differ from each other.

    The defect: at 2.0 the composite measured ~4.0 and at 4.0 it measured
    ~8.0, both of which `FinalPass` flattened to the same pure white. The
    highlight had no shape left. Two inputs an octave apart have to stay
    two distinguishable outputs, and the gap between them has to be real
    rather than float noise.
    """
    bright = _composite_of(composite, 2.0)
    brighter = _composite_of(composite, 4.0)

    assert _KNEE < bright < 1.0, "an over-bright pixel must land inside range"
    assert _KNEE < brighter < 1.0
    assert brighter - bright > 1e-3, (
        "a brighter scene must still read brighter -- equal values here mean "
        "the highlight has been clipped flat, which is the bug"
    )
