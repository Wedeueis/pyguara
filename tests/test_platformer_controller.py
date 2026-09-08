"""Tests for platformer controller system."""

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import CharacterBody, Collider
from pyguara.physics.platformer_controller import (
    PlatformerController,
    PlatformerInput,
    PlatformerState,
)
from pyguara.physics.platformer_system import PlatformerSystem
from pyguara.physics.types import ShapeType


class TestPlatformerControllerComponent:
    """Test PlatformerController component."""

    def test_controller_creation(self):
        """PlatformerController should be created with default values."""
        controller = PlatformerController()

        assert controller.move_speed == 200.0
        assert controller.jump_force == 400.0
        assert controller.coyote_time == 0.15
        assert controller.jump_buffer == 0.1
        assert controller.wall_slide_enabled is True
        assert controller.wall_jump_enabled is True

    def test_controller_custom_values(self):
        """PlatformerController can be created with custom parameters."""
        controller = PlatformerController(
            move_speed=150.0,
            jump_force=500.0,
            coyote_time=0.2,
            wall_slide_enabled=False,
        )

        assert controller.move_speed == 150.0
        assert controller.jump_force == 500.0
        assert controller.coyote_time == 0.2
        assert controller.wall_slide_enabled is False

    def test_pending_input_default(self):
        """A freshly created controller has no pending input."""
        controller = PlatformerController()

        assert controller.pending_input == PlatformerInput()
        assert controller.pending_input.move == 0.0
        assert controller.pending_input.jump is False

    def test_pending_input_can_be_set(self):
        """Callers submit a tick's intent by assigning pending_input directly."""
        controller = PlatformerController()

        controller.pending_input = PlatformerInput(move=-1.0, jump=True)

        assert controller.pending_input.move == -1.0
        assert controller.pending_input.jump is True

    def test_can_jump_when_grounded(self):
        """can_jump should return True when grounded."""
        controller = PlatformerController()
        controller.is_grounded = True

        assert controller.can_jump() is True

    def test_can_jump_in_coyote_time(self):
        """can_jump should return True during coyote time."""
        controller = PlatformerController()
        controller.is_grounded = False
        controller.coyote_timer = 0.1

        assert controller.can_jump() is True

    def test_cannot_jump_airborne(self):
        """can_jump should return False when airborne without coyote time."""
        controller = PlatformerController()
        controller.is_grounded = False
        controller.coyote_timer = 0.0

        assert controller.can_jump() is False

    def test_can_wall_jump_left(self):
        """can_wall_jump should return True when on left wall."""
        controller = PlatformerController()
        controller.on_wall_left = True

        assert controller.can_wall_jump() is True

    def test_can_wall_jump_right(self):
        """can_wall_jump should return True when on right wall."""
        controller = PlatformerController()
        controller.on_wall_right = True

        assert controller.can_wall_jump() is True

    def test_cannot_wall_jump_when_disabled(self):
        """can_wall_jump should return False when wall jumping is disabled."""
        controller = PlatformerController(wall_jump_enabled=False)
        controller.on_wall_left = True

        assert controller.can_wall_jump() is False

    def test_is_wall_sliding(self):
        """is_wall_sliding should check current state."""
        controller = PlatformerController()
        controller.current_state = PlatformerState.WALL_SLIDE

        assert controller.is_wall_sliding() is True

        controller.current_state = PlatformerState.GROUNDED
        assert controller.is_wall_sliding() is False


