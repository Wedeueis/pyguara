"""Tests for system manager."""

import pytest

from pyguara.systems import SystemManager


class MockSystem:
    """Mock system for testing."""

    def __init__(self):
        """Initialize mock system."""
        self.updated = False
        self.update_count = 0
        self.last_dt = 0.0

    def update(self, dt: float) -> None:
        """Update system."""
        self.updated = True
        self.update_count += 1
        self.last_dt = dt


class MockInitializableSystem:
    """Mock system with initialization."""

    def __init__(self):
        """Initialize mock system."""
        self.initialized = False
        self.updated = False

    def initialize(self) -> None:
        """Initialize system."""
        self.initialized = True

    def update(self, dt: float) -> None:
        """Update system."""
        self.updated = True


class MockCleanupSystem:
    """Mock system with cleanup."""

    def __init__(self):
        """Initialize mock system."""
        self.cleaned_up = False
        self.updated = False

    def cleanup(self) -> None:
        """Cleanup system."""
        self.cleaned_up = True

    def update(self, dt: float) -> None:
        """Update system."""
        self.updated = True


class TestSystemManager:
    """Test system manager functionality."""

    def test_manager_creation(self):
        """SystemManager should initialize correctly."""
        manager = SystemManager()

        assert manager.system_count == 0
        assert manager.enabled
        assert not manager._initialized

    def test_register_system(self):
        """Should register systems."""
        manager = SystemManager()
        system = MockSystem()

        manager.register(system)

        assert manager.system_count == 1
        assert manager.has_system(MockSystem)

    def test_register_multiple_systems(self):
        """Should register multiple systems."""
        manager = SystemManager()
        system1 = MockSystem()
        system2 = MockInitializableSystem()

        manager.register(system1)
        manager.register(system2)

        assert manager.system_count == 2

    def test_register_without_update_raises_error(self):
        """Registering object without update() should raise ValueError."""
        manager = SystemManager()
        invalid_system = object()

        with pytest.raises(ValueError, match="update"):
            manager.register(invalid_system)

    def test_get_system(self):
        """Should retrieve registered systems by type."""
        manager = SystemManager()
        system = MockSystem()

        manager.register(system)

        retrieved = manager.get_system(MockSystem)
        assert retrieved is system

    def test_get_nonexistent_system(self):
        """Getting unregistered system should return None."""
        manager = SystemManager()

        result = manager.get_system(MockSystem)
        assert result is None

    def test_has_system(self):
        """Should check if system is registered."""
        manager = SystemManager()
        system = MockSystem()

        assert not manager.has_system(MockSystem)

        manager.register(system)

        assert manager.has_system(MockSystem)

    def test_unregister_system(self):
        """Should unregister systems."""
        manager = SystemManager()
        system = MockSystem()

        manager.register(system)
        assert manager.system_count == 1

        removed = manager.unregister(MockSystem)

        assert removed is system
        assert manager.system_count == 0
        assert not manager.has_system(MockSystem)

    def test_unregister_nonexistent_system(self):
        """Unregistering nonexistent system should return None."""
        manager = SystemManager()

        result = manager.unregister(MockSystem)
        assert result is None

    def test_update_systems(self):
        """Should update all registered systems."""
        manager = SystemManager()
        system1 = MockSystem()
        system2 = MockSystem()

        manager.register(system1)
        manager.register(system2)

        manager.update(0.016)

        assert system1.updated
        assert system2.updated
        assert system1.last_dt == 0.016
        assert system2.last_dt == 0.016

    def test_update_respects_priority(self):
        """Systems should update in priority order."""
        manager = SystemManager()

        update_order = []

        class OrderedSystem:
            def __init__(self, name):
                self.name = name

            def update(self, dt):
                update_order.append(self.name)

        system_a = OrderedSystem("A")
        system_b = OrderedSystem("B")
        system_c = OrderedSystem("C")

        # Register out of order
        manager.register(system_b, priority=200)
        manager.register(system_a, priority=100)
        manager.register(system_c, priority=300)

        manager.update(0.016)

        # Should update in priority order
        assert update_order == ["A", "B", "C"]

    def test_initialize_systems(self):
        """Should initialize InitializableSystem systems."""
        manager = SystemManager()
        system = MockInitializableSystem()

        manager.register(system)
        assert not system.initialized

        manager.initialize()

        assert system.initialized

    def test_initialize_only_once(self):
        """Should only initialize once."""
        manager = SystemManager()
        system = MockInitializableSystem()

        manager.register(system)

        manager.initialize()
        system.initialized = False  # Reset flag
        manager.initialize()  # Call again

        # Should not reinitialize
        assert not system.initialized

    def test_cleanup_systems(self):
        """Should cleanup CleanupSystem systems."""
        manager = SystemManager()
        system = MockCleanupSystem()

        manager.register(system)
        manager.cleanup()

        assert system.cleaned_up
        assert manager.system_count == 0

    def test_unregister_calls_cleanup(self):
        """Unregistering CleanupSystem should call cleanup."""
        manager = SystemManager()
        system = MockCleanupSystem()

        manager.register(system)
        manager.unregister(MockCleanupSystem)

        assert system.cleaned_up

    def test_set_enabled(self):
        """Should enable/disable system updates."""
        manager = SystemManager()
        system = MockSystem()

        manager.register(system)

        # Disable
        manager.set_enabled(False)
        assert not manager.enabled

        manager.update(0.016)
        assert not system.updated

        # Enable
        manager.set_enabled(True)
        assert manager.enabled

        manager.update(0.016)
        assert system.updated

    def test_get_all_systems(self):
        """Should get all systems in priority order."""
        manager = SystemManager()

        system1 = MockSystem()
        system2 = MockInitializableSystem()
        system3 = MockCleanupSystem()

        manager.register(system3, priority=300)
        manager.register(system1, priority=100)
        manager.register(system2, priority=200)

        all_systems = manager.get_all_systems()

        assert len(all_systems) == 3
        assert all_systems[0] is system1
        assert all_systems[1] is system2
        assert all_systems[2] is system3


