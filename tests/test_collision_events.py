"""Tests for physics collision event system."""

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

        def on_collision(event: OnCollisionBegin) -> None:
            received_events.append(event)

        dispatcher.subscribe(OnCollisionBegin, on_collision)

        # Simulate collision begin
        result = collision_system.on_collision_begin(
            entity_a="entity1",
            entity_b="entity2",
            point=Vector2(100, 200),
            normal=Vector2(0, 1),
            impulse=50.0,
            is_sensor=False,
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

        def on_collision_persist(event: OnCollisionPersist) -> None:
            received_events.append(event)

        dispatcher.subscribe(OnCollisionPersist, on_collision_persist)

        # Simulate collision persist
        result = collision_system.on_collision_persist(
            entity_a="entity1",
            entity_b="entity2",
            point=Vector2(100, 200),
            normal=Vector2(0, 1),
            impulse=25.0,
            is_sensor=False,
        )

        assert result is True
        assert len(received_events) == 1
        assert received_events[0].impulse == 25.0

    def test_collision_end_event(self):
        """Collision end should dispatch OnCollisionEnd event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []

        def on_collision_end(event: OnCollisionEnd) -> None:
            received_events.append(event)

        dispatcher.subscribe(OnCollisionEnd, on_collision_end)

        # Start collision first
        collision_system.on_collision_begin(
            "entity1", "entity2", Vector2.zero(), Vector2(0, 1), 50.0, False
        )

        # End collision
        collision_system.on_collision_end("entity1", "entity2", is_sensor=False)

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

        # Start collision
        collision_system.on_collision_begin(
            "entity1", "entity2", Vector2.zero(), Vector2(0, 1), 50.0, False
        )

        assert collision_system.get_active_collision_count() == 1
        assert collision_system.is_colliding("entity1", "entity2") is True
        assert (
            collision_system.is_colliding("entity2", "entity1") is True
        )  # Order-independent

        # End collision
        collision_system.on_collision_end("entity1", "entity2", is_sensor=False)

        assert collision_system.get_active_collision_count() == 0
        assert collision_system.is_colliding("entity1", "entity2") is False

    def test_multiple_active_collisions(self):
        """CollisionSystem should track multiple collisions simultaneously."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        # Start three separate collisions
        collision_system.on_collision_begin(
            "e1", "e2", Vector2.zero(), Vector2(0, 1), 50.0, False
        )
        collision_system.on_collision_begin(
            "e2", "e3", Vector2.zero(), Vector2(0, 1), 30.0, False
        )
        collision_system.on_collision_begin(
            "e1", "e3", Vector2.zero(), Vector2(0, 1), 40.0, False
        )

        assert collision_system.get_active_collision_count() == 3
        assert collision_system.is_colliding("e1", "e2") is True
        assert collision_system.is_colliding("e2", "e3") is True
        assert collision_system.is_colliding("e1", "e3") is True

        # End one collision
        collision_system.on_collision_end("e1", "e2", is_sensor=False)

        assert collision_system.get_active_collision_count() == 2
        assert collision_system.is_colliding("e1", "e2") is False
        assert collision_system.is_colliding("e2", "e3") is True

    def test_clear_state(self):
        """clear_state should remove all tracked collisions and triggers."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        # Add collisions
        collision_system.on_collision_begin(
            "e1", "e2", Vector2.zero(), Vector2(0, 1), 50.0, False
        )
        collision_system.on_collision_begin(
            "e2", "e3", Vector2.zero(), Vector2(0, 1), 30.0, False
        )

        # Add triggers
        collision_system.on_collision_begin(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, True
        )

        assert collision_system.get_active_collision_count() > 0
        assert collision_system.get_active_trigger_count() > 0

        # Clear state
        collision_system.clear_state()

        assert collision_system.get_active_collision_count() == 0
        assert collision_system.get_active_trigger_count() == 0


class TestTriggerEvents:
    """Test trigger/sensor event handling."""

    def test_trigger_enter_event(self):
        """Sensor collision should dispatch OnTriggerEnter event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []

        def on_trigger_enter(event: OnTriggerEnter) -> None:
            received_events.append(event)

        dispatcher.subscribe(OnTriggerEnter, on_trigger_enter)

        # Simulate trigger enter
        result = collision_system.on_collision_begin(
            entity_a="trigger1",
            entity_b="player",
            point=Vector2.zero(),
            normal=Vector2(0, 1),
            impulse=0.0,
            is_sensor=True,
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

        def on_trigger_stay(event: OnTriggerStay) -> None:
            received_events.append(event)

        dispatcher.subscribe(OnTriggerStay, on_trigger_stay)

        # Start trigger first
        collision_system.on_collision_begin(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, True
        )

        # Trigger persist
        collision_system.on_collision_persist(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, True
        )

        assert len(received_events) == 1
        assert received_events[0].trigger_entity == "trigger1"
        assert received_events[0].other_entity == "player"

    def test_trigger_exit_event(self):
        """Sensor end should dispatch OnTriggerExit event."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        received_events = []

        def on_trigger_exit(event: OnTriggerExit) -> None:
            received_events.append(event)

        dispatcher.subscribe(OnTriggerExit, on_trigger_exit)

        # Start trigger
        collision_system.on_collision_begin(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, True
        )

        # End trigger
        collision_system.on_collision_end("trigger1", "player", is_sensor=True)

        assert len(received_events) == 1
        assert received_events[0].trigger_entity == "trigger1"
        assert received_events[0].other_entity == "player"

    def test_trigger_tracking(self):
        """CollisionSystem should track active triggers."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        # Enter trigger
        collision_system.on_collision_begin(
            "trigger1", "player", Vector2.zero(), Vector2(0, 1), 0.0, True
        )

        assert collision_system.get_active_trigger_count() == 1
        assert collision_system.is_in_trigger("trigger1", "player") is True

        # Exit trigger
        collision_system.on_collision_end("trigger1", "player", is_sensor=True)

        assert collision_system.get_active_trigger_count() == 0
        assert collision_system.is_in_trigger("trigger1", "player") is False

    def test_multiple_entities_in_trigger(self):
        """Multiple entities can be in same trigger."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        # Two entities enter trigger
        collision_system.on_collision_begin(
            "trigger1", "player1", Vector2.zero(), Vector2(0, 1), 0.0, True
        )
        collision_system.on_collision_begin(
            "trigger1", "player2", Vector2.zero(), Vector2(0, 1), 0.0, True
        )

        assert collision_system.get_active_trigger_count() == 2
        assert collision_system.is_in_trigger("trigger1", "player1") is True
        assert collision_system.is_in_trigger("trigger1", "player2") is True

        # One exits
        collision_system.on_collision_end("trigger1", "player1", is_sensor=True)

        assert collision_system.get_active_trigger_count() == 1
        assert collision_system.is_in_trigger("trigger1", "player1") is False
        assert collision_system.is_in_trigger("trigger1", "player2") is True


class TestEventSequences:
    """Test realistic event sequences."""

    def test_collision_sequence(self):
        """Test complete collision lifecycle: begin -> persist -> end."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        begin_events = []
        persist_events = []
        end_events = []

        dispatcher.subscribe(OnCollisionBegin, lambda e: begin_events.append(e))
        dispatcher.subscribe(OnCollisionPersist, lambda e: persist_events.append(e))
        dispatcher.subscribe(OnCollisionEnd, lambda e: end_events.append(e))

        # Begin
        collision_system.on_collision_begin(
            "e1", "e2", Vector2(100, 100), Vector2(0, 1), 50.0, False
        )

        # Persist (multiple frames)
        for i in range(5):
            collision_system.on_collision_persist(
                "e1", "e2", Vector2(100, 100), Vector2(0, 1), 30.0 - i, False
            )

        # End
        collision_system.on_collision_end("e1", "e2", is_sensor=False)

        assert len(begin_events) == 1
        assert len(persist_events) == 5
        assert len(end_events) == 1

    def test_trigger_sequence(self):
        """Test complete trigger lifecycle: enter -> stay -> exit."""
        dispatcher = EventDispatcher()
        collision_system = CollisionSystem(dispatcher)

        enter_events = []
        stay_events = []
        exit_events = []

        dispatcher.subscribe(OnTriggerEnter, lambda e: enter_events.append(e))
        dispatcher.subscribe(OnTriggerStay, lambda e: stay_events.append(e))
        dispatcher.subscribe(OnTriggerExit, lambda e: exit_events.append(e))

        # Enter
        collision_system.on_collision_begin(
            "checkpoint", "player", Vector2.zero(), Vector2(0, 1), 0.0, True
        )

        # Stay (multiple frames)
        for i in range(3):
            collision_system.on_collision_persist(
                "checkpoint", "player", Vector2.zero(), Vector2(0, 1), 0.0, True
            )

        # Exit
        collision_system.on_collision_end("checkpoint", "player", is_sensor=True)

        assert len(enter_events) == 1
        assert len(stay_events) == 3
        assert len(exit_events) == 1
