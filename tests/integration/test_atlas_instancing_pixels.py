"""An atlas draws its regions correctly, in one batch, on both backends.

The capability this locks in: before per-instance UVs, the GL sprite path
sampled the whole texture for every instance, so an atlas could only be
drawn by slicing it into one texture per region -- which forces one batch
per region, the exact batching an atlas exists to avoid.

Two halves, and both matter:

- the *pixels*, because a UV rect that is off by a flip, an origin or a
  scale still draws something plausible. A four-quadrant atlas with four
  known colours makes a wrong region read as the wrong colour rather than
  as a subtle smear;
- the *batch count*, because getting the pixels right by slicing the sheet
  into separate textures would pass a pixel test and defeat the point.

Run against both backends, deliberately. `docs/` promises parity, and a
region is exactly the kind of thing one backend can silently do
differently -- GL multiplies UVs in a shader, pygame blits a sub-rect.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderBatch, RenderCommand

pytestmark = pytest.mark.integration

_SIZE = 64
_CELL = 8

# A 2x2 atlas: each quadrant one flat, unmistakable colour.
_QUADRANTS = {
    "top_left": (Rect(0, 0, _CELL, _CELL), (255, 0, 0)),
    "top_right": (Rect(_CELL, 0, _CELL, _CELL), (0, 255, 0)),
    "bottom_left": (Rect(0, _CELL, _CELL, _CELL), (0, 0, 255)),
    "bottom_right": (Rect(_CELL, _CELL, _CELL, _CELL), (255, 255, 0)),
}


def _atlas_pixels() -> np.ndarray:
    """A (2*_CELL, 2*_CELL, 4) RGBA array of four flat colour quadrants."""
    image = np.zeros((_CELL * 2, _CELL * 2, 4), dtype=np.uint8)
    for rect, rgb in _QUADRANTS.values():
        image[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width, 0:3] = rgb
        image[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width, 3] = 255
    return image


class _Atlas:
    """The four-quadrant atlas, wrapped as a backend texture."""

    def __init__(self, native: Any) -> None:
        self._native = native

    @property
    def width(self) -> int:
        """Texture width in pixels."""
        return _CELL * 2

    @property
    def height(self) -> int:
        """Texture height in pixels."""
        return _CELL * 2

    @property
    def native_handle(self) -> Any:
        """The backend texture object."""
        return self._native


def _command(region: Rect | None, position: Vector2) -> RenderCommand:
    """A render command for one atlas region at a world position."""
    return RenderCommand(
        texture=None,  # type: ignore[arg-type] - filled in by the caller
        world_position=position,
        layer=0,
        z_index=0.0,
        source_rect=region,
    )


def _batches_for(regions: list[Rect | None], texture: Any) -> list[RenderBatch]:
    """Batch one command per region, all sharing `texture`."""
    commands = []
    for i, region in enumerate(regions):
        command = _command(region, Vector2(float(i), 0.0))
        command.texture = texture
        commands.append(command)

    camera = Camera2D(_SIZE, _SIZE)
    camera.position = Vector2(0, 0)
    return Batcher().create_batches(commands, camera, Viewport(0, 0, _SIZE, _SIZE))


def test_regions_of_one_atlas_land_in_a_single_batch() -> None:
    """The point of an atlas, asserted directly.

    No GL context needed: this is the batcher's decision, not the
    backend's. Four different regions of one texture, one draw call.
    """
    texture = _Atlas(native=object())

    batches = _batches_for([rect for rect, _ in _QUADRANTS.values()], texture)

    assert len(batches) == 1, "four regions of one atlas must be one draw call"
    batch = batches[0]
    assert batch.source_rects_enabled
    assert len(batch.source_rects) == 4


def test_a_batch_mixing_regions_and_whole_sprites_stays_one_batch() -> None:
    """A `None` region means "all of it", and does not split the batch.

    Otherwise an atlas-backed sprite drawn next to a plain one would cost
    an extra draw call for no reason, and the packer would face a list
    shorter than `destinations`.
    """
    texture = _Atlas(native=object())
    top_left = _QUADRANTS["top_left"][0]

    batches = _batches_for([top_left, None, top_left], texture)

    assert len(batches) == 1
    assert batches[0].source_rects == [top_left, None, top_left]


@pytest.fixture
def gl_scene(gl_ctx: Any) -> Iterator[tuple[Any, Any, _Atlas]]:
    """A GL framebuffer, a renderer drawing into it, and the atlas."""
    from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

    fbo = gl_ctx.simple_framebuffer((_SIZE, _SIZE))
    fbo.use()
    renderer = ModernGLRenderer(gl_ctx, _SIZE, _SIZE)
    native = gl_ctx.texture((_CELL * 2, _CELL * 2), 4, _atlas_pixels().tobytes())
    try:
        yield fbo, renderer, _Atlas(native)
    finally:
        native.release()
        renderer.release()
        fbo.release()


def _gl_centre(fbo: Any) -> tuple[int, int, int]:
    """Read the centre pixel of a GL framebuffer as (r, g, b)."""
    raw = np.frombuffer(fbo.read(components=3), dtype=np.uint8)
    image = raw.reshape((_SIZE, _SIZE, 3))
    return tuple(int(c) for c in image[_SIZE // 2, _SIZE // 2])  # type: ignore[return-value]


@pytest.mark.parametrize("name", sorted(_QUADRANTS))
def test_gl_draws_the_region_it_was_given(
    gl_scene: tuple[Any, Any, _Atlas], name: str
) -> None:
    """Each quadrant reads back as its own colour, on the GPU.

    Parametrised over all four rather than testing one, because a UV rect
    that is flipped vertically, or that uses the region's size as its
    origin, still draws *a* quadrant -- just the wrong one. One region
    cannot tell those apart; four can.
    """
    fbo, renderer, atlas = gl_scene
    rect, expected = _QUADRANTS[name]
    renderer.clear((0, 0, 0, 255))

    renderer.render_batch(
        RenderBatch(
            texture=atlas,
            destinations=[(_SIZE / 2, _SIZE / 2)],
            source_rects=[rect],
            source_rects_enabled=True,
        )
    )

    assert _gl_centre(fbo) == expected


def test_gl_draws_a_region_at_the_region_s_size(
    gl_scene: tuple[Any, Any, _Atlas],
) -> None:
    """An atlas entry is the size of its rect, not of the sheet.

    The half a UV rect alone would miss: sample the right texels, and
    still draw them across the full 16x16 footprint of the whole atlas.
    A region is 8x8, so a pixel 6px from the centre is outside it.
    """
    fbo, renderer, atlas = gl_scene
    rect, expected = _QUADRANTS["top_left"]
    renderer.clear((0, 0, 0, 255))

    renderer.render_batch(
        RenderBatch(
            texture=atlas,
            destinations=[(_SIZE / 2, _SIZE / 2)],
            source_rects=[rect],
            source_rects_enabled=True,
        )
    )

    image = np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(
        (_SIZE, _SIZE, 3)
    )
    centre = _SIZE // 2
    assert tuple(int(c) for c in image[centre, centre]) == expected
    assert tuple(int(c) for c in image[centre, centre + 6]) == (0, 0, 0), (
        "the region drew wider than its own rect -- 8x8 was stretched to "
        "the atlas's 16x16"
    )


@pytest.fixture
def pygame_scene() -> Iterator[tuple[Any, Any, _Atlas]]:
    """A pygame surface, a backend drawing onto it, and the same atlas."""
    import pygame

    from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend

    # `init()` is idempotent and several modules have already called it;
    # this deliberately does not `quit()`, which would tear pygame down
    # under whatever runs next in the session.
    pygame.init()
    screen = pygame.Surface((_SIZE, _SIZE))
    # No `convert_alpha()`: it needs a display mode, which a headless test
    # has no business setting, and a plain RGBA surface blits the same.
    native = pygame.image.frombuffer(
        _atlas_pixels().tobytes(), (_CELL * 2, _CELL * 2), "RGBA"
    )
    yield screen, PygameBackend(screen), _Atlas(native)


@pytest.mark.parametrize("name", sorted(_QUADRANTS))
def test_pygame_draws_the_region_it_was_given(
    pygame_scene: tuple[Any, Any, _Atlas], name: str
) -> None:
    """The pygame mirror of the GL test above.

    The two backends reach the same pixel by different means -- GL
    multiplies UVs in a vertex shader, pygame blits a sub-rect -- which is
    exactly the kind of difference that goes unnoticed until a game
    switches backends.

    `render_batch` blits at the destination as the top-left corner here
    (the fast path takes no centring), so the sampled pixel is offset into
    the quadrant rather than taken from the surface centre.
    """
    screen, renderer, atlas = pygame_scene
    rect, expected = _QUADRANTS[name]
    renderer.clear(Color(0, 0, 0, 255))

    renderer.render_batch(
        RenderBatch(
            texture=atlas,
            destinations=[(0.0, 0.0)],
            source_rects=[rect],
            source_rects_enabled=True,
        )
    )

    assert screen.get_at((_CELL // 2, _CELL // 2))[:3] == expected


def test_pygame_draws_a_region_at_the_region_s_size(
    pygame_scene: tuple[Any, Any, _Atlas],
) -> None:
    """A region blits its own 8x8, leaving the rest of the surface clear."""
    screen, renderer, atlas = pygame_scene
    rect, expected = _QUADRANTS["top_left"]
    renderer.clear(Color(0, 0, 0, 255))

    renderer.render_batch(
        RenderBatch(
            texture=atlas,
            destinations=[(0.0, 0.0)],
            source_rects=[rect],
            source_rects_enabled=True,
        )
    )

    assert screen.get_at((_CELL // 2, _CELL // 2))[:3] == expected
    assert screen.get_at((_CELL + 2, _CELL // 2))[:3] == (0, 0, 0), (
        "the region drew past its own 8x8 rect"
    )