class TestSystemManagerIntegration:
    """Test system manager integration patterns."""

    def test_physics_ai_animation_pattern(self):
        """Common pattern: physics, AI, then animation."""
        manager = SystemManager()

        update_order = []

        class PhysicsSystem:
            def update(self, dt):
                update_order.append("physics")

        class AISystem:
            def update(self, dt):
                update_order.append("ai")

        class AnimationSystem:
            def update(self, dt):
                update_order.append("animation")

        physics = PhysicsSystem()
        ai = AISystem()
        animation = AnimationSystem()

        # Register with explicit priorities
        manager.register(physics, priority=10)  # First
        manager.register(ai, priority=20)  # Second
        manager.register(animation, priority=30)  # Third

        manager.update(0.016)

        assert update_order == ["physics", "ai", "animation"]

    def test_system_lifecycle(self):
        """Test full system lifecycle: register, initialize, update, cleanup."""
        manager = SystemManager()

        class FullLifecycleSystem:
            def __init__(self):
                self.initialized = False
                self.update_count = 0
                self.cleaned_up = False

            def initialize(self):
                self.initialized = True

            def update(self, dt):
                if not self.initialized:
                    raise RuntimeError("Updated before initialized!")
                self.update_count += 1

            def cleanup(self):
                self.cleaned_up = True

        system = FullLifecycleSystem()

        # Register
        manager.register(system)
        assert not system.initialized

        # Initialize
        manager.initialize()
        assert system.initialized

        # Update multiple times
        manager.update(0.016)
        manager.update(0.016)
        assert system.update_count == 2

        # Cleanup
        manager.cleanup()
        assert system.cleaned_up
        assert manager.system_count == 0

    def test_scene_with_system_manager(self):
        """Pattern: scene using system manager."""
        manager = SystemManager()

        # Mock systems
        physics = MockSystem()
        ai = MockSystem()

        manager.register(physics, priority=10)
        manager.register(ai, priority=20)
        manager.initialize()

        # Simulate game loop
        for _ in range(60):  # 1 second at 60 FPS
            manager.update(1 / 60)

        assert physics.update_count == 60
        assert ai.update_count == 60

    def test_pause_all_systems(self):
        """Pattern: pause all systems (e.g., pause menu)."""
        manager = SystemManager()

        system = MockSystem()
        manager.register(system)

        # Normal updates
        manager.update(0.016)
        assert system.update_count == 1

        # Pause
        manager.set_enabled(False)
        manager.update(0.016)
        manager.update(0.016)
        assert system.update_count == 1  # No additional updates

        # Resume
        manager.set_enabled(True)
        manager.update(0.016)
        assert system.update_count == 2


