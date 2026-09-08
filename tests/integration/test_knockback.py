"""Knockback: velocity a character consumes, not an impulse.

`Hazard.knockback_force` was declared on the component from the start and
read by nothing -- there was no velocity a dynamic-body player could
receive it as that didn't immediately get overwritten by
PlatformerSystem's own input-driven control the very same tick.
`apply_knockback()` gives it a real place to land: it overrides
`CharacterBody.velocity` directly and suppresses input control for a short
window, during which the velocity decays back toward zero and gravity
keeps acting underneath it, exactly like an ordinary hit-stun.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.components import CharacterBody, Collider
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.platformer_controller import PlatformerController, PlatformerInput
from pyguara.physics.platformer_system import PlatformerSystem, apply_knockback

pytestmark = pytest.mark.integration

DT = 1.0 / 60.0


class World:
    """A character alone in open space -- knockback needs no geometry."""

    def __init__(self, gravity: Vector2 = Vector2(0, 900)) -> None:
        """Build the world and drop a character into it."""
        self.entities = EntityManager()
        self.dispatcher = EventDispatcher()
        engine = PymunkEngine()
        engine.set_collision_system(CollisionSystem(self.dispatcher))
        self.physics = PhysicsSystem(
            engine, self.entities, self.dispatcher, gravity=gravity
        )
        self.platformer = PlatformerSystem(self.entities, engine, gravity=gravity)

        self.character = self.entities.create_entity()
        self.character.add_component(Transform(position=Vector2(400, 100)))
        self.character.add_component(CharacterBody())
        self.character.add_component(Collider(dimensions=[24.0, 40.0]))
        self.character.add_component(PlatformerController(move_speed=200.0))

    @property
    def body(self) -> CharacterBody:
        """The character's CharacterBody."""
        return self.character.get_component(CharacterBody)

    @property
    def controller(self) -> PlatformerController:
        """The character's controller."""
        return self.character.get_component(PlatformerController)

    def run(self, ticks: int, move_input: float = 0.0) -> None:
        """Advance physics then the platformer layer, holding `move_input`."""
        for _ in range(ticks):
            self.controller.pending_input = PlatformerInput(move=move_input)
            self.physics.update(DT)
            self.platformer.update(DT)


def test_knockback_overrides_velocity_immediately() -> None:
    """The hit itself: velocity becomes the knockback, not whatever it was."""
    world = World(gravity=Vector2(0, 0))
    world.body.velocity = Vector2(50, 0)

    apply_knockback(world.body, Vector2(-300, -200), duration=0.2)

    assert world.body.velocity == Vector2(-300, -200)
    assert world.body.external_velocity_timer == pytest.approx(0.2)


def test_knockback_suppresses_input_control_while_active() -> None:
    """Pressing the opposite direction doesn't cancel the knockback outright."""
    world = World(gravity=Vector2(0, 0))
    apply_knockback(world.body, Vector2(-300, 0), duration=0.2)

    # Hold input toward +x -- away from the knockback -- for a few ticks.
    world.run(5, move_input=1.0)

    assert world.body.velocity.x < 0, "knockback should still be in control"


def test_knockback_decays_toward_zero() -> None:
    """Residual velocity shrinks every tick, not just at the end of the timer."""
    world = World(gravity=Vector2(0, 0))
    apply_knockback(world.body, Vector2(-300, 0), duration=1.0)

    speeds = []
    for _ in range(10):
        world.run(1)
        speeds.append(abs(world.body.velocity.x))

    assert all(a >= b for a, b in zip(speeds, speeds[1:], strict=False)), (
        f"speed should shrink monotonically, was {speeds}"
    )
    assert speeds[-1] < speeds[0]


def test_control_resumes_once_the_timer_expires() -> None:
    """After the window closes, input drives velocity again."""
    world = World(gravity=Vector2(0, 0))
    apply_knockback(world.body, Vector2(-300, 0), duration=0.05)

    world.run(10, move_input=1.0)  # well past 0.05s

    assert world.body.external_velocity_timer == 0.0
    assert world.body.velocity.x > 0, "input should be driving velocity again"


def test_gravity_still_acts_during_knockback() -> None:
    """A knockback arcs through the air; it doesn't suspend gravity."""
    world = World(gravity=Vector2(0, 900))
    apply_knockback(world.body, Vector2(-300, -200), duration=0.5)

    start_vy = world.body.velocity.y
    world.run(10)

    assert world.body.velocity.y > start_vy, "gravity should have kept adding downward"
