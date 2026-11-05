"""Tests for `TopDownBody`/`TopDownSystem` (pyguara/physics/topdown_*.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.kits.topdown_movement.body import TopDownBody
from pyguara.kits.topdown_movement.system import TopDownSystem
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


# ========== Bodies moved elsewhere, and order ==========


def test_a_body_moved_elsewhere_is_not_moved_again() -> None:
    manager = EntityManager()
    system = TopDownSystem(manager, _unobstructed_engine(), SpatialHash[str]())
    entity = manager.create_entity()
    transform = entity.add_component(Transform(position=Vector2(0, 0)))
    entity.add_component(TopDownBody(velocity=Vector2(100, 0), moved_elsewhere=True))
    system.update(1.0)
    assert transform.position == Vector2(0, 0)


def test_a_body_moved_elsewhere_still_takes_part_in_separation() -> None:
    manager = EntityManager()
    index = SpatialHash[str]()
    system = TopDownSystem(manager, _unobstructed_engine(), index)
    moved = manager.create_entity()
    moved_at = moved.add_component(Transform(position=Vector2(0, 0)))
    moved.add_component(TopDownBody(separation_radius=10, moved_elsewhere=True))
    moved.add_component(SpatialTracked())
    other = manager.create_entity()
    other_at = other.add_component(Transform(position=Vector2(5, 0)))
    other.add_component(TopDownBody(separation_radius=10))
    other.add_component(SpatialTracked())
    index.insert(moved.id, moved_at.position)
    index.insert(other.id, other_at.position)
    system.update(0.0)
    assert (other_at.position - moved_at.position).magnitude == 20


_CROWD = """
from unittest.mock import MagicMock
from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.kits.topdown_movement.body import TopDownBody
from pyguara.kits.topdown_movement.system import TopDownSystem
from pyguara.spatial.components import SpatialTracked
engine = MagicMock()
engine.overlap_box.return_value = None
manager = EntityManager()
index = SpatialHash(cell_size=32.0, accelerate=False)
system = TopDownSystem(manager, engine, index)
transforms = []
for i in range(40):
    entity = manager.create_entity(f"actor-{i}")
    at = Vector2((i * 37) % 23 * 0.7, (i * 53) % 19 * 0.7)
    transforms.append(entity.add_component(Transform(position=at)))
    entity.add_component(TopDownBody(separation_radius=12.0))
    entity.add_component(SpatialTracked())
for _ in range(5):
    for i, transform in enumerate(transforms):
        index.insert(f"actor-{i}", transform.position)
    system.update(1 / 60)
print([tuple(t.position) for t in transforms])
"""


def test_a_crowd_separates_the_same_way_in_every_process() -> None:
    """The index's set order changes with each process's string hashing."""
    import os
    import subprocess
    import sys

    results = {
        subprocess.run(
            [sys.executable, "-c", _CROWD],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2", "3", "4")
    }
    assert len(results) == 1
