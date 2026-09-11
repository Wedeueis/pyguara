"""Tests for `pyguara/kits/effects/` (Effect, EffectContainer, add/remove_effect,
EffectSystem)."""

from __future__ import annotations

from typing import Any

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.effects import (
    Effect,
    EffectContainer,
    EffectSystem,
    StackingRule,
    add_effect,
    remove_effect,
)


class _RecordingEffect(Effect):
    """Tracks on_apply()/on_remove() calls for assertions."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.applied_to: str | None = None
        self.removed_from: str | None = None

    def on_apply(self, entity_id: str, dispatcher: EventDispatcher) -> None:
        self.applied_to = entity_id

    def on_remove(self, entity_id: str, dispatcher: EventDispatcher) -> None:
        self.removed_from = entity_id


class _TickingEffect(Effect):
    """Overrides update() to also count ticks, while keeping expiry working."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.ticks = 0

    def update(self, dt: float) -> None:
        super().update(dt)
        self.ticks += 1


# ========== Effect ==========


def test_effect_key_defaults_to_the_class_name() -> None:
    effect = _RecordingEffect()

    assert effect.key == "_RecordingEffect"


def test_effect_key_can_be_overridden() -> None:
    effect = _RecordingEffect(key="poison")

    assert effect.key == "poison"


def test_permanent_effect_never_expires() -> None:
    effect = _RecordingEffect(duration=None)

    for _ in range(1000):
        effect.update(1.0)

    assert effect.is_expired is False


def test_timed_effect_expires_after_its_duration() -> None:
    effect = _RecordingEffect(duration=1.0)

    effect.update(0.5)
    assert effect.is_expired is False

    effect.update(0.6)
    assert effect.is_expired is True


def test_default_on_apply_and_on_remove_do_not_raise() -> None:
    effect = Effect()
    dispatcher = EventDispatcher()

    effect.on_apply("e1", dispatcher)  # must not raise
    effect.on_remove("e1", dispatcher)  # must not raise


def test_subclass_update_override_still_tracks_elapsed() -> None:
    effect = _TickingEffect(duration=1.0)

    effect.update(0.6)

    assert effect.ticks == 1
    assert effect.elapsed == 0.6
    assert effect.is_expired is False


# ========== EffectContainer ==========


def test_effect_container_attaches_to_an_entity() -> None:
    manager = EntityManager()
    entity = manager.create_entity()

    entity.add_component(EffectContainer())

    assert entity.has_component(EffectContainer)
    assert entity.get_component(EffectContainer).effects == []


def test_each_container_gets_its_own_list() -> None:
    a = EffectContainer()
    b = EffectContainer()

    a.effects.append(_RecordingEffect())

    assert b.effects == []


# ========== add_effect / remove_effect ==========


def test_add_effect_calls_on_apply_and_appends(event_dispatcher: Any) -> None:
    container = EffectContainer()
    effect = _RecordingEffect()

    result = add_effect(event_dispatcher, "e1", container, effect)

    assert result is True
    assert effect.applied_to == "e1"
    assert container.effects == [effect]


def test_remove_effect_calls_on_remove_and_discards(event_dispatcher: Any) -> None:
    container = EffectContainer()
    effect = _RecordingEffect()
    add_effect(event_dispatcher, "e1", container, effect)

    remove_effect(event_dispatcher, "e1", container, effect)

    assert effect.removed_from == "e1"
    assert container.effects == []


def test_remove_effect_not_present_is_a_noop(event_dispatcher: Any) -> None:
    container = EffectContainer()
    effect = _RecordingEffect()

    remove_effect(event_dispatcher, "e1", container, effect)  # must not raise

    assert effect.removed_from is None


def test_stack_rule_allows_multiple_same_key_instances(event_dispatcher: Any) -> None:
    container = EffectContainer()
    first = _RecordingEffect(key="poison")
    second = _RecordingEffect(key="poison")

    add_effect(event_dispatcher, "e1", container, first, stacking=StackingRule.STACK)
    add_effect(event_dispatcher, "e1", container, second, stacking=StackingRule.STACK)

    assert container.effects == [first, second]


def test_stack_rule_respects_max_stacks(event_dispatcher: Any) -> None:
    container = EffectContainer()
    for _ in range(2):
        add_effect(
            event_dispatcher,
            "e1",
            container,
            _RecordingEffect(key="poison"),
            stacking=StackingRule.STACK,
            max_stacks=2,
        )

    third = _RecordingEffect(key="poison")
    result = add_effect(
        event_dispatcher,
        "e1",
        container,
        third,
        stacking=StackingRule.STACK,
        max_stacks=2,
    )

    assert result is False
    assert third not in container.effects
    assert third.applied_to is None


