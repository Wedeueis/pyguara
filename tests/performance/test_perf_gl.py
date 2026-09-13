"""Real-GL throughput for the instanced sprite path.

These run against `moderngl.create_standalone_context()` -- no window, no
SDL display, no buffer swap in the timing loop. That is a different job
from `tools/agent_view.py --gl`, which exists to capture what a *demo*
draws and therefore needs a real display path.

**These numbers describe a machine, not the engine.** The GPU work here
runs on whatever driver is underneath -- a real driver, Mesa on D3D12,
llvmpipe on a CI runner -- and those differ by orders of magnitude. The
portable figures are in `test_perf_render_cpu.py`. What makes these worth
recording anyway is the *split*: the pack-loop benchmarks below isolate
the Python cost of filling the instance array from the GPU cost of drawing
it, and the Python half transfers everywhere.

Everything here is in the slow tier. A GL context takes longer to create
than most of the guard suite takes to run, and a runner without one skips
rather than fails.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pyguara.graphics.backends.moderngl.instancing import (
    INSTANCE_FLOATS,
    pack_sprite_instances,
)
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
from pyguara.graphics.types import RenderBatch

pytestmark = [pytest.mark.performance, pytest.mark.slow]

# What `ModernGLRenderer` packed before the sprite path carried a
# per-instance tint, and what it packs now. Measuring both keeps the cost
# of that layout decision on record rather than on trust.
FLOATS_UNTINTED = 7
FLOATS_WITH_TINT = 11


class _GLTexture:
    """A real GL texture, wrapped to satisfy what `render_batch` reads."""

    def __init__(self, ctx, size: int = 16) -> None:
        self._texture = ctx.texture((size, size), 4, b"\xff" * (size * size * 4))
        self._size = size

    @property
    def width(self) -> int:
        """Texture width in pixels."""
        return self._size

    @property
    def height(self) -> int:
        """Texture height in pixels."""
        return self._size

    @property
    def native_handle(self):
        """The ModernGL texture the renderer binds."""
        return self._texture


def _batch(texture, count: int, *, transformed: bool) -> RenderBatch:
    """Build a batch of `count` sprites over `texture`."""
    step = 800.0 / max(count, 1)
    return RenderBatch(
        texture=texture,
        destinations=[(i * step % 800.0, i * step % 600.0) for i in range(count)],
        rotations=[i * 1.0 for i in range(count)] if transformed else [],
        scales=[(1.0, 1.0)] * count if transformed else [],
        transforms_enabled=transformed,
    )


def _pack_rows(batch: RenderBatch, floats: int) -> np.ndarray:
    """Fill an instance array the way `render_batch` used to: row by row.

    The engine packs with numpy column writes now
    (`instancing.pack_sprite_instances`). This is kept as the baseline that
    change is measured against -- reproduced here rather than called
    through the renderer so the Python cost stays isolated from the draw
    call, and kept faithful to the original, per-row length guards and all.
    """
    count = len(batch.destinations)
    data = np.zeros((count, floats), dtype="f4")
    width, height = float(batch.texture.width), float(batch.texture.height)

    for i, (x, y) in enumerate(batch.destinations):
        rotation = 0.0
        scale_x = scale_y = 1.0
        if batch.transforms_enabled:
            if i < len(batch.rotations):
                rotation = math.radians(batch.rotations[i])
            if i < len(batch.scales):
                scale_x, scale_y = batch.scales[i]
        row = [x, y, rotation, scale_x, scale_y, width, height]
        if floats > FLOATS_UNTINTED:
            row += [1.0, 1.0, 1.0, 1.0]
        data[i] = row
    return data


def _pack_vectorised(batch: RenderBatch, floats: int) -> np.ndarray:
    """Fill the same array with numpy column writes instead of a row loop.

    Parameterised by width, which `pack_sprite_instances` is not -- it
    exists to price a layout the engine does not ship, which is the whole
    job of `test_sweep_instance_stride_cost` below. The benchmark of the
    pack the engine *does* run calls the real function.
    """
    count = len(batch.destinations)
    data = np.empty((count, floats), dtype="f4")

    data[:, 0:2] = np.asarray(batch.destinations, dtype="f4")
    if batch.transforms_enabled:
        data[:, 2] = np.radians(np.asarray(batch.rotations, dtype="f4"))
        data[:, 3:5] = np.asarray(batch.scales, dtype="f4")
    else:
        data[:, 2] = 0.0
        data[:, 3:5] = 1.0
    data[:, 5] = float(batch.texture.width)
    data[:, 6] = float(batch.texture.height)
    if floats > FLOATS_UNTINTED:
        data[:, 7:11] = 1.0
    return data


@pytest.fixture(scope="module")
def renderer(gl_ctx):
    """A renderer drawing into an offscreen framebuffer."""
    fbo = gl_ctx.simple_framebuffer((800, 600))
    fbo.use()
    return ModernGLRenderer(gl_ctx, 800, 600)


@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_render_batch_end_to_end(benchmark, gl_ctx, renderer, count: int) -> None:
    """Report the whole instanced draw: pack, upload, and one draw call.

    Uses the transform path, matching the pack benchmarks below, so that
    the pack figure is legitimately a *component* of this one rather than
    a number from a different code path that happens to sit beside it.
    """
    batch = _batch(_GLTexture(gl_ctx), count, transformed=True)

    def frame() -> None:
        renderer.render_batch(batch)
        # Without this the driver queues the work and the timing measures
        # submission rather than execution.
        gl_ctx.finish()

    benchmark.pedantic(frame, rounds=5, iterations=1)


@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_instance_pack_row_loop(benchmark, gl_ctx, count: int) -> None:
    """Report the Python cost of the row-by-row instance pack it replaced.

    This is the portable half of the end-to-end number above.
    """
    batch = _batch(_GLTexture(gl_ctx), count, transformed=True)
    benchmark.pedantic(
        lambda: _pack_rows(batch, FLOATS_WITH_TINT), rounds=5, iterations=1
    )


@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_instance_pack_vectorised(benchmark, gl_ctx, count: int) -> None:
    """Report the pack the engine actually runs, at the same sizes.

    Calls `pack_sprite_instances` rather than a local copy of it, so this
    figure cannot drift away from the shipped code the way a reproduction
    would.
    """
    batch = _batch(_GLTexture(gl_ctx), count, transformed=True)
    scratch = np.empty((count, INSTANCE_FLOATS), dtype="f4")
    benchmark.pedantic(
        lambda: pack_sprite_instances(batch, scratch), rounds=5, iterations=1
    )


@pytest.mark.parametrize("floats", [FLOATS_UNTINTED, FLOATS_WITH_TINT])
def test_sweep_instance_stride_cost(benchmark, gl_ctx, floats: int) -> None:
    """Report what widening the instance layout for the tint cost.

    Packing and uploading 20000 instances at 7 floats each versus 11. The
    difference measured small -- a broadcast into four extra columns is
    nearly free once the pack is vectorised -- which is why the sprite path
    carries the tint attribute unconditionally instead of keeping a second
    shader program for untinted batches. Kept so that decision stays
    falsifiable rather than remembered.
    """
    batch = _batch(_GLTexture(gl_ctx), 20000, transformed=True)
    vbo = gl_ctx.buffer(reserve=20000 * floats * 4)

    def pack_and_upload() -> None:
        data = _pack_vectorised(batch, floats)
        vbo.write(data)

    try:
        benchmark.pedantic(pack_and_upload, rounds=5, iterations=1)
    finally:
        vbo.release()
