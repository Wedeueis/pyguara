"""Tests for system manager."""

import pytest

from pyguara.systems import Phase, SystemManager


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


class MockVariableSystem:
    """A system that wants both channels, and records each separately."""

    def __init__(self) -> None:
        """Start with both tallies empty."""
        self.fixed_dts: list[float] = []
        self.variable_dts: list[float] = []

    def update(self, dt: float) -> None:
        """The fixed step."""
        self.fixed_dts.append(dt)

    def variable_update(self, dt: float) -> None:
        """The rendered frame."""
        self.variable_dts.append(dt)


class TestTheVariableChannel:
    """`variable_update()`, the per-frame half of the pair.

    `SystemManager.update()` has always run on the fixed step -- measured,
    not assumed: `SceneManager.fixed_update()` is what calls it, and
    `SceneManager.update()` did not touch systems at all. So there was no
    way for a system to do per-frame work, which is what camera easing,
    tweens and particle drift need.

    These tests pin the part that matters most: adding that channel must
    not move anything that was already ticking.
    """

    def test_a_system_without_the_protocol_is_left_alone(self) -> None:
        """The whole compatibility story, in one assertion.

        Every system in the engine and every demo defines `update` and
        nothing else. If `variable_update()` reached them, they would all
        silently start ticking at framerate as well as on the fixed step --
        twice the work, and non-deterministic.
        """
        manager = SystemManager()
        plain = MockSystem()
        manager.register(plain)

        manager.variable_update(0.016)

        assert plain.update_count == 0, "a plain system must not tick per frame"

    def test_the_two_channels_are_independent(self) -> None:
        """One system, both methods, each driven only by its own caller."""
        manager = SystemManager()
        system = MockVariableSystem()
        manager.register(system)

        manager.update(1 / 60)
        manager.variable_update(0.016)
        manager.variable_update(0.021)

        assert system.fixed_dts == [1 / 60]
        assert system.variable_dts == [0.016, 0.021]

    def test_variable_updates_run_in_priority_order(self) -> None:
        """The same ordering guarantee `update()` gives.

        A camera that eases toward a target has to run after whatever moved
        the target, on this channel as much as on the other one.
        """
        manager = SystemManager()
        order: list[str] = []

        class Recorder:
            def __init__(self, name: str) -> None:
                self._name = name

            def update(self, dt: float) -> None:
                pass

            def variable_update(self, dt: float) -> None:
                order.append(self._name)

        manager.register(Recorder("late"), priority=300, system_type=type("L", (), {}))
        manager.register(Recorder("early"), priority=100, system_type=type("E", (), {}))

        manager.variable_update(0.016)

        assert order == ["early", "late"]

    def test_a_disabled_manager_runs_neither_channel(self) -> None:
        """`set_enabled(False)` is what scene pause uses; it has to cover both."""
        manager = SystemManager()
        system = MockVariableSystem()
        manager.register(system)
        manager.set_enabled(False)

        manager.update(1 / 60)
        manager.variable_update(0.016)

        assert system.fixed_dts == []
        assert system.variable_dts == []


