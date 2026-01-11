"""System for managing trigger volume state and events.

The TriggerSystem subscribes to physics trigger events and automatically
updates TriggerVolume component state. It also ensures entities with
TriggerVolume components have the necessary sensor Colliders.

This system should be registered in the application bootstrap if you're
using TriggerVolumes in your game.
"""

from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.components import Collider
from pyguara.physics.events import OnTriggerEnter, OnTriggerExit
from pyguara.physics.trigger_volume import EntityTags, TriggerVolume


class TriggerSystem:
    """System that manages trigger volume state based on physics events.

    The TriggerSystem performs two main functions:
    1. Ensures entities with TriggerVolume have sensor Colliders
    2. Updates TriggerVolume.entities_inside based on trigger events

    This system must be initialized with EntityManager and EventDispatcher,
    typically during application bootstrap.

    Attributes:
        _entity_manager: EntityManager for querying entities.
        _event_dispatcher: EventDispatcher for subscribing to trigger events.
    """

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the trigger system.

        Args:
            entity_manager: EntityManager to access entities and components.
            event_dispatcher: EventDispatcher to subscribe to trigger events.
        """
        self._entity_manager = entity_manager
        self._event_dispatcher = event_dispatcher

        # Subscribe to trigger events
        self._event_dispatcher.subscribe(OnTriggerEnter, self._on_trigger_enter)
        self._event_dispatcher.subscribe(OnTriggerExit, self._on_trigger_exit)

    def update(self, delta_time: float) -> None:
        """Update trigger volumes.

        Creates sensor Colliders for entities that have TriggerVolume but no Collider.
        This is called each frame by the application loop.

        Args:
            delta_time: Time elapsed since last update (unused).
        """
        # Find entities with TriggerVolume but no Collider
        for entity in self._entity_manager.get_entities_with(TriggerVolume):
            if not entity.has_component(Collider):
                self._create_trigger_collider(entity)

    def _create_trigger_collider(self, entity: Entity) -> None:
        """Create a sensor Collider for a TriggerVolume entity.

        Args:
            entity: Entity with TriggerVolume component.
        """
        trigger_volume = entity.get_component(TriggerVolume)

        # Create sensor collider matching the trigger volume shape
        collider = Collider(
            shape_type=trigger_volume.shape_type,
            dimensions=trigger_volume.dimensions.copy(),
            is_sensor=True,  # Critical: must be a sensor
        )

        entity.add_component(collider)

    def _on_trigger_enter(self, event: OnTriggerEnter) -> None:
        """Handle entity entering a trigger volume.

        Args:
            event: Trigger enter event from physics system.
        """
        # Get trigger entity
        trigger_entity = self._entity_manager.get_entity(event.trigger_entity)
        if not trigger_entity or not trigger_entity.has_component(TriggerVolume):
            return

        trigger_volume = trigger_entity.get_component(TriggerVolume)

        # Check if trigger is active
        if not trigger_volume.active:
            return

        # Check tag filtering
        other_entity = self._entity_manager.get_entity(event.other_entity)
        if other_entity and trigger_volume.tags:
            # Get entity tags if present
            entity_tags = None
            if other_entity.has_component(EntityTags):
                entity_tags = other_entity.get_component(EntityTags).tags

            # Check if entity matches filter
            if not trigger_volume.matches_tags(entity_tags):
                return

        # Add entity to trigger
        trigger_volume.entities_inside.add(event.other_entity)

        # Handle one-shot triggers
        if trigger_volume.one_shot:
            trigger_volume.active = False

    def _on_trigger_exit(self, event: OnTriggerExit) -> None:
        """Handle entity exiting a trigger volume.

        Args:
            event: Trigger exit event from physics system.
        """
        # Get trigger entity
        trigger_entity = self._entity_manager.get_entity(event.trigger_entity)
        if not trigger_entity or not trigger_entity.has_component(TriggerVolume):
            return

        trigger_volume = trigger_entity.get_component(TriggerVolume)

        # Remove entity from trigger (even if inactive)
        trigger_volume.entities_inside.discard(event.other_entity)

    def clear_all_triggers(self) -> None:
        """Clear all entities from all trigger volumes.

        Useful for resetting game state or transitioning scenes.
        """
        for entity in self._entity_manager.get_entities_with(TriggerVolume):
            trigger_volume = entity.get_component(TriggerVolume)
            trigger_volume.clear()

    def get_triggers_containing(self, entity_id: str) -> list:
        """Get all trigger volumes that contain a specific entity.

        Args:
            entity_id: Entity ID to search for.

        Returns:
            List of entities with TriggerVolume containing the entity.
        """
        triggers = []
        for entity in self._entity_manager.get_entities_with(TriggerVolume):
            trigger_volume = entity.get_component(TriggerVolume)
            if trigger_volume.contains_entity(entity_id):
                triggers.append(entity)
        return triggers
