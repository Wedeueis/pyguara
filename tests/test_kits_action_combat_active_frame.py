"""Tests for `pyguara/kits/action_combat/active_frame.py` + `active_frame_system.py`."""

from __future__ import annotations

from typing import Any

from pyguara.ecs.manager import EntityManager
from pyguara.graphics.events import AnimationFrameEvent
from pyguara.kits.action_combat import ActiveFrameSystem, ActiveFrameWindow
from pyguara.physics.trigger_volume import TriggerVolume


def _make_entity(manager: EntityManager, active: bool = False):
    entity = manager.create_entity()
    entity.add_component(TriggerVolume(active=active))
    entity.add_component(
        ActiveFrameWindow(activate_on="swing_start", deactivate_on="swing_end")
    )
    return entity


def _fire(dispatcher: Any, entity_id: str, name: str) -> None:
    dispatcher.dispatch(
        AnimationFrameEvent(entity_id=entity_id, clip_name="attack", name=name)
    )


def test_activate_on_turns_the_trigger_volume_active(event_dispatcher: Any) -> None:
    manager = EntityManager()
    ActiveFrameSystem(manager, event_dispatcher)
    entity = _make_entity(manager, active=False)

    _fire(event_dispatcher, entity.id, "swing_start")

    assert entity.get_component(TriggerVolume).active is True


def test_deactivate_on_turns_it_back_off(event_dispatcher: Any) -> None:
    manager = EntityManager()
    ActiveFrameSystem(manager, event_dispatcher)
    entity = _make_entity(manager, active=True)

    _fire(event_dispatcher, entity.id, "swing_end")

    assert entity.get_component(TriggerVolume).active is False


def test_an_unrelated_event_name_is_ignored(event_dispatcher: Any) -> None:
    manager = EntityManager()
    ActiveFrameSystem(manager, event_dispatcher)
    entity = _make_entity(manager, active=False)

    _fire(event_dispatcher, entity.id, "footstep")

    assert entity.get_component(TriggerVolume).active is False


def test_an_entity_without_active_frame_window_is_ignored(
    event_dispatcher: Any,
) -> None:
    manager = EntityManager()
    ActiveFrameSystem(manager, event_dispatcher)
    entity = manager.create_entity()
    entity.add_component(TriggerVolume(active=False))

    _fire(event_dispatcher, entity.id, "swing_start")  # must not raise

    assert entity.get_component(TriggerVolume).active is False


def test_an_entity_without_a_trigger_volume_is_ignored(event_dispatcher: Any) -> None:
    manager = EntityManager()
    ActiveFrameSystem(manager, event_dispatcher)
    entity = manager.create_entity()
    entity.add_component(
        ActiveFrameWindow(activate_on="swing_start", deactivate_on="swing_end")
    )

    _fire(event_dispatcher, entity.id, "swing_start")  # must not raise


def test_an_unknown_entity_id_does_not_raise(event_dispatcher: Any) -> None:
    manager = EntityManager()
    ActiveFrameSystem(manager, event_dispatcher)

    _fire(event_dispatcher, "ghost", "swing_start")  # must not raise


def test_update_is_a_noop(event_dispatcher: Any) -> None:
    manager = EntityManager()
    system = ActiveFrameSystem(manager, event_dispatcher)

    system.update(0.016)  # must not raise
