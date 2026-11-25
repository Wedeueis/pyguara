"""An agent becomes an entity and back without jumping, turning or skipping."""

from __future__ import annotations

import math

import pytest

from pyguara.ai.flocking_system import FlockingAgent
from pyguara.ai.swarm import Swarm, SwarmKind, SwarmLook
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.animation import Animator
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture

KIND = SwarmKind(max_speed=90.0, max_force=250.0, mass=1.5, neighbor_radius=40.0)


class _Texture(Texture):
    @property
    def width(self) -> int:
        return 16

    @property
    def height(self) -> int:
        return 12

    @property
    def native_handle(self) -> object:
        return None


FRAMES = (_Texture("f0"), _Texture("f1"), _Texture("f2"))
LOOK = SwarmLook(
    frames=FRAMES,
    frame_rate=10.0,
    layer=7,
    z_index=2,
    offset=Vector2(-8, -6),
    scale=Vector2(1.5, 1.5),
    face_heading=True,
)


class _Backend:
    width, height = 400, 400

    def __init__(self) -> None:
        self.drawn: list[RenderBatch] = []

    def set_viewport(self, viewport: Viewport) -> None:
        pass

    def begin_frame(self) -> None:
        pass

    def end_frame(self) -> None:
        pass

    def render_batch(self, batch: RenderBatch) -> None:
        self.drawn.append(batch)


def _swarm(look: SwarmLook | None = LOOK) -> tuple[Swarm, int, int]:
    swarm = Swarm(cell_size=40.0)
    kind = swarm.add_kind(KIND)
    if look is not None:
        swarm.set_look(kind, look)
    (agent,) = swarm.spawn(kind, [Vector2(100, 120)], [Vector2(30, -40)])
    swarm.set_seek([agent], [Vector2(300, 50)])
    for _ in range(17):  # 0.28 s: the clip is on its third frame
        swarm.update(1 / 60)
    return swarm, kind, agent


def _texture_drawn(swarm: Swarm) -> Texture:
    backend = _Backend()
    system = RenderSystem(backend)  # type: ignore[arg-type]
    camera = Camera2D(400, 400)
    camera.position = Vector2(200, 200)
    swarm.submit(system)
    system.flush(camera)
    (batch,) = backend.drawn
    return batch.texture


class TestPromote:
    def test_the_entity_carries_on_where_the_agent_was(self) -> None:
        swarm, _, agent = _swarm()
        (position,), (velocity,) = swarm.positions([agent]), swarm.velocities([agent])
        manager = EntityManager()

        entity = swarm.promote(agent, manager)

        assert not swarm.is_alive(agent)
        assert swarm.count == 0
        assert manager.get_entity(entity.id) is entity
        assert entity.get_component(Transform).position == position
        flocking = entity.get_component(FlockingAgent)
        assert flocking.velocity == velocity
        assert flocking.seek_target == Vector2(300, 50)
        for name in SwarmKind.__dataclass_fields__:
            assert getattr(flocking, name) == getattr(KIND, name), name

    def test_it_looks_as_it_did_and_its_clip_does_not_skip(self) -> None:
        swarm, _, agent = _swarm()
        showing = _texture_drawn(swarm)
        (velocity,) = swarm.velocities([agent])

        entity = swarm.promote(agent, EntityManager())

        sprite = entity.get_component(Sprite)
        assert sprite.texture is showing is FRAMES[2]
        assert (sprite.layer, sprite.z_index) == (7, 2)
        assert (sprite.position, sprite.scale) == (LOOK.offset, LOOK.scale)
        assert sprite.rotation == math.degrees(math.atan2(velocity.y, velocity.x))
        assert entity.get_component(Animator)._current_clip is not None

    def test_a_kind_with_no_look_promotes_without_a_sprite(self) -> None:
        swarm, _, agent = _swarm(look=None)
        entity = swarm.promote(agent, EntityManager())
        assert not entity.has_component(Sprite)
        assert entity.has_component(FlockingAgent)

    def test_a_dead_agent_cannot_be_promoted(self) -> None:
        swarm, _, agent = _swarm()
        swarm.kill([agent])
        manager = EntityManager()
        with pytest.raises(KeyError):
            swarm.promote(agent, manager)
        assert list(manager.get_all_entities()) == []


class TestAdopt:
    def test_an_entity_becomes_an_agent_where_it_was(self) -> None:
        swarm, kind, _ = _swarm()
        manager = EntityManager()
        entity = manager.create_entity()
        entity.add_component(Transform(position=Vector2(50, 60)))
        entity.add_component(
            FlockingAgent(velocity=Vector2(5, 6), seek_target=Vector2(0, 999))
        )

        agent = swarm.adopt(manager, entity.id, kind)
        manager.flush_pending_removals()

        assert manager.get_entity(entity.id) is None
        assert swarm.positions([agent]) == [Vector2(50, 60)]
        assert swarm.velocities([agent]) == [Vector2(5, 6)]
        swarm.update(1 / 60)
        assert swarm.velocities([agent])[0].y > 6  # pulled toward its target

    def test_an_entity_without_a_flocking_agent_starts_at_rest(self) -> None:
        swarm, kind, _ = _swarm()
        manager = EntityManager()
        entity = manager.create_entity()
        entity.add_component(Transform(position=Vector2(1, 2)))
        agent = swarm.adopt(manager, entity.id, kind)
        assert swarm.velocities([agent]) == [Vector2(0, 0)]

    def test_a_round_trip_changes_nothing_it_carries(self) -> None:
        swarm, kind, agent = _swarm()
        (position,), (velocity,) = swarm.positions([agent]), swarm.velocities([agent])
        manager = EntityManager()
        entity = swarm.promote(agent, manager)

        back = swarm.adopt(manager, entity.id, kind)

        assert swarm.positions([back]) == [position]
        assert swarm.velocities([back]) == [velocity]

    @pytest.mark.parametrize("case", ["missing", "no transform", "unknown kind"])
    def test_a_refused_adoption_keeps_the_entity(self, case: str) -> None:
        swarm, kind, _ = _swarm()
        before = swarm.count
        manager = EntityManager()
        entity = manager.create_entity()
        if case != "no transform":
            entity.add_component(Transform(position=Vector2(1, 2)))
        entity_id = "nobody" if case == "missing" else entity.id
        wanted = 99 if case == "unknown kind" else kind
        with pytest.raises((KeyError, ValueError)):
            swarm.adopt(manager, entity_id, wanted)
        manager.flush_pending_removals()
        assert manager.get_entity(entity.id) is entity
        assert swarm.count == before
