"""Instance-array packing for the ModernGL sprite path.

Kept out of `renderer.py`, and free of every GL import, for two reasons.
It is the hot half of the instanced sprite draw -- `docs/guides/performance.md`
measures the Python pack at roughly four fifths of a 20,000-sprite frame,
a share that grows with sprite count -- so it earns its own place to be
read and optimised. And a pure array fill is testable without a GL context
at all, which is what makes the vectorised column writes below reviewable
against the row loop they replaced.
"""

from __future__ import annotations

import numpy as np

from pyguara.graphics.types import RenderBatch

# Per-instance layout: pos(2) + rot(1) + scale(2) + size(2) + color(4)
# + uv_offset(2) + uv_scale(2) = 15 floats. Neither the colour nor the UV
# columns are gated by a uniform or a second shader program: broadcasting
# a constant (white, or the whole texture) is free once the pack is
# vectorised, and `docs/guides/performance.md` measures 7 floats against
# 11 at 20,000 sprites as a difference below the noise floor -- the same
# reasoning carries the four UV columns. A uniform would instead force a
# per-batch state change to buy nothing, which is the whole problem an
# atlas exists to avoid.
INSTANCE_FLOATS = 15

# Column spans, so a layout change has one place to happen.
_COLOR_COLUMNS = slice(7, 11)
_UV_OFFSET_COLUMNS = slice(11, 13)
_UV_SCALE_COLUMNS = slice(13, 15)


def pack_sprite_instances(batch: RenderBatch, out: np.ndarray) -> int:
    """Fill `out` with one row of instance data per sprite in `batch`.

    Writes into the caller's array rather than returning a fresh one, so a
    renderer can keep a single scratch buffer alive across frames instead
    of allocating (count x INSTANCE_FLOATS) floats every draw.

    Optional per-instance data is applied only when its list is both
    enabled and the same length as `destinations`; a mismatch broadcasts
    the neutral value (no rotation, unit scale, opaque white) across every
    row -- so `colors_enabled` gates the packing, not the shader. That is
    one check for the batch rather than the per-row `i < len(...)` guards
    this replaced, and it means a half-filled list yields an obviously
    untransformed batch rather than a batch that is transformed for its
    first few sprites and not the rest.

    Args:
        batch: The sprites to pack. All share one texture, whose
            dimensions become each row's size columns.
        out: Destination array, at least `len(batch.destinations)` rows of
            `INSTANCE_FLOATS` columns, dtype `f4`.

    Returns:
        The number of rows written -- `out[:n]` is the slice to upload.

    Raises:
        ValueError: If `out` is too small or has the wrong column count.
    """
    count = len(batch.destinations)
    if out.ndim != 2 or out.shape[1] != INSTANCE_FLOATS:
        raise ValueError(
            f"instance array must be (n, {INSTANCE_FLOATS}), got {out.shape}"
        )
    if out.shape[0] < count:
        raise ValueError(f"instance array holds {out.shape[0]} rows, need {count}")
    if count == 0:
        return 0

    rows = out[:count]
    rows[:, 0:2] = np.asarray(batch.destinations, dtype="f4")

    transformed = (
        batch.transforms_enabled
        and len(batch.rotations) == count
        and len(batch.scales) == count
    )
    if transformed:
        # One radians conversion for the whole batch, not one per sprite.
        rows[:, 2] = np.radians(np.asarray(batch.rotations, dtype="f4"))
        rows[:, 3:5] = np.asarray(batch.scales, dtype="f4")
    else:
        rows[:, 2] = 0.0
        rows[:, 3:5] = 1.0

    texture_width = float(batch.texture.width)
    texture_height = float(batch.texture.height)

    if batch.source_rects_enabled and len(batch.source_rects) == count:
        # One (x, y, w, h) block, so the four columns come from a single
        # conversion rather than four list comprehensions.
        rects = np.asarray(
            [
                (r.x, r.y, r.width, r.height)
                if r is not None
                else (0.0, 0.0, texture_width, texture_height)
                for r in batch.source_rects
            ],
            dtype="f4",
        )
        # A region is drawn at the region's size, not the sheet's. This is
        # the half that a UV rect alone would miss: get it wrong and every
        # atlas sprite draws at the full atlas's dimensions.
        rows[:, 5:7] = rects[:, 2:4]
        rows[:, _UV_OFFSET_COLUMNS] = rects[:, 0:2] / (texture_width, texture_height)
        rows[:, _UV_SCALE_COLUMNS] = rects[:, 2:4] / (texture_width, texture_height)
    else:
        rows[:, 5] = texture_width
        rows[:, 6] = texture_height
        rows[:, _UV_OFFSET_COLUMNS] = 0.0
        rows[:, _UV_SCALE_COLUMNS] = 1.0

    if batch.colors_enabled and len(batch.colors) == count:
        # 0-255 on the batch, 0-1 in the shader, where the tint multiplies
        # the sampled texel.
        rows[:, _COLOR_COLUMNS] = np.asarray(batch.colors, dtype="f4") / 255.0
    else:
        rows[:, _COLOR_COLUMNS] = 1.0

    return count
