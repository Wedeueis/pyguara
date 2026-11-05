"""A flock steered by `FlockingSystem` and moved by `TopDownSystem` stops at walls.

The pairing `docs/ai/intelligence.md` describes, against a real physics engine.
"""

from __future__ import annotations

import pytest

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.topdown_movement import TopDownBody, TopDownSystem
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType

pytestmark = pytest.mark.integration

WALL_X = 200.0
DT = 1 / 60


@pytest.mark.parametrize("integrate", [True, False])
def test_a_flock_moved_by_a_collider_stops_at_a_wall(integrate: bool) -> None:
    world = EntityManager()
    engine = PymunkEngine()
    engine.initialize(Vector2(0, 0))
    physics = PhysicsSystem(engine, world, EventDispatcher())
    wall = world.create_entity("wall")
    wall.add_component(Transform(position=Vector2(WALL_X, 0)))
    wall.add_component(RigidBody(body_type=BodyType.STATIC))
    wall.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[20, 400]))
    physics.update(DT)

    for row in range(6):
        agent = world.create_entity(f"agent-{row}")
        agent.add_component(Transform(position=Vector2(0, -100 + row * 40)))
        agent.add_component(
            FlockingAgent(max_speed=200.0, seek_target=Vector2(600, -100 + row * 40))
        )
        agent.add_component(TopDownBody())
        agent.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[16, 16]))

    flock = FlockingSystem(world, integrate=integrate)
    movement = TopDownSystem(world, engine, SpatialHash[str]())
    for _ in range(240):
        flock.update(DT)
        if not integrate:
            for entity in world.get_entities_with(FlockingAgent, TopDownBody):
                body = entity.get_component(TopDownBody)
                body.velocity = entity.get_component(FlockingAgent).velocity
            movement.update(DT)

    furthest = max(
        e.get_component(Transform).position.x
        for e in world.get_entities_with(FlockingAgent)
    )
    if integrate:
        assert furthest > WALL_X, "The default still writes positions, through walls"
    else:
        assert furthest <= WALL_X - 10 - 8
