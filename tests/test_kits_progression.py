"""Tests for the progression kit.

Four things worth pinning down, and they are what the tests are grouped
by: a curve prices levels, a grant crosses as many of them as it reaches
without losing the remainder, an offer draws eligible cards without
repeating one, and a magnet pulls an orb in and says so.
"""

from __future__ import annotations

import pytest

import pyguara.kits.progression
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.progression import (
    Attracted,
    Experience,
    ExperienceGained,
    Geometric,
    LeveledUp,
    Linear,
    Magnet,
    MagnetSystem,
    PickupCollected,
    Table,
    Upgrade,
    UpgradeRecord,
    eligible,
    grant_experience,
    offer,
    take,
    times_taken,
)


class Recorder:
    """Collects dispatched events of one type, in order."""

    def __init__(self, dispatcher: EventDispatcher, event_type: type) -> None:
        self.events: list = []
        dispatcher.subscribe(event_type, self.events.append)


class TestCurves:
    def test_linear_adds_a_fixed_step_per_level(self) -> None:
        curve = Linear(base=100.0, step=50.0)

        assert curve.cost_for(1) == pytest.approx(100.0)
        assert curve.cost_for(3) == pytest.approx(200.0)

    def test_geometric_multiplies_per_level(self) -> None:
        curve = Geometric(base=100.0, growth=2.0)

        assert curve.cost_for(1) == pytest.approx(100.0)
        assert curve.cost_for(3) == pytest.approx(400.0)

    def test_a_table_reads_the_designers_numbers(self) -> None:
        curve = Table(costs=[10.0, 25.0, 80.0])

        assert curve.cost_for(2) == pytest.approx(25.0)

    def test_a_table_repeats_its_last_entry_past_the_end(self) -> None:
        """A table need only describe the levels worth hand-tuning; a run
        that outlasts it still gets an answer."""
        curve = Table(costs=[10.0, 25.0, 80.0])

        assert curve.cost_for(9) == pytest.approx(80.0)

    def test_an_empty_table_is_rejected_rather_than_returning_zero(self) -> None:
        """A zero cost would let one grant advance unbounded levels."""
        with pytest.raises(ValueError, match="must not be empty"):
            Table(costs=[]).cost_for(1)

    def test_a_curve_is_structurally_typed(self) -> None:
        """A `Protocol`, not an ABC: a game's bespoke curve is one method
        with nothing to inherit from."""
        from pyguara.kits.progression import LevelCurve

        class Flat:
            def cost_for(self, level: int) -> float:
                return 5.0

        assert isinstance(Flat(), LevelCurve)


def grant(amount: float, **kwargs) -> tuple[Experience, Recorder, Recorder, int]:
    """Grant `amount` to a fresh entity on a flat 100-per-level curve."""
    dispatcher = EventDispatcher()
    gained = Recorder(dispatcher, ExperienceGained)
    levelled = Recorder(dispatcher, LeveledUp)
    experience = Experience()
    crossed = grant_experience(
        dispatcher, "hero", experience, Table(costs=[100.0]), amount, **kwargs
    )
    return experience, gained, levelled, crossed


