"""Physics-related event definitions.

This module defines events emitted by the physics system, including collision
events (for solid bodies) and trigger events (for sensor volumes).

Events are dispatched through the EventDispatcher and can be subscribed to
by game systems and components.

Usage:
    from pyguara.physics.events import OnCollisionBegin

    def on_collision(event: OnCollisionBegin) -> None:
        print(f"Collision between {event.entity_a} and {event.entity_b}")
        print(f"Impact force: {event.impulse}")

    event_dispatcher.subscribe(OnCollisionBegin, on_collision)
"""

from dataclasses import dataclass
from typing import Any, Optional

from pyguara.common.types import Vector2
from pyguara.events.protocols import Event


@dataclass
class CollisionEvent(Event):
    """Base class for collision events between solid physics bodies.

    Collision events are fired when two non-sensor colliders interact.
    They provide detailed information about the collision including contact
    points, normals, and impulse forces.

    Attributes:
        entity_a: ID of the first entity involved in the collision.
        entity_b: ID of the second entity involved in the collision.
        point: World coordinates of the collision contact point.
        normal: Surface normal at the collision point (pointing from A to B).
        impulse: Magnitude of the collision impulse (impact force).
        timestamp: Time when the event occurred (seconds since epoch).
        source: Entity that triggered the event (collision system).
    """

    entity_a: str
    entity_b: str
    point: Vector2
    normal: Vector2
    impulse: float = 0.0
    timestamp: float = 0.0
    source: Optional[Any] = None


@dataclass
class OnCollisionBegin(CollisionEvent):
    """Fired when two bodies START colliding.

    This event is triggered on the first frame of contact between two physics
    bodies. Use this to respond to initial impacts (e.g., play sound effects,
    apply damage, spawn particles).

    Example:
        def on_collision_start(event: OnCollisionBegin) -> None:
            if event.impulse > 100:
                # Play crash sound for hard impacts
                audio.play_sound("crash.wav")
    """

    pass


@dataclass
class OnCollisionEnd(CollisionEvent):
    """Fired when two bodies STOP colliding.

    This event is triggered when two bodies separate after being in contact.
    Useful for cleanup logic or state changes when objects are no longer
    touching.

    Note:
        impulse is typically 0.0 for collision end events since no force
        is applied during separation.

    Example:
        def on_collision_end(event: OnCollisionEnd) -> None:
            # Stop sound effect when objects separate
            audio.stop_sound("friction_loop.wav")
    """

    pass


@dataclass
class OnCollisionPersist(CollisionEvent):
    """Fired each frame while two bodies remain in contact.

    This event is triggered every physics step (typically 60 FPS) while two
    bodies are touching. Use this for continuous effects like friction sounds
    or cumulative damage over time.

    Warning:
        This event fires frequently (60+ times per second) for sustained
        contact. Avoid expensive operations in handlers.

    Example:
        def on_collision_persist(event: OnCollisionPersist) -> None:
            # Apply continuous friction damage
            if event.impulse > 50:
                apply_damage(event.entity_a, damage=0.1)
    """

    pass


@dataclass
class TriggerEvent(Event):
    """Base class for sensor/trigger volume events.

    Trigger events are fired when entities enter, exit, or remain inside
    trigger volumes (sensor colliders). Unlike collision events, trigger
    events don't involve physical forces or contact points.

    Attributes:
        trigger_entity: ID of the entity with the trigger volume (sensor).
        other_entity: ID of the entity that entered/exited the trigger.
        timestamp: Time when the event occurred (seconds since epoch).
        source: Entity that triggered the event (collision system).
    """

    trigger_entity: str
    other_entity: str
    timestamp: float = 0.0
    source: Optional[Any] = None


@dataclass
class OnTriggerEnter(TriggerEvent):
    """Entity ENTERS a trigger volume.

    Fired when an entity first enters a sensor collider (trigger volume).
    Use this for gameplay mechanics like checkpoints, collectibles, zones,
    and proximity detection.

    Example:
        def on_checkpoint_enter(event: OnTriggerEnter) -> None:
            if event.other_entity == player_id:
                save_checkpoint(event.trigger_entity)
                show_message("Checkpoint activated!")
    """

    pass


@dataclass
class OnTriggerExit(TriggerEvent):
    """Entity EXITS a trigger volume.

    Fired when an entity leaves a sensor collider after being inside.
    Use this for cleanup logic, deactivating zones, or tracking departures.

    Example:
        def on_danger_zone_exit(event: OnTriggerExit) -> None:
            if event.other_entity == player_id:
                stop_damage_over_time()
                ui.hide_warning_indicator()
    """

    pass


@dataclass
class OnTriggerStay(TriggerEvent):
    """Entity remains inside a trigger volume.

    Fired each physics step (typically 60 FPS) while an entity stays inside
    a sensor collider. Use for continuous effects within zones.

    Warning:
        This event fires frequently (60+ times per second) while inside the
        trigger. Avoid expensive operations in handlers.

    Example:
        def on_healing_zone_stay(event: OnTriggerStay) -> None:
            if event.other_entity == player_id:
                heal_player(amount=0.5)  # Heal slowly over time
    """

    pass