class TestPerSystemEnabling:
    """Switching one system off without unregistering it."""

    def test_a_disabled_system_stops_ticking_on_both_channels(self) -> None:
        manager = SystemManager()
        system = MockVariableSystem()
        manager.register(system)

        assert manager.set_system_enabled(MockVariableSystem, False) is True
        manager.update(1 / 60)
        manager.variable_update(0.016)

        assert system.fixed_dts == []
        assert system.variable_dts == []

    def test_its_neighbours_keep_ticking(self) -> None:
        """The point of per-system control, as opposed to `set_enabled()`."""
        manager = SystemManager()
        off, on = MockSystem(), MockInitializableSystem()
        manager.register(off)
        manager.register(on)

        manager.set_system_enabled(MockSystem, False)
        manager.update(0.016)

        assert off.update_count == 0
        assert on.updated is True

    def test_re_enabling_resumes_it(self) -> None:
        manager = SystemManager()
        system = MockSystem()
        manager.register(system)

        manager.set_system_enabled(MockSystem, False)
        manager.update(0.016)
        manager.set_system_enabled(MockSystem, True)
        manager.update(0.016)

        assert system.update_count == 1

    def test_toggling_an_unregistered_key_reports_that_it_was_missing(self) -> None:
        """A silent no-op would hide a typo'd key or a system never added."""
        manager = SystemManager()

        assert manager.set_system_enabled(MockSystem, False) is False
        assert manager.is_system_enabled(MockSystem) is False

    def test_a_registered_system_reads_enabled_by_default(self) -> None:
        manager = SystemManager()
        manager.register(MockSystem())

        assert manager.is_system_enabled(MockSystem) is True

    def test_disabling_does_not_clean_up_or_unregister(self) -> None:
        """A pause, not a removal: state and registration both survive."""
        manager = SystemManager()
        system = MockCleanupSystem()
        manager.register(system)

        manager.set_system_enabled(MockCleanupSystem, False)

        assert system.cleaned_up is False
        assert manager.has_system(MockCleanupSystem) is True
        assert manager.system_count == 1

    def test_re_registering_the_same_system_comes_back_enabled(self) -> None:
        """The flag must not outlive the registration it was set on.

        Registering the *same object* again, deliberately: the flags are
        keyed by object identity, so this is the case where a stale one is
        guaranteed to still match rather than merely likely to. A scene
        that tears down and rebuilds while holding its system handles does
        exactly this, and would find the system silently mute.

        An earlier version of this test used a second, fresh `MockSystem`
        and relied on CPython reusing the dead object's id. It passed
        against a manager that never cleared the flag at all, because the
        id was not in fact reused -- a test that could only fail by luck.
        """
        manager = SystemManager()
        system = MockSystem()
        manager.register(system)
        manager.set_system_enabled(MockSystem, False)
        manager.unregister(MockSystem)

        manager.register(system)
        manager.update(0.016)

        assert system.update_count == 1, (
            "the disable flag survived the system's unregistration"
        )


class TestPhases:
    """`Phase`: the priority int with a name on it."""

    def test_a_phase_is_usable_wherever_a_priority_is(self) -> None:
        """The whole design, asserted.

        `Phase` is an `IntEnum` precisely so it needs no new parameter and
        no new code path -- a phase *is* a priority. If this ever needs a
        conversion, the abstraction has stopped paying for itself.
        """
        manager = SystemManager()
        order: list[str] = []

        class Recorder:
            def __init__(self, name: str) -> None:
                self._name = name

            def update(self, dt: float) -> None:
                order.append(self._name)

        manager.register(
            Recorder("physics"),
            priority=Phase.PHYSICS,
            system_type=type("P", (), {}),
        )
        manager.register(
            Recorder("input"), priority=Phase.INPUT, system_type=type("I", (), {})
        )
        manager.register(
            Recorder("logic"), priority=Phase.LOGIC, system_type=type("L", (), {})
        )

        manager.update(0.016)

        assert order == ["input", "logic", "physics"]

    def test_phases_are_ordered_the_way_a_frame_runs(self) -> None:
        """Ascending, so the enum reads top to bottom as the frame does."""
        values = [
            Phase.INPUT,
            Phase.AI,
            Phase.LOGIC,
            Phase.PHYSICS,
            Phase.POST,
            Phase.PRESENTATION,
        ]

        assert values == sorted(values)

    def test_arithmetic_on_a_phase_still_sorts_between_phases(self) -> None:
        """The "just after that one" case, which is most of the real uses.

        A game adding a `DeathSystem` after its `PoisonSystem` should not
        have to invent a number, nor be pushed into the next phase.
        """
        assert Phase.LOGIC < Phase.LOGIC + 10 < Phase.PHYSICS

    def test_the_engine_s_own_systems_land_where_the_names_claim(self) -> None:
        """`Scene.resolve_dependencies` registers four systems at fixed
        numbers that predate these names. The docstring on `phases.py`
        says the values were chosen to match those bands -- this is the
        assertion that keeps that claim true if either side moves.
        """
        steering, ai, audio_source, animation = 150, 200, 250, 300

        assert Phase.INPUT < steering < Phase.AI
        assert ai == Phase.AI
        assert Phase.AI < audio_source < Phase.LOGIC
        assert Phase.AI < animation < Phase.LOGIC