class TestGrantExperience:
    def test_a_grant_below_the_cost_does_not_level(self) -> None:
        experience, _, levelled, crossed = grant(40.0)

        assert experience.level == 1
        assert experience.current == pytest.approx(40.0)
        assert crossed == 0
        assert levelled.events == []

    def test_crossing_a_level_keeps_the_remainder(self) -> None:
        """Discarding the overshoot would make the same total worth less
        when it arrives in one lump than in pieces."""
        experience, _, _, crossed = grant(130.0)

        assert experience.level == 2
        assert experience.current == pytest.approx(30.0)
        assert crossed == 1

    def test_one_grant_can_cross_several_levels(self) -> None:
        """A boss early in a run. Each crossing gets its own event, so a
        listener owing one upgrade per level does not have to work out how
        many it missed."""
        experience, _, levelled, crossed = grant(350.0)

        assert experience.level == 4
        assert crossed == 3
        assert [event.level for event in levelled.events] == [2, 3, 4]

    def test_pending_levels_accumulate_for_the_game_to_spend(self) -> None:
        """The kit counts levels owed and never spends them -- it has no
        idea what a level is worth."""
        experience, _, _, _ = grant(350.0)

        assert experience.pending_levels == 3

    def test_total_is_lifetime_and_is_never_spent(self) -> None:
        experience, _, _, _ = grant(130.0)

        assert experience.total == pytest.approx(130.0)
        assert experience.current == pytest.approx(30.0)

    def test_many_small_grants_land_where_one_large_one_does(self) -> None:
        dispatcher = EventDispatcher()
        piecemeal = Experience()
        for _ in range(10):
            grant_experience(dispatcher, "hero", piecemeal, Table(costs=[100.0]), 35.0)
        lump, _, _, _ = grant(350.0)

        assert piecemeal.level == lump.level
        assert piecemeal.current == pytest.approx(lump.current)

    def test_the_gain_event_reports_the_settled_numbers(self) -> None:
        _, gained, _, _ = grant(130.0)

        assert len(gained.events) == 1
        assert gained.events[0].level == 2
        assert gained.events[0].current == pytest.approx(30.0)
        assert gained.events[0].amount == pytest.approx(130.0)

    def test_the_gain_event_lands_before_the_level_ups_it_caused(self) -> None:
        """So a listener redrawing an experience bar has already done it by
        the time another pushes a level-up scene over the top."""
        dispatcher = EventDispatcher()
        order: list[str] = []
        dispatcher.subscribe(ExperienceGained, lambda _: order.append("gained"))
        dispatcher.subscribe(LeveledUp, lambda _: order.append("levelled"))

        grant_experience(dispatcher, "hero", Experience(), Table(costs=[100.0]), 250.0)

        assert order == ["gained", "levelled", "levelled"]

    def test_a_zero_grant_still_dispatches(self) -> None:
        """Matching `DamageDealt`: a listener asking "did that pickup
        count" reads the amount, rather than needing a silence to mean it."""
        _, gained, _, _ = grant(0.0)

        assert len(gained.events) == 1
        assert gained.events[0].amount == pytest.approx(0.0)

    def test_a_negative_grant_is_ignored_rather_than_de_levelling(self) -> None:
        """Taking experience back is a different operation, and would need
        its own rules about dropping a level."""
        experience, _, _, _ = grant(-50.0)

        assert experience.current == pytest.approx(0.0)
        assert experience.total == pytest.approx(0.0)

    def test_a_max_level_stops_progression(self) -> None:
        experience, _, _, crossed = grant(1000.0, max_level=3)

        assert experience.level == 3
        assert crossed == 2

    def test_at_the_cap_progress_stops_accumulating(self) -> None:
        """A bar filling toward a level that will never arrive is worse
        than a full one."""
        experience, _, _, _ = grant(1000.0, max_level=3)

        assert experience.current == pytest.approx(0.0)

    def test_at_the_cap_total_still_counts_everything(self) -> None:
        """An end-of-run screen should report what was collected, not what
        was spendable."""
        experience, _, _, _ = grant(1000.0, max_level=3)

        assert experience.total == pytest.approx(1000.0)


def pool() -> list[Upgrade]:
    """Three independent cards plus one that requires the first twice."""
    return [
        Upgrade(key="whip", apply=lambda _: None, max_taken=None),
        Upgrade(key="bracer", apply=lambda _: None),
        Upgrade(key="boots", apply=lambda _: None),
        Upgrade(
            key="evolved_whip",
            apply=lambda _: None,
            requires={"whip": 2, "bracer": 1},
        ),
    ]


class TestEligibility:
    def test_an_untaken_upgrade_is_eligible(self) -> None:
        assert eligible(pool()[1], UpgradeRecord())

    def test_an_upgrade_at_its_limit_is_not_offered_again(self) -> None:
        record = UpgradeRecord(taken={"bracer": 1})

        assert not eligible(pool()[1], record)

    def test_an_unlimited_upgrade_stays_eligible(self) -> None:
        record = UpgradeRecord(taken={"whip": 9})

        assert eligible(pool()[0], record)

    def test_an_upgrade_with_unmet_requirements_is_not_offered(self) -> None:
        record = UpgradeRecord(taken={"whip": 1, "bracer": 1})

        assert not eligible(pool()[3], record)

    def test_meeting_every_requirement_unlocks_it(self) -> None:
        """Weapon evolution with no new type: `requires` plus the record
        already says "evolved whip needs whip x2 and the bracer"."""
        record = UpgradeRecord(taken={"whip": 2, "bracer": 1})

        assert eligible(pool()[3], record)


