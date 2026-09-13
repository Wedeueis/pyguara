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

# Per-instance layout: pos(2) + rot(1) + scale(2) + size(2) = 7 floats.
INSTANCE_FLOATS = 7


def pack_sprite_instances(batch: RenderBatch, out: np.ndarray) -> int:
    """Fill `out` with one row of instance data per sprite in `batch`.

    Writes into the caller's array rather than returning a fresh one, so a
    renderer can keep a single scratch buffer alive across frames instead
    of allocating (count x INSTANCE_FLOATS) floats every draw.

    Optional per-instance data is applied only when its list is both
    enabled and the same length as `destinations`; a mismatch broadcasts
    the neutral value (no rotation, unit scale) across every row. That is
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

    rows[:, 5] = float(batch.texture.width)
    rows[:, 6] = float(batch.texture.height)

    return count
