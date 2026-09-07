"""The game-feel layer built on top of the simulation.

Chipmunk simulates rigid bodies; it knows nothing about characters, ground or
jumping. Everything that makes a platformer feel right -- knowing you are
standing on something, coyote time, jump buffering, one jump per landing --
is PyGuara's own, and all of it rests on the ground raycast telling the truth.

It did not. The ray starts just below the character's feet, but a Chipmunk
segment query is a swept circle whose radius reached back into the character's
own collider, so every character detected itself and read as permanently
grounded -- in mid-air, and with no ground in the world at all. Coyote time
never started, jump buffering had nothing to buffer for, and the landing that
clears the one-jump-per-landing flag never happened, so a character stopped
being able to jump until it died.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.platformer_controller import PlatformerController, PlatformerInput
from pyguara.physics.platformer_system import PlatformerSystem
from pyguara.physics.types import BodyType, ShapeType

pytestmark = pytest.mark.integration

DT = 1.0 / 60.0
PLAYER_HEIGHT = 40.0
GROUND_TOP = 480.0  # ground centre y=500, 40 tall
RESTING_Y = GROUND_TOP - PLAYER_HEIGHT / 2


class Platformer:
    """A character on a floor, wired as a game would wire it."""

    def __init__(self, gravity: Vector2 = Vector2(0, 900), floor_width: float = 800.0):
        """Build the world and drop a character into it."""
        self.entities = EntityManager()
        self.dispatcher = EventDispatcher()
        engine = PymunkEngine()
        engine.set_collision_system(CollisionSystem(self.dispatcher))
        self.physics = PhysicsSystem(
            engine, self.entities, self.dispatcher, gravity=gravity
        )
        self.platformer = PlatformerSystem(self.entities, engine)

        self.ground = self._body(
            Vector2(400, 500), BodyType.STATIC, [floor_width, 40.0]
        )
        self.player = self._body(
            Vector2(400, RESTING_Y), BodyType.DYNAMIC, [24.0, PLAYER_HEIGHT]
        )
        self.player.add_component(PlatformerController(jump_force=350.0))

    def _body(
        self, position: Vector2, body_type: BodyType, dimensions: list[float]
    ) -> Entity:
        entity = self.entities.create_entity()
        entity.add_component(Transform(position=position))
        entity.add_component(RigidBody(mass=1.0, body_type=body_type))
        entity.add_component(Collider(shape_type=ShapeType.BOX, dimensions=dimensions))
        return entity

    @property
    def controller(self) -> PlatformerController:
        """The character's controller."""
        return self.player.get_component(PlatformerController)

    @property
    def y(self) -> float:
        """The character's current height."""
        return self.player.get_component(Transform).position.y

    def run(self, ticks: int) -> None:
        """Advance physics then the platformer layer, as fixed_update does."""
        for _ in range(ticks):
            self.physics.update(DT)
            self.platformer.update(DT)

    def jump(self) -> float:
        """Request a jump and return how high the character actually got."""
        resting = self.y
        self.controller.pending_input = PlatformerInput(jump=True)
        peak = resting
        for _ in range(60):
            self.physics.update(DT)
            self.platformer.update(DT)
            peak = min(peak, self.y)
        return resting - peak


def test_a_character_in_mid_air_is_not_grounded() -> None:
    """The bug in one line: it used to detect its own collider.

    The character is launched upward and checked while it is unambiguously
    airborne, tens of pixels above the floor.
    """
    world = Platformer()
    world.run(60)
    assert world.controller.is_grounded, "should be standing on the floor to start"

    world.player.get_component(RigidBody)._body_handle.velocity = Vector2(0, -400)
    world.run(10)

    assert world.y < RESTING_Y - 20, "should have left the ground"
    assert not world.controller.is_grounded


def test_a_character_with_no_ground_beneath_it_is_not_grounded() -> None:
    """The sharpest version: nothing to stand on anywhere in the world."""
    world = Platformer(gravity=Vector2(0, 0), floor_width=1.0)
    world.player.get_component(Transform).position = Vector2(400, 100)
    world.run(2)

    assert not world.controller.is_grounded


def test_a_character_can_jump_again_after_landing() -> None:
    """One jump per landing, not one jump per lifetime.

    `_jump_used` is cleared by the airborne-to-grounded transition. While
    grounding was stuck on, that transition never fired again and the third
    jump -- the first after the input buffer was exhausted -- did nothing.
    """
    world = Platformer()
    world.run(60)

    heights = []
    for _ in range(3):
        heights.append(world.jump())
        world.run(60)  # land and settle

    assert all(h > 20 for h in heights), f"jump heights were {heights}"


def test_leaving_a_ledge_starts_coyote_time() -> None:
    """Coyote time is the grace period after walking off an edge.

    It can only start on the grounded-to-airborne transition, which never
    happened while the character believed it was always on the ground.
    """
    world = Platformer()
    world.run(60)
    assert world.controller.coyote_timer == 0.0

    world.player.get_component(RigidBody)._body_handle.velocity = Vector2(0, -400)
    world.run(10)

    assert not world.controller.is_grounded
    assert world.controller.coyote_timer > 0.0


def test_a_raycast_can_exclude_the_body_that_cast_it() -> None:
    """The engine-level capability the fix rests on."""
    world = Platformer(gravity=Vector2(0, 0))
    # Float the character far from the floor, so the only thing its own
    # downward ray can possibly reach is the character itself.
    world.player.get_component(Transform).position = Vector2(400, 100)
    world.run(1)

    centre = world.player.get_component(Transform).position
    feet = centre + Vector2(0, PLAYER_HEIGHT / 2 + 1)
    just_below = feet + Vector2(0, 3.0)
    engine = world.physics._engine

    included = engine.raycast(feet, just_below)
    excluded = engine.raycast(feet, just_below, ignore_entity_id=world.player.id)

    assert included is not None, "the swept ray does touch the caster"
    assert included.entity_id == world.player.id
    assert excluded is None or excluded.entity_id != world.player.id