class TestOffer:
    def test_an_offer_draws_the_requested_count(self) -> None:
        drawn = offer(RandomStream(seed=1), pool(), UpgradeRecord(), count=3)

        assert len(drawn) == 3

    def test_an_offer_never_repeats_a_card(self) -> None:
        """Sampling is without replacement: the same upgrade twice in one
        pick is a bug the player can see."""
        drawn = offer(RandomStream(seed=7), pool(), UpgradeRecord(), count=3)

        assert len({upgrade.key for upgrade in drawn}) == len(drawn)

    def test_an_offer_only_contains_eligible_cards(self) -> None:
        record = UpgradeRecord(taken={"bracer": 1})

        drawn = offer(RandomStream(seed=3), pool(), record, count=4)

        assert "bracer" not in {upgrade.key for upgrade in drawn}
        assert "evolved_whip" not in {upgrade.key for upgrade in drawn}

    def test_an_exhausted_pool_offers_what_is_left(self) -> None:
        """A late run offers two cards rather than raising."""
        record = UpgradeRecord(taken={"bracer": 1, "boots": 1})

        drawn = offer(RandomStream(seed=3), pool(), record, count=3)

        assert [upgrade.key for upgrade in drawn] == ["whip"]

    def test_an_empty_pool_offers_nothing(self) -> None:
        assert offer(RandomStream(seed=3), [], UpgradeRecord()) == []

    def test_weights_bias_the_draw(self) -> None:
        heavy = Upgrade(key="heavy", apply=lambda _: None, weight=100.0, max_taken=None)
        light = Upgrade(key="light", apply=lambda _: None, weight=1.0, max_taken=None)
        rng = RandomStream(seed=11)

        firsts = [
            offer(rng, [heavy, light], UpgradeRecord(), count=1)[0].key
            for _ in range(50)
        ]

        assert firsts.count("heavy") > firsts.count("light")

    def test_an_all_zero_weight_pool_offers_nothing_rather_than_raising(self) -> None:
        """`weighted_choice` raises on a zero total, correctly -- but here
        it means the same thing as running out of cards."""
        zeroed = [Upgrade(key="a", apply=lambda _: None, weight=0.0)]

        assert offer(RandomStream(seed=1), zeroed, UpgradeRecord()) == []

    def test_the_same_seed_and_record_produce_the_same_offer(self) -> None:
        """What lets a run be replayed."""
        first = offer(RandomStream(seed=42), pool(), UpgradeRecord(), count=3)
        second = offer(RandomStream(seed=42), pool(), UpgradeRecord(), count=3)

        assert [u.key for u in first] == [u.key for u in second]


class TestTake:
    def test_taking_runs_the_upgrades_own_closure(self) -> None:
        """The kit never learns what an upgrade *does* -- the game wrote
        this closure over whatever its stats actually are."""
        applied: list[str] = []
        upgrade = Upgrade(key="whip", apply=applied.append)
        record = UpgradeRecord()

        take(record, upgrade, "hero")

        assert applied == ["hero"]

    def test_taking_records_the_count(self) -> None:
        record = UpgradeRecord()
        upgrade = Upgrade(key="whip", apply=lambda _: None, max_taken=None)

        take(record, upgrade, "hero")
        take(record, upgrade, "hero")

        assert times_taken(record, "whip") == 2

    def test_the_record_is_updated_before_the_closure_runs(self) -> None:
        """So an upgrade that scales with its own stack count sees the take
        it is part of, rather than the one before."""
        record = UpgradeRecord()
        seen: list[int] = []
        upgrade = Upgrade(
            key="whip",
            apply=lambda _: seen.append(times_taken(record, "whip")),
            max_taken=None,
        )

        take(record, upgrade, "hero")

        assert seen == [1]


def magnet_scene(
    orb_at: Vector2, radius: float = 100.0, collect_radius: float = 12.0
) -> tuple[MagnetSystem, EntityManager, Recorder, Transform, Attracted]:
    """A magnet at the origin and one orb, both in the spatial index."""
    entity_manager = EntityManager()
    dispatcher = EventDispatcher()
    collected = Recorder(dispatcher, PickupCollected)
    index: SpatialHash[str] = SpatialHash()

    hero = entity_manager.create_entity()
    hero.add_component(Transform(position=Vector2(0, 0)))
    hero.add_component(Magnet(radius=radius, speed=100.0, acceleration=0.0))

    orb = entity_manager.create_entity()
    orb_transform = Transform(position=orb_at)
    orb.add_component(orb_transform)
    pickup = Attracted(payload=7.0, collect_radius=collect_radius)
    orb.add_component(pickup)

    index.insert(hero.id, Vector2(0, 0))
    index.insert(orb.id, orb_at)

    return (
        MagnetSystem(entity_manager, dispatcher, index),
        entity_manager,
        collected,
        orb_transform,
        pickup,
    )


