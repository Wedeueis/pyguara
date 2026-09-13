"""Unit tests for the ModernGL sprite instance pack.

No GL context and no renderer: `pack_sprite_instances` is a pure array
fill, which is the whole reason it was lifted out of `renderer.py`. What
the packed rows then *look like* on screen is the job of
`tests/integration/test_moderngl_pixels.py`.
"""

import math
import pathlib

import numpy as np
import pytest

from pyguara.graphics.backends.moderngl import instancing
from pyguara.graphics.backends.moderngl.instancing import (
    INSTANCE_FLOATS,
    pack_sprite_instances,
)
from pyguara.graphics.types import RenderBatch


class _Texture:
    """The two attributes the pack reads off a texture."""

    def __init__(self, width: int = 32, height: int = 16) -> None:
        self.width = width
        self.height = height
        self.path = "<test>"


def _scratch(rows: int = 8) -> np.ndarray:
    """A destination array of the shape the renderer keeps alive."""
    return np.empty((rows, INSTANCE_FLOATS), dtype="f4")


def test_positions_and_texture_size_land_in_their_columns() -> None:
    """The untransformed path writes position, identity transform, size."""
    batch = RenderBatch(texture=_Texture(32, 16), destinations=[(10.0, 20.0)])
    out = _scratch()

    count = pack_sprite_instances(batch, out)

    assert count == 1
    assert out[0, 0] == pytest.approx(10.0)
    assert out[0, 1] == pytest.approx(20.0)
    assert out[0, 2] == pytest.approx(0.0)  # rotation
    assert out[0, 3] == pytest.approx(1.0)  # scale x
    assert out[0, 4] == pytest.approx(1.0)  # scale y
    assert out[0, 5] == pytest.approx(32.0)  # size x
    assert out[0, 6] == pytest.approx(16.0)  # size y


def test_rotation_is_converted_to_radians() -> None:
    """Batches carry degrees; the shader's rotation matrix wants radians."""
    batch = RenderBatch(
        texture=_Texture(),
        destinations=[(0.0, 0.0), (1.0, 1.0)],
        rotations=[90.0, 180.0],
        scales=[(1.0, 1.0), (2.0, 3.0)],
        transforms_enabled=True,
    )
    out = _scratch()

    pack_sprite_instances(batch, out)

    assert out[0, 2] == pytest.approx(math.pi / 2, rel=1e-6)
    assert out[1, 2] == pytest.approx(math.pi, rel=1e-6)
    assert out[1, 3] == pytest.approx(2.0)
    assert out[1, 4] == pytest.approx(3.0)


def test_transforms_disabled_ignores_any_rotations_present() -> None:
    """`transforms_enabled` gates the columns, not the lists' emptiness."""
    batch = RenderBatch(
        texture=_Texture(),
        destinations=[(0.0, 0.0)],
        rotations=[45.0],
        scales=[(5.0, 5.0)],
        transforms_enabled=False,
    )
    out = _scratch()

    pack_sprite_instances(batch, out)

    assert out[0, 2] == pytest.approx(0.0)
    assert out[0, 3:5] == pytest.approx([1.0, 1.0])


def test_a_short_transform_list_leaves_the_whole_batch_untransformed() -> None:
    """One up-front length check, not a per-row guard.

    The row loop this replaced transformed the sprites it had data for and
    silently left the rest at identity -- a batch half-rotated by accident
    reads as a bug in the game, not in the pack.
    """
    batch = RenderBatch(
        texture=_Texture(),
        destinations=[(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)],
        rotations=[90.0],
        scales=[(2.0, 2.0)],
        transforms_enabled=True,
    )
    out = _scratch()

    count = pack_sprite_instances(batch, out)

    assert count == 3
    assert out[:3, 2] == pytest.approx([0.0, 0.0, 0.0])
    assert out[:3, 3] == pytest.approx([1.0, 1.0, 1.0])


def test_an_empty_batch_writes_nothing() -> None:
    """Zero sprites is a normal frame, not an error."""
    batch = RenderBatch(texture=_Texture(), destinations=[])
    out = _scratch()
    out.fill(7.0)

    assert pack_sprite_instances(batch, out) == 0
    assert out[0, 0] == pytest.approx(7.0)


def test_only_the_used_rows_are_touched() -> None:
    """A scratch array outlives the batch; stale rows past `count` are
    never uploaded, so the pack must not waste time clearing them."""
    batch = RenderBatch(texture=_Texture(), destinations=[(1.0, 2.0)])
    out = _scratch()
    out[1:].fill(-1.0)

    count = pack_sprite_instances(batch, out)

    assert count == 1
    assert np.all(out[1:] == -1.0)