class TestPlatformerSystem:
    """Test PlatformerSystem integration."""

    def setup_method(self):
        """Set up test environment."""
        self.manager = EntityManager()
        self.physics_engine = PymunkEngine()
        self.physics_engine.initialize(Vector2(0, 980))  # Gravity
        self.platformer_system = PlatformerSystem(
            self.manager, self.physics_engine, gravity=Vector2(0, 980)
        )

    def test_system_creation(self):
        """PlatformerSystem should be created successfully."""
        assert self.platformer_system is not None

    def test_system_requires_all_components(self):
        """System should only process entities with all required components."""
        # Entity with only controller - should not crash
        entity1 = self.manager.create_entity()
        entity1.add_component(PlatformerController())

        # Should not raise
        self.platformer_system.update(1 / 60)

        # Entity with controller and body but no transform
        entity2 = self.manager.create_entity()
        entity2.add_component(PlatformerController())
        entity2.add_component(CharacterBody())

        # Should not raise
        self.platformer_system.update(1 / 60)

    def test_timer_updates(self):
        """System should update coyote and jump buffer timers."""
        entity = self.manager.create_entity()
        entity.add_component(Transform(position=Vector2(100, 100)))
        entity.add_component(CharacterBody())
        controller = PlatformerController()
        controller.coyote_timer = 0.15
        controller.jump_buffer_timer = 0.1
        entity.add_component(controller)

        # Update system
        dt = 1 / 60  # 60 FPS
        self.platformer_system.update(dt)

        # Check timers decreased
        controller = entity.get_component(PlatformerController)
        assert controller.coyote_timer < 0.15
        assert controller.jump_buffer_timer < 0.1

    def test_pending_input_reset(self):
        """System should reset pending_input after consuming it each update."""
        entity = self.manager.create_entity()
        entity.add_component(Transform(position=Vector2(100, 100)))
        entity.add_component(CharacterBody())
        controller = PlatformerController()
        controller.pending_input = PlatformerInput(move=1.0)
        entity.add_component(controller)

        # Update system
        self.platformer_system.update(1 / 60)

        # This tick's intent should be consumed (translated to move_input/
        # facing_right) and reset to a fresh, empty PlatformerInput
        controller = entity.get_component(PlatformerController)
        assert controller.move_input == 1.0
        assert controller.facing_right is True
        assert controller.pending_input == PlatformerInput()

    def test_reset_jump_state(self):
        """PlatformerSystem.reset_jump_state should clear jump-related state."""
        controller = PlatformerController()
        controller._jump_requested = True
        controller.jump_buffer_timer = 0.1
        controller.coyote_timer = 0.1

        self.platformer_system.reset_jump_state(controller)

        assert controller._jump_requested is False
        assert controller.jump_buffer_timer == 0.0
        assert controller.coyote_timer == 0.0

    def test_jump_intent_translates_to_buffer(self):
        """pending_input.jump should translate into a buffered jump request."""
        entity = self.manager.create_entity()
        entity.add_component(Transform(position=Vector2(100, 100)))
        entity.add_component(CharacterBody())
        controller = PlatformerController(jump_buffer=0.1)
        entity.add_component(controller)

        controller.pending_input = PlatformerInput(jump=True)
        self.platformer_system.update(1 / 60)

        controller = entity.get_component(PlatformerController)
        # Airborne with no ground/wall contact this tick: the jump is buffered,
        # not yet consumed, and has ticked down by one frame's worth of dt.
        assert 0.0 < controller.jump_buffer_timer < 0.1


class TestPlatformerStates:
    """Test state transitions."""

    def test_grounded_state(self):
        """Controller should be in GROUNDED state when on ground."""
        controller = PlatformerController()
        controller.is_grounded = True
        controller.current_state = PlatformerState.GROUNDED

        assert controller.current_state == PlatformerState.GROUNDED

    def test_airborne_state(self):
        """Controller should be in AIRBORNE state when in air."""
        controller = PlatformerController()
        controller.is_grounded = False
        controller.on_wall_left = False
        controller.on_wall_right = False
        controller.current_state = PlatformerState.AIRBORNE

        assert controller.current_state == PlatformerState.AIRBORNE

    def test_wall_slide_state(self):
        """Controller should be in WALL_SLIDE state when on wall."""
        controller = PlatformerController()
        controller.is_grounded = False
        controller.on_wall_left = True
        controller.current_state = PlatformerState.WALL_SLIDE

        assert controller.current_state == PlatformerState.WALL_SLIDE


class TestCoyoteTime:
    """Test coyote time mechanics."""

    def test_coyote_time_allows_jump(self):
        """Character can jump during coyote time after leaving ground."""
        controller = PlatformerController(coyote_time=0.15)
        controller.is_grounded = False
        controller.coyote_timer = 0.10  # Still in coyote time

        assert controller.can_jump() is True

    def test_coyote_time_expires(self):
        """Character cannot jump after coyote time expires."""
        controller = PlatformerController(coyote_time=0.15)
        controller.is_grounded = False
        controller.coyote_timer = 0.0  # Coyote time expired

        assert controller.can_jump() is False

    def test_coyote_timer_decreases(self):
        """Coyote timer should decrease over time."""
        # This is tested indirectly through the system test_timer_updates
        pass


