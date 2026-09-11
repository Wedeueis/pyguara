"""Tests for `pyguara/kits/action_combat/` (Health, HealthSystem, apply_damage)."""

from __future__ import annotations

from typing import Any

from pyguara.common.modifiers import ModifiableValue
from pyguara.ecs.manager import EntityManager
from pyguara.kits.action_combat import (
    ARMOR_STAT,
    RESISTANCE_STAT,
    DamageDealt,
    Health,
    HealthSystem,
    apply_damage,
)
from pyguara.kits.stats import (
    DamageType,
    StatBlock,
    effective_defense,
    mitigation_from_defense,
)

# ========== Health ==========


def test_health_defaults_are_alive_and_not_invincible() -> None:
    health = Health()

    assert health.is_alive is True
    assert health.is_invincible is False


def test_health_is_not_alive_at_zero() -> None:
    health = Health(current=0.0)

    assert health.is_alive is False


def test_health_is_invincible_while_timer_is_positive() -> None:
    health = Health(invincible_timer=0.5)

    assert health.is_invincible is True


def test_health_attaches_to_an_entity() -> None:
    manager = EntityManager()
    entity = manager.create_entity()

    entity.add_component(Health(current=50.0, max_health=100.0))

    assert entity.has_component(Health)
    assert entity.get_component(Health).current == 50.0


# ========== HealthSystem ==========


def test_health_system_ticks_the_timer_down() -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    entity.add_component(Health(invincible_timer=1.0))
    system = HealthSystem(manager)

    system.update(0.4)

    assert entity.get_component(Health).invincible_timer == 0.6


def test_health_system_floors_the_timer_at_zero() -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    entity.add_component(Health(invincible_timer=0.3))
    system = HealthSystem(manager)

    system.update(1.0)

    assert entity.get_component(Health).invincible_timer == 0.0


def test_health_system_leaves_a_non_invincible_entity_alone() -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    entity.add_component(Health(invincible_timer=0.0))
    system = HealthSystem(manager)

    system.update(1.0)  # must not raise or go negative

    assert entity.get_component(Health).invincible_timer == 0.0


# ========== apply_damage ==========


def _dispatched(dispatcher: Any) -> list[DamageDealt]:
    events: list[DamageDealt] = []
    dispatcher.subscribe(DamageDealt, events.append)
    return events


def test_basic_damage_with_no_stats_applies_in_full(event_dispatcher: Any) -> None:
    health = Health(current=100.0, max_health=100.0)
    events = _dispatched(event_dispatcher)

    apply_damage(event_dispatcher, "e1", health, 20.0, DamageType.TRUE)

    assert health.current == 80.0
    assert events[0].amount == 20.0
    assert events[0].target == "e1"


def test_critical_hit_multiplies_damage(event_dispatcher: Any) -> None:
    health = Health(current=100.0, max_health=100.0)
    events = _dispatched(event_dispatcher)

    apply_damage(
        event_dispatcher,
        "e1",
        health,
        10.0,
        DamageType.TRUE,
        is_critical=True,
        crit_multiplier=2.0,
    )

    assert health.current == 80.0
    assert events[0].amount == 20.0
    assert events[0].is_critical is True


def test_true_damage_skips_mitigation_even_with_stats(event_dispatcher: Any) -> None:
    health = Health(current=100.0)
    stats = StatBlock(stats={ARMOR_STAT: ModifiableValue(1000.0)})

    apply_damage(
        event_dispatcher, "e1", health, 20.0, DamageType.TRUE, target_stats=stats
    )

    assert health.current == 80.0  # full damage, armor ignored


def test_physical_damage_is_mitigated_by_armor(event_dispatcher: Any) -> None:
    health = Health(current=100.0)
    stats = StatBlock(stats={ARMOR_STAT: ModifiableValue(50.0)})
    events = _dispatched(event_dispatcher)

    apply_damage(
        event_dispatcher, "e1", health, 20.0, DamageType.PHYSICAL, target_stats=stats
    )

    expected_mitigation = mitigation_from_defense(
        effective_defense(50.0, 0.0), scaling=50.0
    )
    expected_damage = 20.0 * (1 - expected_mitigation)
    assert events[0].amount == expected_damage
    assert health.current == 100.0 - expected_damage


