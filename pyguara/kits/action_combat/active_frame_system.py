"""Turns `AnimationFrameEvent` into `TriggerVolume.active` toggles."""

from __future__ import annotations

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.events import AnimationFrameEvent
from pyguara.kits.action_combat.active_frame import ActiveFrameWindow
from pyguara.physics.trigger_volume import TriggerVolume


class ActiveFrameSystem:
    """Sets a `Hitbox` entity's `TriggerVolume.active` from frame events.

    Purely event-driven -- `update()` is a no-op present only to satisfy
    `pyguara.systems.protocols.System` for `SystemManager` registration.
    `AnimationSystem` (registered separately) is what actually drives the
    entity's `Animator` and dispatches the `AnimationFrameEvent`s this
    reacts to.
    """

    def __init__(
        self, entity_manager: EntityManager, dispatcher: EventDispatcher
    ) -> None:
        """Subscribe to the frame event this system reacts to.

        Args:
            entity_manager: Source of the entity a fired event names.
            dispatcher: Subscribed to for `AnimationFrameEvent`.
        """
        self._entity_manager = entity_manager
        dispatcher.subscribe(AnimationFrameEvent, self._on_frame_event)

    def update(self, dt: float) -> None:
        """No-op: see class docstring."""

    def _on_frame_event(self, event: AnimationFrameEvent) -> None:
        entity = self._entity_manager.get_entity(event.entity_id)
        if entity is None or not entity.has_component(ActiveFrameWindow):
            return
        if not entity.has_component(TriggerVolume):
            return

        window = entity.get_component(ActiveFrameWindow)
        if event.name == window.activate_on:
            entity.get_component(TriggerVolume).active = True
        elif event.name == window.deactivate_on:
            entity.get_component(TriggerVolume).active = False
