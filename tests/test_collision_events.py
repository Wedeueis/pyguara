"""Tests for physics collision event system.

The backend hands ``CollisionSystem`` a contact pair in Chipmunk's own,
arbitrary order plus ``sensor_entity_id`` -- which of the two owns the sensor
shape, or None for a solid collision. These tests drive that contract
directly; ``test_trigger_volumes.py`` covers the end-to-end path through the
real pymunk backend.
"""

from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.events import (
    OnCollisionBegin,
    OnCollisionEnd,
    OnCollisionPersist,
    OnTriggerEnter,
    OnTriggerExit,
    OnTriggerStay,
)


class TestCollisionSystemBasics:
    """Test basic CollisionSystem functionality."""

    def test_collision_system_creation(self):
        """CollisionSystem should be created with EventDispatcher."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        assert collision_system is not None
        assert collision_system.get_active_collision_count() == 0
        assert collision_system.get_active_trigger_count() == 0

    def test_collision_begin_event(self):
        """Collision begin should dispatch OnCollisionBegin event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []
        dispatcher.subscribe(OnCollisionBegin, received_events.append)

        result = collision_system.on_collision_begin(
            entity_a="entity1",
            entity_b="entity2",
            point=Vector2(100, 200),
            normal=Vector2(0, 1),
            impulse=50.0,
            sensor_entity_id=None,
        )

        assert result is True  # Physical collision should return True
        assert len(received_events) == 1
        assert received_events[0].entity_a == "entity1"
        assert received_events[0].entity_b == "entity2"
        assert received_events[0].point == Vector2(100, 200)
        assert received_events[0].normal == Vector2(0, 1)
        assert received_events[0].impulse == 50.0

    def test_collision_persist_event(self):
        """Collision persist should dispatch OnCollisionPersist event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []
        dispatcher.subscribe(OnCollisionPersist, received_events.append)

        result = collision_system.on_collision_persist(
            entity_a="entity1",
            entity_b="entity2",
            point=Vector2(100, 200),
            normal=Vector2(0, 1),
            impulse=25.0,
            sensor_entity_id=None,
        )

        assert result is True
        assert len(received_events) == 1
        assert received_events[0].impulse == 25.0

    def test_collision_end_event(self):
        """Collision end should dispatch OnCollisionEnd event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []
        dispatcher.subscribe(OnCollisionEnd, received_events.append)

        collision_system.on_collision_begin(
            "entity1", "entity2", Vector2.zero(), Vector2(0, 1), 50.0, None
        )
        collision_system.on_collision_end("entity1", "entity2", None)

        assert len(received_events) == 1
        assert received_events[0].entity_a == "entity1"
        assert received_events[0].entity_b == "entity2"
        assert received_events[0].impulse == 0.0  # No impulse on end