def test_a_scratch_array_too_small_is_rejected() -> None:
    """The renderer grows the array before packing; if it did not, this is
    where a silent out-of-bounds write would otherwise start."""
    batch = RenderBatch(texture=_Texture(), destinations=[(0.0, 0.0)] * 4)

    with pytest.raises(ValueError, match="need 4"):
        pack_sprite_instances(batch, _scratch(2))


def test_a_scratch_array_of_the_wrong_width_is_rejected() -> None:
    """Guards against a layout change landing in one place but not both."""
    batch = RenderBatch(texture=_Texture(), destinations=[(0.0, 0.0)])

    with pytest.raises(ValueError, match=f"\\(n, {INSTANCE_FLOATS}\\)"):
        pack_sprite_instances(batch, np.empty((4, 3), dtype="f4"))


def test_the_filled_slice_is_contiguous_for_upload() -> None:
    """`vbo.write()` takes the view directly, which requires contiguity."""
    batch = RenderBatch(texture=_Texture(), destinations=[(0.0, 0.0)] * 3)
    out = _scratch()

    count = pack_sprite_instances(batch, out)

    assert out[:count].flags["C_CONTIGUOUS"]


def test_an_enabled_tint_is_packed_normalised() -> None:
    """Batches carry 0-255 RGBA; the shader multiplies in 0-1."""
    batch = RenderBatch(
        texture=_Texture(),
        destinations=[(0.0, 0.0), (1.0, 1.0)],
        colors=[(255, 0, 0, 255), (0, 128, 255, 0)],
        colors_enabled=True,
    )
    out = _scratch()

    pack_sprite_instances(batch, out)

    assert out[0, 7:11] == pytest.approx([1.0, 0.0, 0.0, 1.0])
    assert out[1, 7:11] == pytest.approx([0.0, 128 / 255, 1.0, 0.0], abs=1e-6)


def test_no_tint_broadcasts_opaque_white() -> None:
    """The colour columns are always packed -- an untinted batch multiplies
    the texel by 1, which is why no second shader program is needed."""
    batch = RenderBatch(texture=_Texture(), destinations=[(0.0, 0.0)] * 2)
    out = _scratch()

    pack_sprite_instances(batch, out)

    assert out[:2, 7:11] == pytest.approx(np.ones((2, 4)))


def test_a_short_colour_list_broadcasts_white_rather_than_tinting_some() -> None:
    """`colors_enabled` gates the packing, not the shader -- and it gates it
    on the whole batch, so a malformed one renders plainly rather than
    tinting its first few sprites."""
    batch = RenderBatch(
        texture=_Texture(),
        destinations=[(0.0, 0.0), (1.0, 1.0)],
        colors=[(255, 0, 0, 255)],
        colors_enabled=True,
    )
    out = _scratch()

    pack_sprite_instances(batch, out)

    assert out[:2, 7:11] == pytest.approx(np.ones((2, 4)))


def test_colours_left_over_from_a_previous_batch_do_not_leak() -> None:
    """The scratch array is reused every frame: an untinted batch packed
    after a tinted one must overwrite the colour columns, not inherit them."""
    out = _scratch()
    tinted = RenderBatch(
        texture=_Texture(),
        destinations=[(0.0, 0.0)],
        colors=[(255, 0, 0, 255)],
        colors_enabled=True,
    )
    pack_sprite_instances(tinted, out)

    plain = RenderBatch(texture=_Texture(), destinations=[(0.0, 0.0)])
    pack_sprite_instances(plain, out)

    assert out[0, 7:11] == pytest.approx([1.0, 1.0, 1.0, 1.0])


def test_the_default_material_shaders_are_the_shaders_in_use() -> None:
    """`materials/defaults.py` kept inline copies of the sprite shaders,
    which stopped matching the moment the sprite path grew a tint. They
    read from the same files now; this fails if anyone inlines them again."""
    from pyguara.graphics.materials import (
        DEFAULT_SPRITE_FRAGMENT,
        DEFAULT_SPRITE_VERTEX,
    )

    shader_dir = pathlib.Path(instancing.__file__).parent / "shaders"
    assert (shader_dir / "sprite.vert").read_text() == DEFAULT_SPRITE_VERTEX
    assert (shader_dir / "sprite.frag").read_text() == DEFAULT_SPRITE_FRAGMENT
