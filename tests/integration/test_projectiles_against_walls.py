"""`ProjectileSystem` with real walls: a shot stops at one, and spares what is behind it.

Uses a real `PymunkEngine` for `solids`, so the raycast the system relies on is
the physics backend's own rather than a stand-in.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.action_combat import Health, Hurtbox
from pyguara.kits.projectiles import ProjectileSystem
from pyguara.kits.stats import DamageType
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType

pytestmark = pytest.mark.integration

WALL_X = 200.0
DT = 1 / 60


@pytest.mark.parametrize("behind", [True, False])
def test_a_shot_hits_only_what_is_before_a_wall(behind: bool) -> None:
    walls = EntityManager()
    engine = PymunkEngine()
    engine.initialize(Vector2(0, 0))
    physics = PhysicsSystem(engine, walls, EventDispatcher())
    wall = walls.create_entity("wall")
    wall.add_component(Transform(position=Vector2(WALL_X, 0)))
    wall.add_component(RigidBody(body_type=BodyType.STATIC))
    wall.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[20, 400]))
    physics.update(DT)

    world = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    target = world.create_entity("target")
    position = Vector2(WALL_X + 60 if behind else WALL_X - 60, 0)
    target.add_component(Transform(position=position))
    target.add_component(Health(current=100.0, max_health=100.0))
    target.add_component(Hurtbox())
    index.insert(target.id, position)

    shots = ProjectileSystem(world, EventDispatcher(), index, solids=engine)
    # 1500 px/s is 25 px a tick: further than the shot's reach, every tick.
    shots.spawn(
        None,
        Vector2(0, 0),
        Vector2(1500, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        hit_radius=6.0,
        life=1.0,
    )

    furthest = 0.0
    for _ in range(60):
        shots.update(DT)
        for shot in shots.get_active():
            furthest = max(furthest, shot.position.x)

    assert not shots.get_active()
    assert furthest <= WALL_X - 10
    expected = 100.0 if behind else 90.0
    assert target.get_component(Health).current == expected