class TestJumpBuffering:
    """Test jump buffering mechanics."""

    def test_jump_buffer_stores_input(self):
        """Jump input is captured as intent; buffering itself is
        PlatformerSystem's job (see test_jump_intent_translates_to_buffer)."""
        controller = PlatformerController(jump_buffer=0.1)
        controller.pending_input = PlatformerInput(jump=True)

        assert controller.pending_input.jump is True

    def test_buffered_jump_executes(self):
        """Buffered jump should execute when possible."""
        # This is tested through integration tests
        pass


class TestWallMechanics:
    """Test wall slide and wall jump mechanics."""

    def test_wall_slide_detection(self):
        """Controller should detect walls."""
        controller = PlatformerController()
        controller.on_wall_left = True

        assert controller.on_wall_left is True

    def test_wall_jump_from_left_wall(self):
        """Wall jump from left wall should jump right."""
        controller = PlatformerController()
        controller.on_wall_left = True

        assert controller.can_wall_jump() is True

    def test_wall_jump_from_right_wall(self):
        """Wall jump from right wall should jump left."""
        controller = PlatformerController()
        controller.on_wall_right = True

        assert controller.can_wall_jump() is True

    def test_wall_slide_disabled(self):
        """Wall mechanics can be disabled."""
        controller = PlatformerController(wall_slide_enabled=False)
        controller.on_wall_left = True

        assert controller.is_wall_sliding() is False


class TestPlatformerUsagePatterns:
    """Test practical platformer controller usage."""

    def test_basic_platformer_setup(self):
        """Basic platformer character setup."""
        manager = EntityManager()

        # Create player
        player = manager.create_entity()
        player.add_component(Transform(position=Vector2(400, 300)))
        player.add_component(CharacterBody())
        player.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[32, 64]))
        player.add_component(
            PlatformerController(
                move_speed=200.0, jump_force=400.0, coyote_time=0.15, jump_buffer=0.1
            )
        )

        # Verify all components present
        assert player.has_component(PlatformerController)
        assert player.has_component(CharacterBody)
        assert player.has_component(Transform)

    def test_input_handling_pattern(self):
        """Input handling for platformer movement flows through pending_input."""
        controller = PlatformerController()

        # Simulate left movement
        controller.pending_input = PlatformerInput(move=-1.0)
        assert controller.pending_input.move == -1.0

        # Simulate right movement
        controller.pending_input = PlatformerInput(move=1.0)
        assert controller.pending_input.move == 1.0

        # Simulate jump
        controller.pending_input = PlatformerInput(jump=True)
        assert controller.pending_input.jump is True

    def test_responsive_controls_pattern(self):
        """Coyote time makes controls responsive even without a system tick."""
        controller = PlatformerController(coyote_time=0.15, jump_buffer=0.1)

        # Player walks off ledge
        controller.is_grounded = False
        controller.coyote_timer = 0.10  # Still in grace period

        # Player can still jump
        assert controller.can_jump() is True

        # Player presses jump slightly early -- captured as intent, buffered
        # once PlatformerSystem.update() consumes it (see TestPlatformerSystem)
        controller.pending_input = PlatformerInput(jump=True)
        assert controller.pending_input.jump is True

    def test_wall_jump_pattern(self):
        """Wall jumping for advanced movement."""
        controller = PlatformerController(
            wall_slide_enabled=True, wall_jump_enabled=True
        )

        # Player touches wall while airborne
        controller.is_grounded = False
        controller.on_wall_left = True
        controller.current_state = PlatformerState.WALL_SLIDE

        # Player can wall jump
        assert controller.can_wall_jump() is True
        assert controller.is_wall_sliding() is True

    def test_disabled_advanced_mechanics(self):
        """Advanced mechanics can be disabled for simpler gameplay."""
        controller = PlatformerController(
            wall_slide_enabled=False,
            wall_jump_enabled=False,
            coyote_time=0.0,
            jump_buffer=0.0,
        )

        # No coyote time
        controller.is_grounded = False
        controller.coyote_timer = 0.0
        assert controller.can_jump() is False

        # No wall mechanics
        controller.on_wall_left = True
        assert controller.can_wall_jump() is False
        assert controller.is_wall_sliding() is False
