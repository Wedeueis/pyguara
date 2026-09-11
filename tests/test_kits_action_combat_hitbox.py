"""Tests for `pyguara/kits/action_combat/` Hitbox/Hurtbox/HitboxSystem."""

from __future__ import annotations

from typing import Any

from pyguara.common.modifiers import ModifiableValue
from pyguara.ecs.manager import EntityManager
from pyguara.kits.action_combat import (
    ARMOR_STAT,
    DamageDealt,
    Health,
    Hitbox,
    HitboxSystem,
    Hurtbox,
)
from pyguara.kits.stats import DamageType, StatBlock
from pyguara.physics.events import OnTriggerEnter

# ========== Hitbox / Hurtbox: plain data ==========


def test_hitbox_defaults() -> None:
    hitbox = Hitbox()

    assert hitbox.damage == 0.0
    assert hitbox.damage_type == DamageType.PHYSICAL
    assert hitbox.team is None


def test_hurtbox_attaches_to_an_entity() -> None:
    manager = EntityManager()
    entity = manager.create_entity()

    entity.add_component(Hurtbox(team="enemies"))

    assert entity.has_component(Hurtbox)
    assert entity.get_component(Hurtbox).team == "enemies"


# ========== HitboxSystem ==========


def _make_attacker(manager: EntityManager, **hitbox_kwargs: Any):
    attacker = manager.create_entity()
    attacker.add_component(Hitbox(**hitbox_kwargs))
    return attacker


def _make_target(
    manager: EntityManager, health: float = 100.0, team: str | None = None
):
    target = manager.create_entity()
    target.add_component(Health(current=health, max_health=health))
    target.add_component(Hurtbox(team=team))
    return target


def _enter(dispatcher: Any, trigger_entity: str, other_entity: str) -> None:
    dispatcher.dispatch(
        OnTriggerEnter(trigger_entity=trigger_entity, other_entity=other_entity)
    )


def test_hit_applies_damage(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(manager, damage=25.0, damage_type=DamageType.TRUE)
    target = _make_target(manager)

    _enter(event_dispatcher, attacker.id, target.id)

    assert target.get_component(Health).current == 75.0


def test_hit_dispatches_damage_dealt(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    events: list[DamageDealt] = []
    event_dispatcher.subscribe(DamageDealt, events.append)
    attacker = _make_attacker(manager, damage=10.0, damage_type=DamageType.TRUE)
    target = _make_target(manager)

    _enter(event_dispatcher, attacker.id, target.id)

    assert len(events) == 1
    assert events[0].target == target.id
    assert events[0].amount == 10.0


def test_trigger_without_a_hitbox_is_ignored(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    non_combat_trigger = manager.create_entity()  # no Hitbox
    target = _make_target(manager)

    _enter(event_dispatcher, non_combat_trigger.id, target.id)

    assert target.get_component(Health).current == 100.0


def test_target_without_a_hurtbox_is_ignored(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(manager, damage=10.0, damage_type=DamageType.TRUE)
    bystander = manager.create_entity()
    bystander.add_component(Health(current=100.0))  # no Hurtbox

    _enter(event_dispatcher, attacker.id, bystander.id)

    assert bystander.get_component(Health).current == 100.0


def test_target_without_health_is_ignored(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(manager, damage=10.0, damage_type=DamageType.TRUE)
    healthless = manager.create_entity()
    healthless.add_component(Hurtbox())  # no Health

    _enter(event_dispatcher, attacker.id, healthless.id)  # must not raise


def test_same_team_never_damages(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(
        manager, damage=10.0, damage_type=DamageType.TRUE, team="allies"
    )
    target = _make_target(manager, team="allies")

    _enter(event_dispatcher, attacker.id, target.id)

    assert target.get_component(Health).current == 100.0


def test_different_teams_damages(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(
        manager, damage=10.0, damage_type=DamageType.TRUE, team="enemies"
    )
    target = _make_target(manager, team="allies")

    _enter(event_dispatcher, attacker.id, target.id)

    assert target.get_component(Health).current == 90.0


def test_hitbox_with_no_team_damages_anyone(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(
        manager, damage=10.0, damage_type=DamageType.TRUE, team=None
    )
    target = _make_target(manager, team="allies")

    _enter(event_dispatcher, attacker.id, target.id)

    assert target.get_component(Health).current == 90.0


def test_hurtbox_with_no_team_is_hit_by_any_team(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(
        manager, damage=10.0, damage_type=DamageType.TRUE, team="enemies"
    )
    target = _make_target(manager, team=None)

    _enter(event_dispatcher, attacker.id, target.id)

    assert target.get_component(Health).current == 90.0


def test_target_stats_are_used_for_mitigation_when_present(
    event_dispatcher: Any,
) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(manager, damage=20.0, damage_type=DamageType.PHYSICAL)
    target = _make_target(manager)
    target.add_component(StatBlock(stats={ARMOR_STAT: ModifiableValue(50.0)}))

    _enter(event_dispatcher, attacker.id, target.id)

    # Unmitigated would be 100 - 20 = 80; 50 armor against the default
    # scaling=50 mitigates exactly half, landing at 90.
    assert target.get_component(Health).current == 90.0


def test_attacker_is_forwarded_to_the_damage_event(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    events: list[DamageDealt] = []
    event_dispatcher.subscribe(DamageDealt, events.append)
    attacker = _make_attacker(
        manager, damage=10.0, damage_type=DamageType.TRUE, attacker="player_1"
    )
    target = _make_target(manager)

    _enter(event_dispatcher, attacker.id, target.id)

    assert events[0].attacker == "player_1"


def test_critical_and_invincibility_duration_are_forwarded(
    event_dispatcher: Any,
) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)
    attacker = _make_attacker(
        manager,
        damage=10.0,
        damage_type=DamageType.TRUE,
        is_critical=True,
        invincibility_duration=1.0,
    )
    target = _make_target(manager)

    _enter(event_dispatcher, attacker.id, target.id)

    # crit_multiplier defaults to 1.5 in apply_damage(); 10 * 1.5 = 15.
    assert target.get_component(Health).current == 85.0
    assert target.get_component(Health).invincible_timer == 1.0


def test_unknown_entity_ids_do_not_raise(event_dispatcher: Any) -> None:
    manager = EntityManager()
    HitboxSystem(manager, event_dispatcher)

    _enter(event_dispatcher, "ghost-trigger", "ghost-target")  # must not raise


def test_update_is_a_noop(event_dispatcher: Any) -> None:
    manager = EntityManager()
    system = HitboxSystem(manager, event_dispatcher)

    system.update(0.016)  # must not raise
