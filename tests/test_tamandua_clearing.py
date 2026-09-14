"""Tests for Tamanduá's clearing: the mounds, the drift and the tongue.

The demo runs on ModernGL, so it is excluded from `DEMOS_THAT_DRAW` --
SDL's dummy video driver provides no OpenGL and the scene cannot boot
headlessly at all. That makes these the *only* automated coverage its
rules get, so they test the rules rather than the pictures: nothing here
imports the scene, the bootstrap or a renderer.
"""

from __future__ import annotations

import math

import pytest

from games.tamandua_murundus.components import Insect, Murundu, Tamandua
from games.tamandua_murundus.events import (
    InsectKilled,
    MurunduBroken,
    TongueLashed,
)
from games.tamandua_murundus.systems import (
    D1_INSECT_CAP,
    InsectDriftSystem,
    MurunduSystem,
    TongueSystem,
)
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher

ARENA = Rect(0, 0, 800, 600)


class Recorder:
    """Collects dispatched events of one type, in order."""

    def __init__(self, dispatcher: EventDispatcher, event_type: type) -> None:
        self.events: list = []
        dispatcher.subscribe(event_type, self.events.append)


def make_mound(
    entity_manager: EntityManager, position: Vector2, **kwargs
) -> tuple[str, Murundu]:
    """Stand one mound up and return its id and component."""
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=position))
    mound = Murundu(**kwargs)
    entity.add_component(mound)
    return entity.id, mound


def insect_count(entity_manager: EntityManager) -> int:
    """How many insects are alive."""
    return sum(1 for _ in entity_manager.get_entities_with(Insect))


class TestMurunduFeeding:
    def test_a_mound_releases_an_insect_when_its_timer_expires(self) -> None:
        entity_manager = EntityManager()
        make_mound(entity_manager, Vector2(400, 300), feed_interval=1.0, feed_timer=0.0)
        system = MurunduSystem(
            entity_manager, EventDispatcher(), ARENA, RandomStream(seed=1)
        )

        system.update(0.1)

        assert insect_count(entity_manager) == 1

    def test_a_mound_waits_out_its_interval(self) -> None:
        entity_manager = EntityManager()
        make_mound(entity_manager, Vector2(400, 300), feed_interval=1.0, feed_timer=1.0)
        system = MurunduSystem(
            entity_manager, EventDispatcher(), ARENA, RandomStream(seed=1)
        )

        system.update(0.1)

        assert insect_count(entity_manager) == 0

    def test_a_released_insect_starts_beside_its_mound(self) -> None:
        """Not on top of it -- an insect spawned at the centre is hidden
        by the mound it came out of."""
        entity_manager = EntityManager()
        make_mound(entity_manager, Vector2(400, 300), feed_timer=0.0)
        MurunduSystem(
            entity_manager, EventDispatcher(), ARENA, RandomStream(seed=1)
        ).update(0.1)

        insect = next(iter(entity_manager.get_entities_with(Insect)))
        offset = insect.get_component(Transform).position - Vector2(400, 300)

        assert offset.magnitude == pytest.approx(38.0, abs=0.5)

    def test_a_released_insect_remembers_its_anchor(self) -> None:
        entity_manager = EntityManager()
        mound_id, _ = make_mound(entity_manager, Vector2(400, 300), feed_timer=0.0)
        MurunduSystem(
            entity_manager, EventDispatcher(), ARENA, RandomStream(seed=1)
        ).update(0.1)

        insect = next(iter(entity_manager.get_entities_with(Insect)))

        assert insect.get_component(Insect).anchor == mound_id

    def test_a_broken_mound_stops_feeding(self) -> None:
        """The whole point of breaking one."""
        entity_manager = EntityManager()
        make_mound(entity_manager, Vector2(400, 300), feed_timer=0.0, broken=True)
        MurunduSystem(
            entity_manager, EventDispatcher(), ARENA, RandomStream(seed=1)
        ).update(1.0)

        assert insect_count(entity_manager) == 0

    def test_the_cap_holds_across_every_mound(self) -> None:
        """The cap is on the clearing, not on each mound -- five mounds
        must not each get their own allowance."""
        entity_manager = EntityManager()
        for _ in range(5):
            make_mound(
                entity_manager, Vector2(400, 300), feed_interval=0.01, feed_timer=0.0
            )
        system = MurunduSystem(
            entity_manager, EventDispatcher(), ARENA, RandomStream(seed=1)
        )

        for _ in range(200):
            system.update(0.05)

        assert insect_count(entity_manager) == D1_INSECT_CAP