class TestMagnet:
    def test_an_orb_in_range_is_pulled_toward_the_magnet(self) -> None:
        system, _, _, orb, _ = magnet_scene(Vector2(50, 0))

        system.update(0.1)

        assert orb.position.x < 50.0

    def test_an_orb_out_of_range_is_left_alone(self) -> None:
        system, _, _, orb, _ = magnet_scene(Vector2(500, 0), radius=100.0)

        system.update(0.1)

        assert orb.position.x == pytest.approx(500.0)

    def test_an_inactive_orb_is_not_pulled(self) -> None:
        """A just-dropped orb can sit inert so it does not fly straight
        back into whoever dropped it."""
        system, _, _, orb, pickup = magnet_scene(Vector2(50, 0))
        pickup.active = False

        system.update(0.1)

        assert orb.position.x == pytest.approx(50.0)

    def test_an_orb_never_overshoots_the_magnet(self) -> None:
        """A fast orb one frame away should land on the magnet, not skip
        past it and be dragged back next frame."""
        system, _, _, orb, _ = magnet_scene(Vector2(10, 0))

        system.update(10.0)

        assert orb.position.x == pytest.approx(0.0)
        assert orb.position.y == pytest.approx(0.0)

    def test_reaching_the_collect_radius_dispatches_the_payload(self) -> None:
        system, _, collected, _, _ = magnet_scene(Vector2(10, 0))

        system.update(10.0)

        assert len(collected.events) == 1
        assert collected.events[0].payload == pytest.approx(7.0)

    def test_a_collected_orb_is_marked_inactive_not_destroyed(self) -> None:
        """Destroying it is the game's call -- it may want to pool it, or
        play something on it first."""
        system, entity_manager, collected, _, pickup = magnet_scene(Vector2(10, 0))

        system.update(10.0)

        assert not pickup.active
        assert entity_manager.get_entity(collected.events[0].pickup) is not None

    def test_an_orb_is_only_collected_once(self) -> None:
        system, _, collected, _, _ = magnet_scene(Vector2(10, 0))

        system.update(10.0)
        system.update(10.0)

        assert len(collected.events) == 1

    def test_the_event_names_who_collected_it(self) -> None:
        system, _, collected, _, _ = magnet_scene(Vector2(10, 0))

        system.update(10.0)

        assert collected.events[0].collector != collected.events[0].pickup

    def test_a_magnet_does_not_attract_itself(self) -> None:
        """A magnet that is also attractable would collect itself on the
        first frame."""
        entity_manager = EntityManager()
        dispatcher = EventDispatcher()
        collected = Recorder(dispatcher, PickupCollected)
        index: SpatialHash[str] = SpatialHash()

        both = entity_manager.create_entity()
        both.add_component(Transform(position=Vector2(0, 0)))
        both.add_component(Magnet(radius=100.0))
        both.add_component(Attracted(payload=1.0))
        index.insert(both.id, Vector2(0, 0))

        MagnetSystem(entity_manager, dispatcher, index).update(0.1)

        assert collected.events == []


class TestKitBoundaries:
    def test_the_kit_imports_no_other_kit(self) -> None:
        """`Upgrade.apply` being opaque is what buys this, and this is what
        proves it was not quietly spent: the kit composes with
        `kits.stats` and `kits.effects` without importing either, so a
        game is never obliged to model its upgrades as one of them.

        Parsed rather than grepped -- both are named in prose in this
        package, which is the point, and a substring search would read
        that as a violation.
        """
        import ast
        from pathlib import Path

        package = Path(pyguara.kits.progression.__file__).parent
        imported: set[str] = set()
        for path in package.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
                elif isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)

        other_kits = {
            module
            for module in imported
            if module.startswith("pyguara.kits.")
            and not module.startswith("pyguara.kits.progression")
        }
        assert other_kits == set()