def test_elemental_damage_reads_the_resistance_stat(event_dispatcher: Any) -> None:
    health = Health(current=100.0)
    stats = StatBlock(
        stats={
            ARMOR_STAT: ModifiableValue(999.0),
            RESISTANCE_STAT: ModifiableValue(0.0),
        }
    )

    apply_damage(
        event_dispatcher, "e1", health, 20.0, DamageType.ELEMENTAL, target_stats=stats
    )

    # Zero resistance -> zero mitigation -> full damage, regardless of armor.
    assert health.current == 80.0


def test_pierce_reduces_effective_defense(event_dispatcher: Any) -> None:
    health_a = Health(current=100.0)
    health_b = Health(current=100.0)
    stats = StatBlock(stats={ARMOR_STAT: ModifiableValue(50.0)})

    apply_damage(
        event_dispatcher, "a", health_a, 20.0, DamageType.PHYSICAL, target_stats=stats
    )
    apply_damage(
        event_dispatcher,
        "b",
        health_b,
        20.0,
        DamageType.PHYSICAL,
        target_stats=stats,
        pierce_fraction=0.5,
    )

    # More pierce -> less mitigation -> more damage taken.
    assert health_b.current < health_a.current


def test_no_stats_given_skips_mitigation(event_dispatcher: Any) -> None:
    health = Health(current=100.0)

    apply_damage(
        event_dispatcher, "e1", health, 20.0, DamageType.PHYSICAL, target_stats=None
    )

    assert health.current == 80.0


def test_invincible_target_takes_no_damage(event_dispatcher: Any) -> None:
    health = Health(current=100.0, invincible_timer=1.0)
    events = _dispatched(event_dispatcher)

    apply_damage(event_dispatcher, "e1", health, 20.0, DamageType.TRUE)

    assert health.current == 100.0
    assert events[0].amount == 0.0


def test_invincibility_duration_is_granted_on_a_successful_hit(
    event_dispatcher: Any,
) -> None:
    health = Health(current=100.0)

    apply_damage(
        event_dispatcher,
        "e1",
        health,
        20.0,
        DamageType.TRUE,
        invincibility_duration=1.5,
    )

    assert health.invincible_timer == 1.5


def test_default_invincibility_duration_grants_none(event_dispatcher: Any) -> None:
    health = Health(current=100.0)

    apply_damage(event_dispatcher, "e1", health, 20.0, DamageType.TRUE)

    assert health.invincible_timer == 0.0


def test_zero_damage_does_not_grant_invincibility(event_dispatcher: Any) -> None:
    health = Health(current=100.0)
    stats = StatBlock(stats={ARMOR_STAT: ModifiableValue(0.0)})

    apply_damage(
        event_dispatcher,
        "e1",
        health,
        0.0,
        DamageType.PHYSICAL,
        target_stats=stats,
        invincibility_duration=1.0,
    )

    assert health.invincible_timer == 0.0


def test_damage_never_takes_health_below_zero(event_dispatcher: Any) -> None:
    health = Health(current=10.0)

    apply_damage(event_dispatcher, "e1", health, 999.0, DamageType.TRUE)

    assert health.current == 0.0


def test_killed_flag_is_true_when_the_hit_is_lethal(event_dispatcher: Any) -> None:
    health = Health(current=10.0)
    events = _dispatched(event_dispatcher)

    apply_damage(event_dispatcher, "e1", health, 999.0, DamageType.TRUE)

    assert events[0].killed is True


def test_killed_flag_is_false_otherwise(event_dispatcher: Any) -> None:
    health = Health(current=100.0)
    events = _dispatched(event_dispatcher)

    apply_damage(event_dispatcher, "e1", health, 10.0, DamageType.TRUE)

    assert events[0].killed is False


def test_attacker_is_forwarded_to_the_event(event_dispatcher: Any) -> None:
    health = Health(current=100.0)
    events = _dispatched(event_dispatcher)

    apply_damage(event_dispatcher, "e1", health, 10.0, DamageType.TRUE, attacker="e2")

    assert events[0].attacker == "e2"


def test_apply_damage_returns_the_dispatched_event(event_dispatcher: Any) -> None:
    health = Health(current=100.0)

    result = apply_damage(event_dispatcher, "e1", health, 10.0, DamageType.TRUE)

    assert isinstance(result, DamageDealt)
    assert result.amount == 10.0