class TestCollisionTracking:
    """Test collision state tracking."""

    def test_active_collision_tracking(self):
        """CollisionSystem should track active collisions."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        collision_system.on_collision_begin(
            "entity1", "entity2", Vector2.zero(), Vector2(0, 1), 50.0, None
        )

        assert collision_system.get_active_collision_count() == 1
        assert collision_system.is_colliding("entity1", "entity2") is True
        assert collision_system.is_colliding("entity2", "entity1") is True

        collision_system.on_collision_end("entity1", "entity2", None)

        assert collision_system.get_active_collision_count() == 0
        assert collision_system.is_colliding("entity1", "entity2") is False

    def test_multiple_active_collisions(self):
        """CollisionSystem should track multiple collisions simultaneously."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        collision_system.on_collision_begin(
            "e1", "e2", Vector2.zero(), Vector2(0, 1), 50.0, None
        )
        collision_system.on_collision_begin(
            "e2", "e3", Vector2.zero(), Vector2(0, 1), 30.0, None
        )
        collision_system.on_collision_begin(
            "e1", "e3", Vector2.zero(), Vector2(0, 1), 40.0, None
        )

        assert collision_system.get_active_collision_count() == 3
        assert collision_system.is_colliding("e1", "e2") is True
        assert collision_system.is_colliding("e2", "e3") is True
        assert collision_system.is_colliding("e1", "e3") is True

        collision_system.on_collision_end("e1", "e2", None)

        assert collision_system.get_active_collision_count() == 2
        assert collision_system.is_colliding("e1", "e2") is False
        assert collision_system.is_colliding("e2", "e3") is True

    def test_clear_state(self):
        """clear_state should remove all tracked collisions and triggers."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        collision_system.on_collision_begin(
            "e1", "e2", Vector2.zero(), Vector2(0, 1), 50.0, None
        )
        collision_system.on_collision_begin(
            "e2", "e3", Vector2.zero(), Vector2(0, 1), 30.0, None
        )
        collision_system.on_collision_begin(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, "trigger1"
        )

        assert collision_system.get_active_collision_count() > 0
        assert collision_system.get_active_trigger_count() > 0

        collision_system.clear_state()

        assert collision_system.get_active_collision_count() == 0
        assert collision_system.get_active_trigger_count() == 0


class TestTriggerEvents:
    """Test trigger/sensor event handling, sensor passed as entity_a."""

    def test_trigger_enter_event(self):
        """Sensor collision should dispatch OnTriggerEnter event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []
        dispatcher.subscribe(OnTriggerEnter, received_events.append)

        result = collision_system.on_collision_begin(
            entity_a="trigger1",
            entity_b="player",
            point=Vector2.zero(),
            normal=Vector2(0, 1),
            impulse=0.0,
            sensor_entity_id="trigger1",
        )

        assert result is False  # Sensors should return False
        assert len(received_events) == 1
        assert received_events[0].trigger_entity == "trigger1"
        assert received_events[0].other_entity == "player"

    def test_trigger_stay_event(self):
        """Sensor persist should dispatch OnTriggerStay event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []
        dispatcher.subscribe(OnTriggerStay, received_events.append)

        collision_system.on_collision_begin(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, "trigger1"
        )
        collision_system.on_collision_persist(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, "trigger1"
        )

        assert len(received_events) == 1
        assert received_events[0].trigger_entity == "trigger1"
        assert received_events[0].other_entity == "player"

    def test_trigger_exit_event(self):
        """Sensor end should dispatch OnTriggerExit event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []
        dispatcher.subscribe(OnTriggerExit, received_events.append)

        collision_system.on_collision_begin(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, "trigger1"
        )
        collision_system.on_collision_end("trigger1", "player", "trigger1")

        assert len(received_events) == 1
        assert received_events[0].trigger_entity == "trigger1"
        assert received_events[0].other_entity == "player"

    def test_trigger_tracking(self):
        """CollisionSystem should track active triggers."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        collision_system.on_collision_begin(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, "trigger1"
        )

        assert collision_system.get_active_trigger_count() == 1
        assert collision_system.is_in_trigger("trigger1", "player") is True

        collision_system.on_collision_end("trigger1", "player", "trigger1")

        assert collision_system.get_active_trigger_count() == 0
        assert collision_system.is_in_trigger("trigger1", "player") is False

    def test_multiple_entities_in_trigger(self):
        """Multiple entities can be in same trigger."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        collision_system.on_collision_begin(
            "trigger1", "player1", Vector2.zero(), Vector2(0, 1), 0.0, "trigger1"
        )
        collision_system.on_collision_begin(
            "trigger1", "player2", Vector2.zero(), Vector2(0, 1), 0.0, "trigger1"
        )

        assert collision_system.get_active_trigger_count() == 2
        assert collision_system.is_in_trigger("trigger1", "player1") is True
        assert collision_system.is_in_trigger("trigger1", "player2") is True

        collision_system.on_collision_end("trigger1", "player1", "trigger1")

        assert collision_system.get_active_trigger_count() == 1
        assert collision_system.is_in_trigger("trigger1", "player1") is False
        assert collision_system.is_in_trigger("trigger1", "player2") is True


