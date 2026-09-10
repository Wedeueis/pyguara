"""Tests for `TopDownBody`/`TopDownSystem` (pyguara/physics/topdown_*.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.physics.topdown_controller import TopDownBody
from pyguara.physics.topdown_system import TopDownSystem
from pyguara.spatial.components import SpatialTracked


def _unobstructed_engine() -> MagicMock:
    engine = MagicMock()
    engine.overlap_box.return_value = None
    return engine


# ========== Movement ==========


def test_update_moves_a_body_by_velocity_times_delta_time() -> None:
    manager = EntityManager()
    system = TopDownSystem(manager, _unobstructed_engine(), SpatialHash[str]())

    entity = manager.create_entity()
    transform = entity.add_component(Transform(position=Vector2(0, 0)))
    entity.add_component(TopDownBody(velocity=Vector2(100, 0)))

    system.update(1.0)

    assert transform.position == Vector2(100, 0)


def test_update_stops_at_a_blocking_overlap() -> None:
    manager = EntityManager()
    engine = MagicMock()
    # Blocked as soon as the box would move past x=5.
    engine.overlap_box.side_effect = lambda centre, *a, **k: (
        "blocker" if centre.x > 5 else None
    )
    system = TopDownSystem(manager, engine, SpatialHash[str]())

    entity = manager.create_entity()
    transform = entity.add_component(Transform(position=Vector2(0, 0)))
    entity.add_component(TopDownBody(velocity=Vector2(100, 0)))

    system.update(1.0)

    assert transform.position.x <= 5


def test_a_zero_velocity_body_does_not_move() -> None:
    manager = EntityManager()
    system = TopDownSystem(manager, _unobstructed_engine(), SpatialHash[str]())

    entity = manager.create_entity()
    transform = entity.add_component(Transform(position=Vector2(10, 10)))
    entity.add_component(TopDownBody())

    system.update(1.0)

    assert transform.position == Vector2(10, 10)


# ========== Actor separation ==========


def _tracked_entity(manager: EntityManager, position: Vector2, radius: float):
    entity = manager.create_entity()
    entity.add_component(Transform(position=position))
    entity.add_component(TopDownBody(separation_radius=radius))
    entity.add_component(SpatialTracked())
    return entity


def test_overlapping_actors_are_pushed_apart() -> None:
    manager = EntityManager()
    index = SpatialHash[str]()
    system = TopDownSystem(manager, _unobstructed_engine(), index)

    a = _tracked_entity(manager, Vector2(0, 0), radius=10.0)
    b = _tracked_entity(manager, Vector2(5, 0), radius=10.0)
    index.insert(a.id, Vector2(0, 0))
    index.insert(b.id, Vector2(5, 0))

    system.update(0.0)

    a_transform = a.get_component(Transform)
    b_transform = b.get_component(Transform)
    # Combined radius is 20, they started 5 apart: 15 of overlap, split
    # evenly, pushed directly along the line between them (the x axis here).
    assert a_transform.position.x == -7.5
    assert b_transform.position.x == 12.5


def test_non_overlapping_actors_are_left_alone() -> None:
    manager = EntityManager()
    index = SpatialHash[str]()
    system = TopDownSystem(manager, _unobstructed_engine(), index)

    a = _tracked_entity(manager, Vector2(0, 0), radius=5.0)
    b = _tracked_entity(manager, Vector2(100, 0), radius=5.0)
    index.insert(a.id, Vector2(0, 0))
    index.insert(b.id, Vector2(100, 0))

    system.update(0.0)

    assert a.get_component(Transform).position == Vector2(0, 0)
    assert b.get_component(Transform).position == Vector2(100, 0)


def test_a_pair_is_pushed_apart_exactly_once() -> None:
    """Regardless of which entity the query visits first, the pair is only
    resolved from one side -- otherwise it would be pushed twice as far."""
    manager = EntityManager()
    index = SpatialHash[str]()
    system = TopDownSystem(manager, _unobstructed_engine(), index)

    a = _tracked_entity(manager, Vector2(0, 0), radius=10.0)
    b = _tracked_entity(manager, Vector2(5, 0), radius=10.0)
    index.insert(a.id, Vector2(0, 0))
    index.insert(b.id, Vector2(5, 0))

    system._separate_actors()
    system._separate_actors()  # calling twice would double it if buggy

    total_spread = (
        b.get_component(Transform).position.x - a.get_component(Transform).position.x
    )
    # A single resolution brings them to exactly touching (20 apart); a
    # second call finds them no longer overlapping and does nothing more.
    assert total_spread == 20.0


def test_zero_separation_radius_opts_an_actor_out_of_separation() -> None:
    manager = EntityManager()
    index = SpatialHash[str]()
    system = TopDownSystem(manager, _unobstructed_engine(), index)

    a = _tracked_entity(manager, Vector2(0, 0), radius=0.0)
    b = _tracked_entity(manager, Vector2(5, 0), radius=10.0)
    index.insert(a.id, Vector2(0, 0))
    index.insert(b.id, Vector2(5, 0))

    system.update(0.0)

    assert a.get_component(Transform).position == Vector2(0, 0)
    assert b.get_component(Transform).position == Vector2(5, 0)


def test_untracked_actor_does_not_participate_in_separation() -> None:
    """A TopDownBody with no SpatialTracked can't be found by the query, so
    it neither pushes others nor gets pushed."""
    manager = EntityManager()
    index = SpatialHash[str]()
    system = TopDownSystem(manager, _unobstructed_engine(), index)

    a = manager.create_entity()
    a.add_component(Transform(position=Vector2(0, 0)))
    a.add_component(TopDownBody(separation_radius=10.0))
    # No SpatialTracked on `a`, and nothing inserted into the index for it.

    b = _tracked_entity(manager, Vector2(5, 0), radius=10.0)
    index.insert(b.id, Vector2(5, 0))

    system.update(0.0)

    assert a.get_component(Transform).position == Vector2(0, 0)
    assert b.get_component(Transform).position == Vector2(5, 0)
