"""Collision callback routing system.

This module provides the CollisionSystem, which bridges pymunk's collision
handlers to PyGuara's event system. It translates low-level physics callbacks
into high-level game events that can be subscribed to by game systems.

The CollisionSystem is registered as a singleton in the DI container and
automatically wired to the physics engine during application bootstrap.

Architecture:
    Pymunk Callbacks → CollisionSystem → EventDispatcher → Game Systems

Example:
    # Collision system is automatically registered during bootstrap
    # Subscribe to collision events in your scene or system:

    def on_enter(self):
        self.event_dispatcher.subscribe(OnCollisionBegin, self._on_collision)

    def _on_collision(self, event: OnCollisionBegin) -> None:
        print(f"Collision: {event.entity_a} <-> {event.entity_b}")
        print(f"Impact: {event.impulse}")
"""

import time
from typing import Dict, Set, Tuple

from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.events import (
    OnCollisionBegin,
    OnCollisionEnd,
    OnCollisionPersist,
    OnTriggerEnter,
    OnTriggerExit,
    OnTriggerStay,
)


class CollisionSystem:
    """Bridges pymunk collision handlers to PyGuara event system.

    The CollisionSystem maintains state about active collisions and triggers,
    ensuring that events are dispatched correctly and consistently. It's
    designed to be called by the physics engine's collision handlers.

    Attributes:
        _dispatcher: EventDispatcher for publishing collision events.
        _active_collisions: Set of entity pairs currently in collision.
        _active_triggers: Dict tracking which entities are in which triggers.
    """

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the collision system.

        Args:
            event_dispatcher: EventDispatcher instance for publishing events.
        """
        self._dispatcher = event_dispatcher

        # Track active collisions to distinguish begin/persist/end
        # Key: frozenset of (entity_a, entity_b)
        self._active_collisions: Set[frozenset[str]] = set()

        # Track active triggers
        # Key: (trigger_entity_id, other_entity_id), Value: True if active
        self._active_triggers: Dict[Tuple[str, str], bool] = {}

    def on_collision_begin(
        self,
        entity_a: str,
        entity_b: str,
        point: Vector2,
        normal: Vector2,
        impulse: float,
        is_sensor: bool,
    ) -> bool:
        """Handle collision begin event from physics engine.

        Args:
            entity_a: ID of first entity.
            entity_b: ID of second entity.
            point: Contact point in world coordinates.
            normal: Surface normal (from A to B).
            impulse: Collision impulse magnitude.
            is_sensor: True if either collider is a sensor.

        Returns:
            True to process collision physically, False to ignore.
        """
        if is_sensor:
            # Handle as trigger, not physical collision
            self._handle_trigger_begin(entity_a, entity_b)
            return False  # Don't process physically
        else:
            # Handle as physical collision
            collision_key = frozenset({entity_a, entity_b})
            self._active_collisions.add(collision_key)

            event = OnCollisionBegin(
                entity_a=entity_a,
                entity_b=entity_b,
                point=point,
                normal=normal,
                impulse=impulse,
                timestamp=time.time(),
            )
            self._dispatcher.dispatch(event)
            return True  # Process collision physically

    def on_collision_persist(
        self,
        entity_a: str,
        entity_b: str,
        point: Vector2,
        normal: Vector2,
        impulse: float,
        is_sensor: bool,
    ) -> bool:
        """Handle collision persist event from physics engine.

        Args:
            entity_a: ID of first entity.
            entity_b: ID of second entity.
            point: Contact point in world coordinates.
            normal: Surface normal (from A to B).
            impulse: Current collision impulse magnitude.
            is_sensor: True if either collider is a sensor.

        Returns:
            True to continue processing collision, False to ignore.
        """
        if is_sensor:
            # Handle as trigger
            self._handle_trigger_stay(entity_a, entity_b)
            return False
        else:
            # Dispatch persist event
            event = OnCollisionPersist(
                entity_a=entity_a,
                entity_b=entity_b,
                point=point,
                normal=normal,
                impulse=impulse,
                timestamp=time.time(),
            )
            self._dispatcher.dispatch(event)
            return True

    def on_collision_end(
        self,
        entity_a: str,
        entity_b: str,
        is_sensor: bool,
    ) -> None:
        """Handle collision end event from physics engine.

        Args:
            entity_a: ID of first entity.
            entity_b: ID of second entity.
            is_sensor: True if either collider is a sensor.
        """
        if is_sensor:
            # Handle as trigger
            self._handle_trigger_end(entity_a, entity_b)
        else:
            # Remove from active collisions
            collision_key = frozenset({entity_a, entity_b})
            self._active_collisions.discard(collision_key)

            # Dispatch end event
            # Note: No contact point/normal/impulse available at separation
            event = OnCollisionEnd(
                entity_a=entity_a,
                entity_b=entity_b,
                point=Vector2.zero(),
                normal=Vector2(0, 1),
                impulse=0.0,
                timestamp=time.time(),
            )
            self._dispatcher.dispatch(event)

    def _handle_trigger_begin(self, trigger_entity: str, other_entity: str) -> None:
        """Handle entity entering trigger volume.

        Args:
            trigger_entity: Entity with the sensor collider.
            other_entity: Entity that entered the trigger.
        """
        trigger_key = (trigger_entity, other_entity)
        reverse_key = (other_entity, trigger_entity)

        # Mark as active (handle both orderings)
        if trigger_key not in self._active_triggers:
            self._active_triggers[trigger_key] = True
            self._active_triggers[reverse_key] = True

            # Dispatch enter event
            event = OnTriggerEnter(
                trigger_entity=trigger_entity,
                other_entity=other_entity,
                timestamp=time.time(),
            )
            self._dispatcher.dispatch(event)

    def _handle_trigger_stay(self, trigger_entity: str, other_entity: str) -> None:
        """Handle entity staying in trigger volume.

        Args:
            trigger_entity: Entity with the sensor collider.
            other_entity: Entity still inside the trigger.
        """
        trigger_key = (trigger_entity, other_entity)

        if self._active_triggers.get(trigger_key, False):
            # Dispatch stay event
            event = OnTriggerStay(
                trigger_entity=trigger_entity,
                other_entity=other_entity,
                timestamp=time.time(),
            )
            self._dispatcher.dispatch(event)

    def _handle_trigger_end(self, trigger_entity: str, other_entity: str) -> None:
        """Handle entity exiting trigger volume.

        Args:
            trigger_entity: Entity with the sensor collider.
            other_entity: Entity that exited the trigger.
        """
        trigger_key = (trigger_entity, other_entity)
        reverse_key = (other_entity, trigger_entity)

        # Remove from active triggers
        if trigger_key in self._active_triggers:
            del self._active_triggers[trigger_key]
            del self._active_triggers[reverse_key]

            # Dispatch exit event
            event = OnTriggerExit(
                trigger_entity=trigger_entity,
                other_entity=other_entity,
                timestamp=time.time(),
            )
            self._dispatcher.dispatch(event)

    def clear_state(self) -> None:
        """Clear all tracked collision and trigger state.

        Useful when resetting physics simulation or transitioning scenes.
        """
        self._active_collisions.clear()
        self._active_triggers.clear()

    def get_active_collision_count(self) -> int:
        """Get number of active collisions.

        Returns:
            Number of entity pairs currently in collision.
        """
        return len(self._active_collisions)

    def get_active_trigger_count(self) -> int:
        """Get number of active trigger interactions.

        Returns:
            Number of entity pairs in trigger volumes.
        """
        return len(self._active_triggers) // 2  # Divide by 2 (bidirectional tracking)

    def is_colliding(self, entity_a: str, entity_b: str) -> bool:
        """Check if two entities are currently colliding.

        Args:
            entity_a: First entity ID.
            entity_b: Second entity ID.

        Returns:
            True if entities are in collision, False otherwise.
        """
        collision_key = frozenset({entity_a, entity_b})
        return collision_key in self._active_collisions

    def is_in_trigger(self, trigger_entity: str, other_entity: str) -> bool:
        """Check if an entity is inside a trigger volume.

        Args:
            trigger_entity: Entity with the sensor collider.
            other_entity: Entity to check.

        Returns:
            True if other_entity is inside trigger, False otherwise.
        """
        trigger_key = (trigger_entity, other_entity)
        return self._active_triggers.get(trigger_key, False)
