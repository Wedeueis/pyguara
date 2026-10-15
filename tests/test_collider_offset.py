"""`Collider.offset` moves the collider, everywhere it is consulted.

The field is documented as "local offset from the RigidBody center" and was
honoured in exactly two places: the pymunk CIRCLE branch, and
`physics/debug_draw.py`. The pymunk BOX branch -- the **default** shape
type -- dropped it, and so did every mover probe. The debug overlay
therefore drew a collider in one place while the simulation used another.

Nothing in the engine, the demos or the tests had ever set a non-zero
offset, which is why it went unnoticed, and is also why these tests exist:
there was no coverage of the field at all.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.bounds import collider_bounds
from pyguara.physics.components import Collider
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    PhysicsMaterial,
    ShapeType,
)

OFFSET = Vector2(0.0, -16.0)


# --------------------------------------------------------------------------
# The shared seam
# --------------------------------------------------------------------------
def test_bounds_applies_the_offset_to_the_centre() -> None:
    transform = Transform(position=Vector2(100.0, 100.0))
    collider = Collider(dimensions=[32.0, 48.0], offset=OFFSET)

    centre, half_extents = collider_bounds(transform, collider, Vector2(1.0, 1.0))

    assert centre == Vector2(100.0, 84.0)
    assert half_extents == Vector2(16.0, 24.0)


def test_bounds_without_a_collider_uses_the_callers_default() -> None:
    """A platformer character, a top-down one and a moving solid have
    deliberately different fallbacks, so the default is the caller's."""
    transform = Transform(position=Vector2(5.0, 7.0))

    centre, half_extents = collider_bounds(transform, None, Vector2(12.0, 20.0))

    assert centre == Vector2(5.0, 7.0)
    assert half_extents == Vector2(12.0, 20.0)


# --------------------------------------------------------------------------
# The pymunk backend
# --------------------------------------------------------------------------
@pytest.fixture
def engine() -> PymunkEngine:
    engine = PymunkEngine()
    engine.initialize(Vector2(0.0, 900.0))
    return engine


def _shape_centre_y(engine: PymunkEngine, shape_type: ShapeType, offset: Vector2):
    handle = engine.create_body(
        entity_id=f"e-{shape_type.name}-{offset.y}",
        body_type=BodyType.DYNAMIC,
        position=Vector2(100.0, 100.0),
        mass=1.0,
    )
    dimensions = [16.0] if shape_type is ShapeType.CIRCLE else [32.0, 32.0]
    engine.add_shape(
        handle,
        shape_type=shape_type,
        dimensions=dimensions,
        offset=offset,
        material=PhysicsMaterial(),
        collision_layer=CollisionLayer(),
        is_sensor=False,
    )
    box = next(iter(handle._body.shapes)).bb
    return (box.bottom + box.top) / 2.0


@pytest.mark.parametrize("shape_type", [ShapeType.CIRCLE, ShapeType.BOX])
def test_the_shape_is_built_at_the_offset(
    engine: PymunkEngine, shape_type: ShapeType
) -> None:
    """BOX used `Poly.create_box`, which always centres on the body origin
    and takes no transform, so the offset was silently discarded."""
    without = _shape_centre_y(engine, shape_type, Vector2(0.0, 0.0))
    with_offset = _shape_centre_y(engine, shape_type, OFFSET)

    assert with_offset == pytest.approx(without + OFFSET.y, abs=0.01)


def test_a_box_keeps_its_size_when_offset(engine: PymunkEngine) -> None:
    """Built from vertices now rather than `create_box`, so the dimensions
    are worth re-asserting."""
    handle = engine.create_body(
        entity_id="sized",
        body_type=BodyType.DYNAMIC,
        position=Vector2(0.0, 0.0),
        mass=1.0,
    )
    engine.add_shape(
        handle,
        shape_type=ShapeType.BOX,
        dimensions=[32.0, 48.0],
        offset=OFFSET,
        material=PhysicsMaterial(),
        collision_layer=CollisionLayer(),
        is_sensor=False,
    )
    box = next(iter(handle._body.shapes)).bb

    assert box.right - box.left == pytest.approx(32.0, abs=0.01)
    assert box.top - box.bottom == pytest.approx(48.0, abs=0.01)


@pytest.mark.parametrize("shape_type", [ShapeType.SEGMENT, ShapeType.POLYGON])
def test_an_unimplemented_shape_raises_instead_of_vanishing(
    engine: PymunkEngine, shape_type: ShapeType
) -> None:
    """These are in `ShapeType` and unhandled. They used to fall through
    with `shape` still None, so `add_shape` returned None having attached
    nothing -- a collider that silently does not exist, on a body that
    still moves and still reports as physical."""
    handle = engine.create_body(
        entity_id="unsupported",
        body_type=BodyType.DYNAMIC,
        position=Vector2(0.0, 0.0),
        mass=1.0,
    )

    with pytest.raises(NotImplementedError, match=shape_type.name):
        engine.add_shape(
            handle,
            shape_type=shape_type,
            dimensions=[10.0, 10.0],
            offset=Vector2(0.0, 0.0),
            material=PhysicsMaterial(),
            collision_layer=CollisionLayer(),
            is_sensor=False,
        )

    assert len(list(handle._body.shapes)) == 0
