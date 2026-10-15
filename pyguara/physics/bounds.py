"""The world-space box a `Collider` actually occupies.

One function, because four places were each deriving it and three of them
derived it differently. `Collider.offset` is documented as a "local offset
from the RigidBody center", and `physics/debug_draw.py` applied it while
the pymunk BOX branch and every mover probe did not -- so the debug overlay
drew a collider in one place and the simulation used another.

Callers pass their own default half-extents: a platformer character, a
top-down one and a moving solid have deliberately different fallbacks when
no `Collider` is attached, and this is not the place to pick between them.
"""

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.physics.components import Collider


def collider_bounds(
    transform: Transform,
    collider: Collider | None,
    default_half_extents: Vector2,
) -> tuple[Vector2, Vector2]:
    """Return the `(centre, half_extents)` a collider occupies in the world.

    Args:
        transform: The owning entity's transform, read for its position.
        collider: The collider, or None when the entity has none.
        default_half_extents: Half width and height to assume without a
            collider. Genre-specific, so the caller owns it.

    Returns:
        `(centre, half_extents)`. The centre is the transform's position
        shifted by `collider.offset`, which is what makes a collider that
        does not sit on its entity's origin -- feet at the transform, body
        above it -- behave the way the debug overlay already draws it.
    """
    if collider is None:
        return transform.position, default_half_extents

    half_extents = Vector2(collider.dimensions[0] / 2.0, collider.dimensions[1] / 2.0)
    return transform.position + collider.offset, half_extents