class TestMurunduBreaking:
    def test_damage_below_the_threshold_does_not_break_it(self) -> None:
        entity_manager = EntityManager()
        mound_id, mound = make_mound(entity_manager, Vector2(1, 1), health=3.0)
        system = MurunduSystem(
            entity_manager, EventDispatcher(), ARENA, RandomStream(seed=1)
        )

        assert system.damage(mound_id, 1.0) is False
        assert mound.broken is False
        assert mound.health == pytest.approx(2.0)

    def test_the_last_hit_breaks_it_and_announces_it(self) -> None:
        entity_manager = EntityManager()
        dispatcher = EventDispatcher()
        broken = Recorder(dispatcher, MurunduBroken)
        mound_id, mound = make_mound(entity_manager, Vector2(1, 1), health=1.0)
        system = MurunduSystem(entity_manager, dispatcher, ARENA, RandomStream(seed=1))

        assert system.damage(mound_id, 1.0) is True
        assert mound.broken is True
        assert len(broken.events) == 1

    def test_the_break_event_counts_what_is_left(self) -> None:
        """The HUD reads this; an off-by-one here is visible."""
        entity_manager = EntityManager()
        dispatcher = EventDispatcher()
        broken = Recorder(dispatcher, MurunduBroken)
        first, _ = make_mound(entity_manager, Vector2(1, 1), health=1.0)
        make_mound(entity_manager, Vector2(2, 2), health=1.0)
        make_mound(entity_manager, Vector2(3, 3), health=1.0)
        system = MurunduSystem(entity_manager, dispatcher, ARENA, RandomStream(seed=1))

        system.damage(first, 1.0)

        assert broken.events[0].remaining == 2

    def test_an_already_broken_mound_cannot_break_twice(self) -> None:
        """Two hits in the same frame would otherwise fire two events and
        double the shake."""
        entity_manager = EntityManager()
        dispatcher = EventDispatcher()
        broken = Recorder(dispatcher, MurunduBroken)
        mound_id, _ = make_mound(entity_manager, Vector2(1, 1), health=1.0)
        system = MurunduSystem(entity_manager, dispatcher, ARENA, RandomStream(seed=1))

        system.damage(mound_id, 1.0)
        system.damage(mound_id, 1.0)

        assert len(broken.events) == 1

    def test_damaging_something_that_is_not_a_mound_is_ignored(self) -> None:
        entity_manager = EntityManager()
        system = MurunduSystem(
            entity_manager, EventDispatcher(), ARENA, RandomStream(seed=1)
        )

        assert system.damage("no-such-entity", 1.0) is False


def make_insect(
    entity_manager: EntityManager, position: Vector2, velocity: Vector2
) -> Transform:
    """Put one insect in the world and return its transform."""
    entity = entity_manager.create_entity()
    transform = Transform(position=position)
    entity.add_component(transform)
    entity.add_component(Insect(velocity=velocity))
    return transform


class TestInsectDrift:
    def test_an_insect_moves_along_its_velocity(self) -> None:
        entity_manager = EntityManager()
        transform = make_insect(entity_manager, Vector2(400, 300), Vector2(100.0, 0.0))

        InsectDriftSystem(entity_manager, ARENA).update(0.1)

        assert transform.position.x > 400.0

    def test_an_insect_turns_back_at_the_edge(self) -> None:
        """Turns rather than clamps: a clamped insect piles up against the
        boundary and the clearing grows a rim of stuck sprites."""
        entity_manager = EntityManager()
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(ARENA.right - 1, 300)))
        insect = Insect(velocity=Vector2(400.0, 0.0))
        entity.add_component(insect)

        InsectDriftSystem(entity_manager, ARENA).update(0.1)

        assert insect.velocity.x < 0.0

    def test_an_insect_stays_inside_the_clearing(self) -> None:
        entity_manager = EntityManager()
        transform = make_insect(
            entity_manager,
            Vector2(ARENA.right - 2, ARENA.bottom - 2),
            Vector2(600.0, 600.0),
        )
        system = InsectDriftSystem(entity_manager, ARENA)

        for _ in range(120):
            system.update(0.016)

        assert ARENA.left <= transform.position.x <= ARENA.right
        assert ARENA.top <= transform.position.y <= ARENA.bottom


