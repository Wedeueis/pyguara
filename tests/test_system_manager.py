"""Tests for system manager."""

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

        try:
            manager.register(invalid_system)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "update" in str(e)

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