def test_refresh_rule_resets_elapsed_without_adding_a_new_instance(
    event_dispatcher: Any,
) -> None:
    container = EffectContainer()
    first = _RecordingEffect(key="haste", duration=5.0)
    add_effect(event_dispatcher, "e1", container, first, stacking=StackingRule.REFRESH)
    first.update(3.0)
    assert first.elapsed == 3.0

    second = _RecordingEffect(key="haste", duration=5.0)
    result = add_effect(
        event_dispatcher, "e1", container, second, stacking=StackingRule.REFRESH
    )

    assert result is True
    assert first.elapsed == 0.0
    assert container.effects == [first]  # second was never installed
    assert second.applied_to is None


def test_ignore_rule_rejects_a_second_application(event_dispatcher: Any) -> None:
    container = EffectContainer()
    first = _RecordingEffect(key="shield")
    add_effect(event_dispatcher, "e1", container, first, stacking=StackingRule.IGNORE)

    second = _RecordingEffect(key="shield")
    result = add_effect(
        event_dispatcher, "e1", container, second, stacking=StackingRule.IGNORE
    )

    assert result is False
    assert container.effects == [first]
    assert second.applied_to is None


def test_replace_rule_removes_the_old_instance_first(event_dispatcher: Any) -> None:
    container = EffectContainer()
    first = _RecordingEffect(key="curse")
    add_effect(event_dispatcher, "e1", container, first, stacking=StackingRule.REPLACE)

    second = _RecordingEffect(key="curse")
    result = add_effect(
        event_dispatcher, "e1", container, second, stacking=StackingRule.REPLACE
    )

    assert result is True
    assert first.removed_from == "e1"
    assert container.effects == [second]


def test_different_keys_do_not_interfere_under_ignore(event_dispatcher: Any) -> None:
    container = EffectContainer()
    poison = _RecordingEffect(key="poison")
    burn = _RecordingEffect(key="burn")

    add_effect(event_dispatcher, "e1", container, poison, stacking=StackingRule.IGNORE)
    result = add_effect(
        event_dispatcher, "e1", container, burn, stacking=StackingRule.IGNORE
    )

    assert result is True
    assert container.effects == [poison, burn]


# ========== EffectSystem ==========


def test_effect_system_ticks_active_effects(event_dispatcher: Any) -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    container = EffectContainer()
    effect = _TickingEffect(duration=10.0)
    add_effect(event_dispatcher, entity.id, container, effect)
    entity.add_component(container)
    system = EffectSystem(manager, event_dispatcher)

    system.update(0.5)

    assert effect.ticks == 1
    assert effect.elapsed == 0.5


def test_effect_system_removes_an_expired_effect(event_dispatcher: Any) -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    container = EffectContainer()
    effect = _RecordingEffect(duration=1.0)
    add_effect(event_dispatcher, entity.id, container, effect)
    entity.add_component(container)
    system = EffectSystem(manager, event_dispatcher)

    system.update(1.5)

    assert container.effects == []
    assert effect.removed_from == entity.id


def test_effect_system_leaves_a_permanent_effect_alone(event_dispatcher: Any) -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    container = EffectContainer()
    effect = _RecordingEffect(duration=None)
    add_effect(event_dispatcher, entity.id, container, effect)
    entity.add_component(container)
    system = EffectSystem(manager, event_dispatcher)

    for _ in range(100):
        system.update(1.0)

    assert container.effects == [effect]


def test_effect_system_handles_no_effect_containers(event_dispatcher: Any) -> None:
    manager = EntityManager()
    system = EffectSystem(manager, event_dispatcher)

    system.update(1.0)  # must not raise


def test_expiring_one_effect_does_not_skip_ticking_the_next(
    event_dispatcher: Any,
) -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    container = EffectContainer()
    expiring = _TickingEffect(duration=0.4)
    survives = _TickingEffect(duration=10.0)
    add_effect(event_dispatcher, entity.id, container, expiring)
    add_effect(event_dispatcher, entity.id, container, survives)
    entity.add_component(container)
    system = EffectSystem(manager, event_dispatcher)

    system.update(0.5)

    assert expiring not in container.effects
    assert survives in container.effects
    assert survives.ticks == 1