class TestTriggerRoleOrdering:
    """The sensor must land as ``trigger_entity`` regardless of pair order.

    Chipmunk reports a contact pair in an order the engine does not control,
    so the sensor arrives as ``entity_a`` on some pairs and ``entity_b`` on
    others. Before ``sensor_entity_id`` existed, ``CollisionSystem`` assumed
    ``entity_a`` was always the trigger; the events then came out with
    ``trigger_entity`` and ``other_entity`` swapped, and ``TriggerSystem``
    dropped every one whose "trigger" had no ``TriggerVolume``.
    """

    def test_sensor_as_entity_b_enter(self):
        """Sensor passed second still becomes the trigger_entity on enter."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        events = []
        dispatcher.subscribe(OnTriggerEnter, events.append)

        result = collision_system.on_collision_begin(
            entity_a="player",
            entity_b="zone",
            point=Vector2.zero(),
            normal=Vector2(0, 1),
            impulse=0.0,
            sensor_entity_id="zone",
        )

        assert result is False
        assert len(events) == 1
        assert events[0].trigger_entity == "zone"
        assert events[0].other_entity == "player"

    def test_sensor_as_entity_b_stay_and_exit(self):
        """Stay and exit route by the sensor id too, not by pair position."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        stay, exit_ = [], []
        dispatcher.subscribe(OnTriggerStay, stay.append)
        dispatcher.subscribe(OnTriggerExit, exit_.append)

        collision_system.on_collision_begin(
            "player", "zone", Vector2.zero(), Vector2(0, 1), 0.0, "zone"
        )
        collision_system.on_collision_persist(
            "player", "zone", Vector2.zero(), Vector2(0, 1), 0.0, "zone"
        )
        collision_system.on_collision_end("player", "zone", "zone")

        assert [(e.trigger_entity, e.other_entity) for e in stay] == [
            ("zone", "player")
        ]
        assert [(e.trigger_entity, e.other_entity) for e in exit_] == [
            ("zone", "player")
        ]
        assert collision_system.is_in_trigger("zone", "player") is False

    def test_tracking_query_order_matches_event_order(self):
        """is_in_trigger takes (trigger, other); enter stored it that way."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        collision_system.on_collision_begin(
            "player", "zone", Vector2.zero(), Vector2(0, 1), 0.0, "zone"
        )

        assert collision_system.is_in_trigger("zone", "player") is True
        assert collision_system.get_active_trigger_count() == 1


class TestEventSequences:
    """Test realistic event sequences."""

    def test_collision_sequence(self):
        """Test complete collision lifecycle: begin -> persist -> end."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        begin_events, persist_events, end_events = [], [], []
        dispatcher.subscribe(OnCollisionBegin, begin_events.append)
        dispatcher.subscribe(OnCollisionPersist, persist_events.append)
        dispatcher.subscribe(OnCollisionEnd, end_events.append)

        collision_system.on_collision_begin(
            "e1", "e2", Vector2(100, 100), Vector2(0, 1), 50.0, None
        )
        for i in range(5):
            collision_system.on_collision_persist(
                "e1", "e2", Vector2(100, 100), Vector2(0, 1), 30.0 - i, None
            )
        collision_system.on_collision_end("e1", "e2", None)

        assert len(begin_events) == 1
        assert len(persist_events) == 5
        assert len(end_events) == 1

    def test_trigger_sequence(self):
        """Test complete trigger lifecycle: enter -> stay -> exit."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        enter_events, stay_events, exit_events = [], [], []
        dispatcher.subscribe(OnTriggerEnter, enter_events.append)
        dispatcher.subscribe(OnTriggerStay, stay_events.append)
        dispatcher.subscribe(OnTriggerExit, exit_events.append)

        collision_system.on_collision_begin(
            "checkpoint", "player", Vector2.zero(), Vector2(0, 1), 0.0, "checkpoint"
        )
        for _i in range(3):
            collision_system.on_collision_persist(
                "checkpoint", "player", Vector2.zero(), Vector2(0, 1), 0.0, "checkpoint"
            )
        collision_system.on_collision_end("checkpoint", "player", "checkpoint")

        assert len(enter_events) == 1
        assert len(stay_events) == 3
        assert len(exit_events) == 1
