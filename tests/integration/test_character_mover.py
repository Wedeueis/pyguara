"""Collide-and-slide movement: the character is never inside the world.

The dynamic-body controller lets the solver resolve penetration after the
fact, so a character pressed into geometry is briefly inside it -- measured
at 8px in guara_falcao, recovering at 0.04px a tick. A swept mover cannot
produce that state: it stops flush at the surface instead of passing through
it and being pushed back.

Movement is Celeste's model: whole pixels only, with a float remainder
carrying whatever didn't add up to one yet. That means a resting position is
never approximate -- most of these assertions are exact pixel equalities,
not `pytest.approx(..., abs=0.1)`, because there is no bisection settling
near the answer; the last free whole pixel *is* the answer.

Every test here asserts the same underlying property in a different
situation: after the move, the character does not overlap anything.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.character_mover import CharacterMover
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType

pytestmark = pytest.mark.integration

DT = 1.0 / 60.0
HALF = Vector2(12.0, 20.0)
FLOOR_TOP = 480.0
TILE = 32


class World:
    """Static geometry plus a mover, with no character body of its own."""

    def __init__(self) -> None:
        """Create an empty world."""
        self.entities = EntityManager()
        self.dispatcher = EventDispatcher()
        self.engine = PymunkEngine()
        self.engine.set_collision_system(CollisionSystem(self.dispatcher))
        self.physics = PhysicsSystem(
            self.engine, self.entities, self.dispatcher, gravity=Vector2(0, 0)
        )
        self.mover = CharacterMover(self.engine)

    def solid(self, centre: Vector2, dimensions: list[float]) -> str:
        """Add one static box and return its entity id."""
        entity = self.entities.create_entity()
        entity.add_component(Transform(position=centre))
        entity.add_component(RigidBody(body_type=BodyType.STATIC))
        entity.add_component(Collider(shape_type=ShapeType.BOX, dimensions=dimensions))
        return entity.id

    def tiled_floor(self, tiles: int) -> None:
        """A floor built as separate tiles, seams and all."""
        for i in range(tiles):
            self.solid(
                Vector2(i * TILE + TILE / 2, FLOOR_TOP + TILE / 2),
                [float(TILE), float(TILE)],
            )

    def build(self) -> None:
        """Create the bodies in the backend."""
        self.physics.update(DT)

    def sunk_below(self, position: Vector2, surface_top: float) -> float:
        """How far the character's feet are below a surface. Negative is clear.

        Asserted geometrically rather than by asking the engine whether the
        box overlaps: a box resting exactly flush counts as overlapping, so a
        boolean answer cannot distinguish "resting on" from "inside".
        """
        return (position.y + HALF.y) - surface_top


def test_falling_stops_flush_on_the_floor() -> None:
    """Landing leaves the character touching the surface, not inside it."""
    world = World()
    world.solid(Vector2(400, FLOOR_TOP + TILE / 2), [800.0, float(TILE)])
    world.build()

    result = world.mover.move(Vector2(400, 300), HALF, Vector2(0, 400))

    assert result.grounded
    assert world.sunk_below(result.position, FLOOR_TOP) == 0.0
    assert result.position.y == FLOOR_TOP - HALF.y


def test_walking_into_a_wall_stops_flush() -> None:
    """Horizontal motion is stopped without entering the wall."""
    world = World()
    wall_id = world.solid(Vector2(500, 400), [float(TILE), 200.0])
    world.build()

    result = world.mover.move(Vector2(400, 400), HALF, Vector2(200, 0))

    assert result.hit_x
    wall_face = 500 - TILE / 2
    assert result.position.x == wall_face - HALF.x
    assert result.blocking_x == wall_id


def test_landing_keeps_horizontal_motion() -> None:
    """Axes resolve separately, which is what makes it slide rather than stick."""
    world = World()
    world.solid(Vector2(400, FLOOR_TOP + TILE / 2), [800.0, float(TILE)])
    world.build()

    start = Vector2(300, FLOOR_TOP - HALF.y - 5)
    result = world.mover.move(start, HALF, Vector2(60, 40))

    assert result.grounded
    assert result.position.x == 360, "slid along the floor"
    assert world.sunk_below(result.position, FLOOR_TOP) == 0.0


def test_walking_across_tile_seams_never_penetrates() -> None:
    """The reported bug, in the form it took: seams flung the character up.

    A swept mover has nothing to catch on -- it either fits at the next
    position or stops before it -- so the interior faces of a tiled floor
    stop mattering.
    """
    world = World()
    world.tiled_floor(tiles=20)
    world.build()

    position = Vector2(48, FLOOR_TOP - HALF.y)
    remainder = Vector2(0.0, 0.0)
    worst = -HALF.y
    for _ in range(200):
        result = world.mover.move(position, HALF, Vector2(3.0, 1.0), remainder)
        position = result.position
        remainder = result.remainder
        worst = max(worst, world.sunk_below(position, FLOOR_TOP))

    assert worst == 0.0, f"sank {worst:.3f}px into a tiled floor while walking"
    assert position.x > 400, "should have travelled along the floor"


def test_a_fast_move_does_not_step_over_a_thin_wall() -> None:
    """Sweeping one pixel at a time is also what prevents tunnelling."""
    world = World()
    world.solid(Vector2(500, 400), [4.0, 200.0])
    world.build()

    result = world.mover.move(Vector2(400, 400), HALF, Vector2(3000, 0))

    assert result.hit_x
    assert result.position.x == 500 - 2.0 - HALF.x


def test_moving_through_open_space_is_unobstructed() -> None:
    """The control: nothing in the way means the full delta is travelled."""
    world = World()
    world.solid(Vector2(400, FLOOR_TOP + TILE / 2), [800.0, float(TILE)])
    world.build()

    result = world.mover.move(Vector2(400, 100), HALF, Vector2(50, 60))

    assert not result.hit_x and not result.hit_y
    assert result.position == Vector2(450, 160)
    assert result.blocking_x is None and result.blocking_y is None


def test_a_blocked_axis_discards_its_banked_remainder() -> None:
    """Being stuck against a wall must not store up a lurch for later.

    Without discarding it, a character held against a wall by continuous
    input would bank the full distance requested every tick, and the
    instant the wall was gone, jump forward by everything that had piled up.
    """
    world = World()
    world.solid(Vector2(500, 400), [float(TILE), 200.0])
    world.build()

    # Slam flush against the wall first, then keep pushing into it in small
    # increments -- the case that would bank a remainder if blocking didn't
    # discard it.
    result = world.mover.move(Vector2(400, 400), HALF, Vector2(200, 0))
    assert result.hit_x
    for _ in range(5):
        result = world.mover.move(
            result.position, HALF, Vector2(1.0, 0), result.remainder
        )
        assert result.hit_x
        assert result.remainder.x == 0.0


def test_sub_pixel_motion_accumulates_without_drift() -> None:
    """Ten ticks of 0.3px add up to exactly 3px, not zero and not four.

    Each individual tick rounds to zero whole pixels -- if the remainder
    weren't carried forward, the character would never move at all under
    a force applied in small enough increments, which gravity often is.
    """
    world = World()
    remainder = Vector2(0.0, 0.0)
    position = Vector2(400, 100)
    for _ in range(10):
        result = world.mover.move(position, HALF, Vector2(0.3, 0), remainder)
        position = result.position
        remainder = result.remainder

    assert position.x == 403


def test_probe_detects_a_surface_without_moving() -> None:
    """The ground-check primitive: one pixel below, no movement involved."""
    world = World()
    floor_id = world.solid(Vector2(400, FLOOR_TOP + TILE / 2), [800.0, float(TILE)])
    world.build()

    resting = Vector2(400, FLOOR_TOP - HALF.y)
    assert world.mover.probe(resting, HALF, Vector2(0, 1)) == floor_id


def test_probe_finds_nothing_over_open_space() -> None:
    """The control: nothing below means the probe reports clear."""
    world = World()
    world.solid(Vector2(400, FLOOR_TOP + TILE / 2), [800.0, float(TILE)])
    world.build()

    airborne = Vector2(400, 100)
    assert world.mover.probe(airborne, HALF, Vector2(0, 1)) is None
