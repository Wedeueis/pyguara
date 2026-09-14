"""Tests for the XP motes: the pool, the drop, and what a mote is worth.

The demo runs on ModernGL and cannot boot headlessly, so these test the
rules directly -- no scene, no bootstrap, no renderer.
"""

from __future__ import annotations

import pytest

from games.tamandua_murundus.motes import MOTE_CAP, MOTE_VALUE, Motes
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.kits.progression import Attracted
from pyguara.spatial.components import SpatialTracked

ARENA = Rect(0, 0, 800, 600)


class FakeTexture:
    """A texture with a size and no pixels behind it."""

    width = 8
    height = 8
    path = "<insect>"


def make_motes(cap: int = 8) -> tuple[Motes, EntityManager]:
    """A small mote pool over a fresh world."""
    entity_manager = EntityManager()
    return (
        Motes(entity_manager, ARENA, RandomStream(seed=5), cap=cap),
        entity_manager,
    )


class TestDropping:
    def test_a_kill_leaves_a_mote(self) -> None:
        motes, _ = make_motes()

        motes.drop(Vector2(400, 300))

        assert motes.active_count == 1

    def test_a_mote_carries_what_it_is_worth(self) -> None:
        """`Attracted.payload` is opaque to the kit -- deciding a mote is
        worth experience is the game's job, and this is where it is said."""
        motes, _ = make_motes()

        mote = motes.drop(Vector2(400, 300), MOTE_VALUE)

        assert mote is not None
        assert mote.get_component(Attracted).payload == pytest.approx(MOTE_VALUE)

    def test_a_mote_scatters_from_the_kill(self) -> None:
        """Dropped on the spot, a cluster of kills stacks into one mote the
        player cannot judge the size of."""
        motes, _ = make_motes(cap=6)
        positions = {
            (
                mote.get_component(Transform).position.x,
                mote.get_component(Transform).position.y,
            )
            for mote in (motes.drop(Vector2(400, 300)) for _ in range(6))
            if mote is not None
        }

        assert len(positions) > 1

    def test_a_mote_stays_inside_the_clearing(self) -> None:
        """A kill at the edge must not scatter its mote out of reach."""
        motes, _ = make_motes()

        mote = motes.drop(Vector2(ARENA.right, ARENA.bottom))

        assert mote is not None
        position = mote.get_component(Transform).position
        assert ARENA.left <= position.x <= ARENA.right
        assert ARENA.top <= position.y <= ARENA.bottom

    def test_an_exhausted_pool_declines(self) -> None:
        """The cap doing its job: a clearing carpeted in uncollected
        experience reads as a bug, not as generosity."""
        motes, _ = make_motes(cap=2)

        motes.drop(Vector2(1, 1))
        motes.drop(Vector2(2, 2))

        assert motes.drop(Vector2(3, 3)) is None

    def test_the_shipping_cap_is_below_the_swarm_cap(self) -> None:
        """Motes only pile up if the player stops collecting entirely."""
        from games.tamandua_murundus.swarm import SWARM_CAP

        assert MOTE_CAP < SWARM_CAP


class TestPooling:
    def test_an_idle_mote_is_invisible_to_the_magnet(self) -> None:
        """The same trap `swarm.py` hit: a pooled entity is never
        destroyed, so an `Attracted` attached at construction would keep
        every mote in `MagnetSystem`'s candidate set for the life of the
        scene."""
        _, entity_manager = make_motes(cap=50)

        assert sum(1 for _ in entity_manager.get_entities_with(Attracted)) == 0

    def test_an_idle_mote_is_invisible_to_the_spatial_index(self) -> None:
        _, entity_manager = make_motes(cap=50)

        assert sum(1 for _ in entity_manager.get_entities_with(SpatialTracked)) == 0

    def test_dropping_makes_it_visible_to_both(self) -> None:
        motes, entity_manager = make_motes()

        motes.drop(Vector2(400, 300))

        assert sum(1 for _ in entity_manager.get_entities_with(Attracted)) == 1
        assert sum(1 for _ in entity_manager.get_entities_with(SpatialTracked)) == 1

    def test_collecting_takes_it_back_out_of_both(self) -> None:
        motes, entity_manager = make_motes()
        mote = motes.drop(Vector2(400, 300))
        assert mote is not None

        motes.collect(mote.id)

        assert motes.active_count == 0
        assert sum(1 for _ in entity_manager.get_entities_with(Attracted)) == 0
        assert sum(1 for _ in entity_manager.get_entities_with(SpatialTracked)) == 0

    def test_collecting_something_that_is_not_a_mote_is_ignored(self) -> None:
        """The scene hands this every `PickupCollected` it sees, rather
        than first working out whether the pickup was one of ours."""
        motes, _ = make_motes()

        motes.collect("no-such-entity")

        assert motes.active_count == 0

    def test_collecting_twice_is_ignored(self) -> None:
        motes, _ = make_motes()
        mote = motes.drop(Vector2(400, 300))
        assert mote is not None

        motes.collect(mote.id)
        motes.collect(mote.id)

        assert motes.active_count == 0

    def test_a_recycled_mote_carries_its_new_value(self) -> None:
        motes, _ = make_motes(cap=1)
        first = motes.drop(Vector2(1, 1), 1.0)
        assert first is not None
        motes.collect(first.id)

        second = motes.drop(Vector2(2, 2), 5.0)

        assert second is not None
        assert second.get_component(Attracted).payload == pytest.approx(5.0)