class TestLateRegistration:
    """A system registered after initialize() was never initialised.

    Scene.resolve_dependencies() calls initialize() on the scene's manager,
    and that runs *before* on_enter() -- which is exactly where a game is
    meant to register its own systems. Every one of them started up
    uninitialised.
    """

    def test_a_system_registered_after_initialize_is_initialised(self):
        manager = SystemManager()
        manager.register(MockInitializableSystem())
        manager.initialize()

        late = MockInitializableSystem()
        manager.register(late, system_type=type("LateKey", (), {}))

        assert late.initialized

    def test_a_late_system_is_not_initialised_twice(self):
        class CountingInit:
            def __init__(self):
                self.init_count = 0

            def initialize(self):
                self.init_count += 1

            def update(self, dt):
                pass

        manager = SystemManager()
        manager.initialize()
        system = CountingInit()
        manager.register(system)
        manager.initialize()

        assert system.init_count == 1

    def test_registering_before_initialize_still_defers(self):
        manager = SystemManager()
        system = MockInitializableSystem()
        manager.register(system)

        assert not system.initialized
        manager.initialize()
        assert system.initialized

    def test_a_late_system_without_initialize_is_fine(self):
        manager = SystemManager()
        manager.initialize()
        manager.register(MockSystem())

        assert manager.system_count == 1


class TestDuplicateRegistrationKeys:
    """Several systems may share a key, but only one is addressable.

    The lookup table holds one entry per key while the update list holds them
    all, so the earlier systems keep updating with no way to reach them by
    type. That is allowed -- the update list is the source of truth -- but it
    is now said out loud instead of being silent.
    """

    def test_both_systems_still_update(self):
        manager = SystemManager()
        first, second = MockSystem(), MockSystem()
        manager.register(first)
        manager.register(second)

        manager.update(0.016)

        assert first.update_count == 1
        assert second.update_count == 1

    def test_the_ambiguity_is_logged(self, caplog):
        import logging

        manager = SystemManager()
        manager.register(MockSystem())

        with caplog.at_level(logging.WARNING):
            manager.register(MockSystem())

        assert "get_system() and unregister() will only see the newest" in caplog.text

    def test_re_registering_the_same_object_is_not_flagged(self, caplog):
        import logging

        manager = SystemManager()
        system = MockSystem()
        manager.register(system)

        with caplog.at_level(logging.WARNING):
            manager.register(system)

        assert caplog.text == ""

    def test_distinct_keys_keep_both_addressable(self):
        class KeyA:
            pass

        class KeyB:
            pass

        manager = SystemManager()
        first, second = MockSystem(), MockSystem()
        manager.register(first, system_type=KeyA)
        manager.register(second, system_type=KeyB)

        assert manager.get_system(KeyA) is first
        assert manager.get_system(KeyB) is second


class TestUnregisterEdgeCases:
    def test_a_falsy_system_is_fully_removed(self):
        """`if system:` dropped a falsy system from the lookup table but left
        it in the update list -- still ticking every frame, never cleaned up,
        and reported as removed."""

        class FalsySystem:
            def __init__(self):
                self.cleaned = False
                self.ticked = False

            def __len__(self):
                return 0

            def update(self, dt):
                self.ticked = True

            def cleanup(self):
                self.cleaned = True

        manager = SystemManager()
        system = FalsySystem()
        manager.register(system)

        returned = manager.unregister(FalsySystem)
        manager.update(0.016)

        assert returned is system
        assert manager.system_count == 0
        assert system.cleaned
        assert not system.ticked

    def test_unregistering_an_unknown_type_returns_none(self):
        manager = SystemManager()

        assert manager.unregister(MockSystem) is None

    def test_unregister_removes_only_the_named_system(self):
        class KeyA:
            pass

        class KeyB:
            pass

        manager = SystemManager()
        keep = MockSystem()
        manager.register(MockSystem(), system_type=KeyA)
        manager.register(keep, system_type=KeyB)

        manager.unregister(KeyA)
        manager.update(0.016)

        assert manager.system_count == 1
        assert keep.update_count == 1


class TestManagerReuse:
    def test_a_manager_can_be_rebuilt_after_cleanup(self):
        manager = SystemManager()
        manager.register(MockInitializableSystem())
        manager.initialize()
        manager.cleanup()

        rebuilt = MockInitializableSystem()
        manager.register(rebuilt)
        manager.initialize()

        assert rebuilt.initialized
        assert manager.system_count == 1

    def test_priority_order_is_ascending(self):
        """Ascending, unlike EventDispatcher where higher priority runs
        first. Systems are a pipeline; event handlers compete."""
        order: list[str] = []

        class Ordered:
            def __init__(self, name):
                self.name = name

            def update(self, dt):
                order.append(self.name)

        manager = SystemManager()
        manager.register(Ordered("late"), priority=300, system_type=type("L", (), {}))
        manager.register(Ordered("early"), priority=100, system_type=type("E", (), {}))
        manager.update(0.016)

        assert order == ["early", "late"]
