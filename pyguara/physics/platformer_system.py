"""System for managing platformer controller physics and state.

The PlatformerSystem updates PlatformerController components each frame,
handling ground detection, movement, jumping, and wall mechanics.
"""

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.physics.components import RigidBody
from pyguara.physics.platformer_controller import PlatformerController, PlatformerState
from pyguara.physics.protocols import IPhysicsEngine


class PlatformerSystem:
    """System that updates platformer controller movement and state.

    The PlatformerSystem performs raycasts for ground/wall detection,
    updates movement velocities, handles jump logic with coyote time
    and jump buffering, and manages wall slide/jump mechanics.

    Attributes:
        _entity_manager: EntityManager for querying entities.
        _physics_engine: Physics engine for raycasting.
    """

    def __init__(self, entity_manager: EntityManager, physics_engine: IPhysicsEngine):
        """Initialize the platformer system.

        Args:
            entity_manager: EntityManager to access entities and components.
            physics_engine: Physics engine for raycasting.
        """
        self._entity_manager = entity_manager
        self._physics_engine = physics_engine

    def update(self, delta_time: float) -> None:
        """Update all platformer controllers.

        Args:
            delta_time: Time elapsed since last update (seconds).
        """
        # Query all entities with platformer controller
        for entity in self._entity_manager.get_entities_with(
            PlatformerController, RigidBody, Transform
        ):
            controller = entity.get_component(PlatformerController)
            rigidbody = entity.get_component(RigidBody)
            transform = entity.get_component(Transform)

            # Perform ground and wall detection (pass entity ID to filter self-hits)
            self._update_ground_detection(controller, transform, entity.id)
            self._update_wall_detection(controller, transform, entity.id)

            # Update timers
            self._update_timers(controller, delta_time)

            # Update state machine
            self._update_state(controller)

            # Apply movement
            self._apply_movement(controller, rigidbody)

            # Handle jumping
            self._handle_jump(controller, rigidbody)

            # Reset input for next frame
            controller.move_input = 0.0

    def _update_ground_detection(
        self, controller: PlatformerController, transform: Transform, entity_id: str
    ) -> None:
        """Detect if character is on ground using raycast.

        Args:
            controller: PlatformerController component.
            transform: Transform component.
            entity_id: ID of the entity to exclude from raycast results.
        """
        # Cast ray downward from character center
        start = transform.position
        end = start + Vector2(0, controller.ground_check_distance)

        hit = self._physics_engine.raycast(start, end)

        # Filter out hits on the entity's own collider
        if hit is not None and hit.entity_id == entity_id:
            hit = None

        was_grounded = controller.is_grounded
        controller.is_grounded = hit is not None

        # Reset coyote time when landing
        if controller.is_grounded and not was_grounded:
            controller.coyote_timer = 0.0
            controller.reset_jump_state()

        # Start coyote time when leaving ground
        if not controller.is_grounded and was_grounded:
            controller.coyote_timer = controller.coyote_time

    def _update_wall_detection(
        self, controller: PlatformerController, transform: Transform, entity_id: str
    ) -> None:
        """Detect if character is touching walls using raycasts.

        Args:
            controller: PlatformerController component.
            transform: Transform component.
            entity_id: ID of the entity to exclude from raycast results.
        """
        if not controller.wall_slide_enabled:
            controller.on_wall_left = False
            controller.on_wall_right = False
            return

        # Cast rays to left and right
        start = transform.position
        left_end = start + Vector2(-controller.wall_check_distance, 0)
        right_end = start + Vector2(controller.wall_check_distance, 0)

        left_hit = self._physics_engine.raycast(start, left_end)
        right_hit = self._physics_engine.raycast(start, right_end)

        # Filter out hits on the entity's own collider
        if left_hit is not None and left_hit.entity_id == entity_id:
            left_hit = None
        if right_hit is not None and right_hit.entity_id == entity_id:
            right_hit = None

        controller.on_wall_left = left_hit is not None
        controller.on_wall_right = right_hit is not None

    def _update_timers(
        self, controller: PlatformerController, delta_time: float
    ) -> None:
        """Update coyote time and jump buffer timers.

        Args:
            controller: PlatformerController component.
            delta_time: Time elapsed since last update.
        """
        # Update coyote timer
        if controller.coyote_timer > 0:
            controller.coyote_timer -= delta_time
            if controller.coyote_timer < 0:
                controller.coyote_timer = 0.0

        # Update jump buffer timer
        if controller.jump_buffer_timer > 0:
            controller.jump_buffer_timer -= delta_time
            if controller.jump_buffer_timer < 0:
                controller.jump_buffer_timer = 0.0

    def _update_state(self, controller: PlatformerController) -> None:
        """Update controller state machine.

        Args:
            controller: PlatformerController component.
        """
        if controller.is_grounded:
            controller.current_state = PlatformerState.GROUNDED
        elif (
            controller.wall_slide_enabled
            and not controller.is_grounded
            and (controller.on_wall_left or controller.on_wall_right)
        ):
            controller.current_state = PlatformerState.WALL_SLIDE
        else:
            controller.current_state = PlatformerState.AIRBORNE

    def _apply_movement(
        self, controller: PlatformerController, rigidbody: RigidBody
    ) -> None:
        """Apply horizontal movement to rigidbody.

        Args:
            controller: PlatformerController component.
            rigidbody: RigidBody component.
        """
        if not rigidbody.handle:
            return

        # Get current velocity
        current_velocity = rigidbody.handle.velocity

        # Calculate target horizontal velocity
        target_velocity_x = controller.move_input * controller.move_speed

        # Apply air control multiplier if airborne
        if controller.current_state != PlatformerState.GROUNDED:
            target_velocity_x *= controller.air_control

        # Smoothly interpolate to target velocity
        new_velocity_x = (
            current_velocity.x
            + (target_velocity_x - current_velocity.x) * controller.acceleration
        )

        # Apply wall slide friction
        if controller.current_state == PlatformerState.WALL_SLIDE:
            # Limit falling speed when wall sliding
            new_velocity_y = min(current_velocity.y, controller.wall_slide_speed)
            rigidbody.handle.velocity = Vector2(new_velocity_x, new_velocity_y)
        else:
            # Clamp falling speed to max
            new_velocity_y = max(current_velocity.y, -controller.max_fall_speed)
            rigidbody.handle.velocity = Vector2(new_velocity_x, new_velocity_y)

    def _handle_jump(
        self, controller: PlatformerController, rigidbody: RigidBody
    ) -> None:
        """Handle jump logic with coyote time and jump buffering.

        Args:
            controller: PlatformerController component.
            rigidbody: RigidBody component.
        """
        if not rigidbody.handle:
            return

        # Check if jump was requested (either this frame or buffered)
        if not controller._jump_requested and controller.jump_buffer_timer <= 0:
            return

        # Wall jump takes priority
        if controller.can_wall_jump():
            self._perform_wall_jump(controller, rigidbody)
            return

        # Regular jump
        if controller.can_jump():
            self._perform_jump(controller, rigidbody)
            return

        # Clear jump request if couldn't jump
        controller._jump_requested = False

    def _perform_jump(
        self, controller: PlatformerController, rigidbody: RigidBody
    ) -> None:
        """Execute a regular jump.

        Args:
            controller: PlatformerController component.
            rigidbody: RigidBody component.
        """
        if not rigidbody.handle:
            return

        # Set upward velocity
        current_velocity = rigidbody.handle.velocity
        rigidbody.handle.velocity = Vector2(current_velocity.x, -controller.jump_force)

        # Consume jump
        controller._jump_requested = False
        controller.jump_buffer_timer = 0.0
        controller.coyote_timer = 0.0  # Can't jump again until grounded

    def _perform_wall_jump(
        self, controller: PlatformerController, rigidbody: RigidBody
    ) -> None:
        """Execute a wall jump.

        Args:
            controller: PlatformerController component.
            rigidbody: RigidBody component.
        """
        if not rigidbody.handle:
            return

        # Determine jump direction (away from wall)
        if controller.on_wall_left:
            jump_x = controller.wall_jump_force_x  # Jump right
        else:
            jump_x = -controller.wall_jump_force_x  # Jump left

        # Apply wall jump velocity
        rigidbody.handle.velocity = Vector2(jump_x, -controller.wall_jump_force_y)

        # Consume jump
        controller._jump_requested = False
        controller.jump_buffer_timer = 0.0
        controller.coyote_timer = 0.0