class TestSettling:
    def test_a_dropped_mote_drifts_then_stops(self) -> None:
        """The scatter decelerates to nothing.

        Asserted as *deceleration* rather than "stopped after N frames":
        the drift decays geometrically, so most of the distance is covered
        early and a naive cutoff measures the tail of the same motion
        rather than the end of it. What matters is that the mote is
        effectively still by the time a magnet could have hold of it --
        `MagnetSystem` owns the position from then on, and a second mover
        would fight it for the same `Transform`.
        """
        motes, _ = make_motes()
        mote = motes.drop(Vector2(400, 300))
        assert mote is not None
        transform = mote.get_component(Transform)

        start = transform.position
        for _ in range(10):
            motes.update(1.0 / 60.0)
        early = (transform.position - start).magnitude

        for _ in range(80):
            motes.update(1.0 / 60.0)

        before_last = transform.position
        for _ in range(10):
            motes.update(1.0 / 60.0)
        late = (transform.position - before_last).magnitude

        assert early > 0.0
        assert late < early / 100.0

    def test_settling_keeps_motes_in_the_clearing(self) -> None:
        motes, _ = make_motes()
        mote = motes.drop(Vector2(ARENA.right - 2, ARENA.bottom - 2))
        assert mote is not None

        for _ in range(120):
            motes.update(1.0 / 60.0)

        position = mote.get_component(Transform).position
        assert ARENA.left <= position.x <= ARENA.right
        assert ARENA.top <= position.y <= ARENA.bottom

    def test_an_empty_pool_settles_cheaply(self) -> None:
        motes, _ = make_motes()

        motes.update(1.0 / 60.0)

        assert motes.active_count == 0


class TestBatch:
    def test_the_motes_draw_in_one_tinted_batch(self) -> None:
        motes, _ = make_motes()
        for _ in range(3):
            motes.drop(Vector2(400, 300))

        batch = motes.build_batch(FakeTexture(), 1.0)

        assert len(batch.destinations) == 3
        assert batch.colors_enabled is True
        assert len(batch.colors) == len(batch.destinations)

    def test_motes_dim_with_the_clearing(self) -> None:
        """Otherwise they sit at full brightness through a bright dusk,
        which reads as the only lit thing in a daylit frame."""
        motes, _ = make_motes()
        motes.drop(Vector2(400, 300))

        dusk = motes.build_batch(FakeTexture(), 0.0)
        night = motes.build_batch(FakeTexture(), 1.0)

        assert night.colors[0][3] > dusk.colors[0][3]

    def test_an_empty_pool_builds_an_empty_batch(self) -> None:
        motes, _ = make_motes()

        assert motes.build_batch(FakeTexture(), 0.5).destinations == []


class TestTheLevelCurve:
    """The curve is tuned against a measured kill rate, and D5's card
    table is sized to the number of levels it produces. Nothing else stops
    those two drifting apart."""

    def test_a_measured_run_reaches_about_eight_levels(self) -> None:
        """The fit: D5 offers six to eight distinct upgrades, so a run
        should offer about as many picks as there are things to pick.

        Pinned against `MEASURED_RUN_YIELD` -- the experience a simulated
        orbiting player actually collected over one night -- rather than
        against the curve's own arithmetic, which would only prove the
        formula agrees with itself.
        """
        from games.tamandua_murundus.scenes import (
            LEVEL_CURVE,
            MEASURED_RUN_YIELD,
        )
        from pyguara.events.dispatcher import EventDispatcher
        from pyguara.kits.progression import Experience, grant_experience

        experience = Experience()
        grant_experience(
            EventDispatcher(), "hero", experience, LEVEL_CURVE, MEASURED_RUN_YIELD
        )

        assert 7 <= experience.level <= 9

    def test_an_idle_run_still_levels_at_least_once(self) -> None:
        """A player who barely engages should still see the mechanic --
        a run that never levels teaches nothing about progression."""
        from games.tamandua_murundus.scenes import LEVEL_CURVE
        from pyguara.events.dispatcher import EventDispatcher
        from pyguara.kits.progression import Experience, grant_experience

        experience = Experience()
        # What an idle player collected in the same simulation.
        grant_experience(EventDispatcher(), "hero", experience, LEVEL_CURVE, 19.0)

        assert experience.level >= 2

    def test_each_level_costs_more_than_the_last(self) -> None:
        from games.tamandua_murundus.scenes import LEVEL_CURVE

        costs = [LEVEL_CURVE.cost_for(level) for level in range(1, 9)]

        assert costs == sorted(costs)
        assert costs[0] < costs[-1]