def tongue_scene(
    insect_at: Vector2, facing: float = 0.0
) -> tuple[TongueSystem, EntityManager, Tamandua, Recorder, Recorder]:
    """An anteater at (400, 300) and one insect, both in the index."""
    entity_manager = EntityManager()
    dispatcher = EventDispatcher()
    lashed = Recorder(dispatcher, TongueLashed)
    killed = Recorder(dispatcher, InsectKilled)
    index: SpatialHash[str] = SpatialHash()

    hunter_entity = entity_manager.create_entity()
    hunter_entity.add_component(Transform(position=Vector2(400, 300)))
    hunter = Tamandua(facing=facing)
    hunter_entity.add_component(hunter)

    insect = entity_manager.create_entity()
    insect.add_component(Transform(position=insect_at))
    insect.add_component(Insect())
    index.insert(insect.id, insect_at)

    return (
        TongueSystem(entity_manager, dispatcher, index),
        entity_manager,
        hunter,
        lashed,
        killed,
    )


class TestTongue:
    def test_an_insect_straight_ahead_is_lashed(self) -> None:
        system, _, _, lashed, _ = tongue_scene(Vector2(480, 300))

        system.update(0.1)

        assert len(lashed.events) == 1

    def test_an_insect_behind_is_not_lashed(self) -> None:
        """The tongue reaches into an arc, not a circle -- otherwise the
        anteater eats things it is walking away from."""
        system, _, _, lashed, _ = tongue_scene(Vector2(320, 300))

        system.update(0.1)

        assert lashed.events == []

    def test_an_insect_out_of_range_is_not_lashed(self) -> None:
        system, _, _, lashed, _ = tongue_scene(Vector2(900, 300))

        system.update(0.1)

        assert lashed.events == []

    def test_the_arc_follows_the_facing(self) -> None:
        """The same insect, reachable or not depending on which way the
        anteater is pointed."""
        behind, _, _, missed, _ = tongue_scene(Vector2(320, 300), facing=0.0)
        behind.update(0.1)

        ahead, _, _, hit, _ = tongue_scene(Vector2(320, 300), facing=math.pi)
        ahead.update(0.1)

        assert missed.events == []
        assert len(hit.events) == 1

    def test_a_killed_insect_is_removed_and_announced(self) -> None:
        system, entity_manager, _, _, killed = tongue_scene(Vector2(480, 300))

        system.update(0.1)

        assert insect_count(entity_manager) == 0
        assert len(killed.events) == 1

    def test_the_tongue_respects_its_cooldown(self) -> None:
        """Otherwise it lashes once per frame and the clearing empties in
        a second."""
        system, entity_manager, hunter, lashed, _ = tongue_scene(Vector2(480, 300))
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(470, 300)))
        entity.add_component(Insect())

        system.update(0.001)
        system.update(0.001)

        assert len(lashed.events) == 1
        assert hunter.tongue_cooldown > 0.0

    def test_the_cooldown_expires(self) -> None:
        system, _, hunter, _, _ = tongue_scene(Vector2(480, 300))

        system.update(0.1)
        system.update(hunter.tongue_interval + 0.01)

        assert hunter.tongue_cooldown == pytest.approx(0.0)

    def test_nothing_to_lash_leaves_the_cooldown_alone(self) -> None:
        """A lash into empty air would put the tongue on cooldown for
        nothing, so the one moment it is needed it is not ready."""
        system, _, hunter, lashed, _ = tongue_scene(Vector2(900, 300))

        system.update(0.1)

        assert lashed.events == []
        assert hunter.tongue_cooldown == pytest.approx(0.0)
