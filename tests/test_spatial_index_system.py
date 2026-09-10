"""Tests for `SpatialIndexSystem`/`SpatialTracked` (pyguara/spatial/)."""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.events import EntityDestroyed
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.spatial.components import SpatialTracked
from pyguara.spatial.system import SpatialIndexSystem


def _wire_entity_destroyed(manager: EntityManager, dispatcher: EventDispatcher) -> None:
    """Mirrors `Scene.resolve_dependencies()`'s removal-hook wiring."""
    manager.subscribe_entity_removed(
        lambda e: dispatcher.dispatch(EntityDestroyed(entity=e, source=None))
    )


def test_update_inserts_tracked_entities_at_their_world_position(
    event_dispatcher,
) -> None:
    manager = EntityManager()
    index = SpatialHash[str]()
    system = SpatialIndexSystem(manager, index, event_dispatcher)

    entity = manager.create_entity()
    entity.add_component(Transform(position=Vector2(10, 10)))
    entity.add_component(SpatialTracked())

    system.update(0.1)

    assert index.query_radius(Vector2(10, 10), radius=1.0) == [entity.id]


def test_update_moves_an_already_tracked_entity(event_dispatcher) -> None:
    manager = EntityManager()
    index = SpatialHash[str]()
    system = SpatialIndexSystem(manager, index, event_dispatcher)

    entity = manager.create_entity()
    transform = entity.add_component(Transform(position=Vector2(0, 0)))
    entity.add_component(SpatialTracked())
    system.update(0.1)

    transform.position = Vector2(500, 500)
    system.update(0.1)

    assert index.query_radius(Vector2(0, 0), radius=10.0) == []
    assert index.query_radius(Vector2(500, 500), radius=10.0) == [entity.id]


def test_untracked_entity_is_never_indexed(event_dispatcher) -> None:
    manager = EntityManager()
    index = SpatialHash[str]()
    system = SpatialIndexSystem(manager, index, event_dispatcher)

    entity = manager.create_entity()
    entity.add_component(Transform(position=Vector2(0, 0)))

    system.update(0.1)

    assert index.query_radius(Vector2(0, 0), radius=10.0) == []


def test_entity_destroyed_removes_it_from_the_index(event_dispatcher) -> None:
    manager = EntityManager()
    _wire_entity_destroyed(manager, event_dispatcher)
    index = SpatialHash[str]()
    system = SpatialIndexSystem(manager, index, event_dispatcher)

    entity = manager.create_entity()
    entity.add_component(Transform(position=Vector2(0, 0)))
    entity.add_component(SpatialTracked())
    system.update(0.1)

    manager.remove_entity(entity.id)

    assert index.query_radius(Vector2(0, 0), radius=10.0) == []


def test_destroying_an_untracked_entity_is_a_noop(event_dispatcher) -> None:
    manager = EntityManager()
    _wire_entity_destroyed(manager, event_dispatcher)
    index = SpatialHash[str]()
    SpatialIndexSystem(manager, index, event_dispatcher)

    entity = manager.create_entity()
    entity.add_component(Transform(position=Vector2(0, 0)))

    manager.remove_entity(entity.id)  # must not raise


def test_mask_is_forwarded_from_the_component(event_dispatcher) -> None:
    manager = EntityManager()
    index = SpatialHash[str]()
    system = SpatialIndexSystem(manager, index, event_dispatcher)

    entity = manager.create_entity()
    entity.add_component(Transform(position=Vector2(0, 0)))
    entity.add_component(SpatialTracked(mask=0b01))

    system.update(0.1)

    assert index.query_radius(Vector2(0, 0), radius=10.0, mask=0b10) == []
    assert index.query_radius(Vector2(0, 0), radius=10.0, mask=0b01) == [entity.id]
