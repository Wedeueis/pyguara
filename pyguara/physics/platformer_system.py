"""System for managing platformer controller physics and state.

The PlatformerSystem updates PlatformerController components each frame,
handling ground detection, movement, jumping, and wall mechanics.
"""

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.physics.components import Collider, RigidBody
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
            collider = entity.get_component(Collider)

            # Get collider half-dimensions for raycast offsets
            half_height = collider.dimensions[1] / 2 if collider else 20.0
            half_width = collider.dimensions[0] / 2 if collider else 12.0

            # Perform ground and wall detection
            self._update_ground_detection(controller, transform, half_height)
            self._update_wall_detection(controller, transform, half_width)

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
        self, controller: PlatformerController, transform: Transform, half_height: float
    ) -> None:
        """Detect if character is on ground using raycast.

        Args:
            controller: PlatformerController component.
            transform: Transform component.
            half_height: Half the collider height (to start ray from feet).
        """
        # Cast ray downward from just below character's feet
        # Start slightly below the collider to avoid self-intersection
        start = transform.position + Vector2(0, half_height + 1)
        end = start + Vector2(0, controller.ground_check_distance)

        hit = self._physics_engine.raycast(start, end)

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
        self, controller: PlatformerController, transform: Transform, half_width: float
    ) -> None:
        """Detect if character is touching walls using raycasts.

        Args:
            controller: PlatformerController component.
            transform: Transform component.
            half_width: Half the collider width (to start ray from sides).
        """
        # Always detect walls (needed to prevent pushing into them)
        # Wall sliding/jumping is a separate feature that uses this data

        # Cast rays from just outside character's sides at upper body height
        # to avoid detecting ground tiles. Use a point above the feet.
        ray_y_offset = -10  # Cast from upper body, not center

        # Start further outside the collider to avoid self-intersection
        left_start = transform.position + Vector2(-half_width - 2, ray_y_offset)
        right_start = transform.position + Vector2(half_width + 2, ray_y_offset)

        left_end = left_start + Vector2(-controller.wall_check_distance, 0)
        right_end = right_start + Vector2(controller.wall_check_distance, 0)

        left_hit = self._physics_engine.raycast(left_start, left_end)
        right_hit = self._physics_engine.raycast(right_start, right_end)

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

        # Instant stop when no input (prevents sliding and diagonal jumps)
        if controller.move_input == 0:
            new_velocity_x = 0.0
        else:
            # Don't push into walls when airborne - this prevents fighting the physics engine
            # On ground, physics collision handles this naturally
            if not controller.is_grounded:
                if controller.on_wall_left and controller.move_input < 0:
                    new_velocity_x = 0.0
                elif controller.on_wall_right and controller.move_input > 0:
                    new_velocity_x = 0.0
                else:
                    new_velocity_x = (
                        current_velocity.x
                        + (target_velocity_x - current_velocity.x)
                        * controller.acceleration
                    )
            else:
                # On ground, smoothly interpolate to target velocity
                new_velocity_x = (
                    current_velocity.x
                    + (target_velocity_x - current_velocity.x) * controller.acceleration
                )

        # Apply wall slide friction or normal fall speed clamping
        # In screen coords: positive Y is down, so falling = positive velocity.y
        if controller.current_state == PlatformerState.WALL_SLIDE:
            # Limit falling speed when wall sliding
            new_velocity_y = min(current_velocity.y, controller.wall_slide_speed)
        else:
            # Clamp falling speed to max (don't exceed terminal velocity)
            new_velocity_y = min(current_velocity.y, controller.max_fall_speed)

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
        # If no horizontal input, don't preserve horizontal velocity (prevents diagonal jumps)
        if controller.move_input == 0:
            rigidbody.handle.velocity = Vector2(0, -controller.jump_force)
        else:
            current_velocity = rigidbody.handle.velocity
            rigidbody.handle.velocity = Vector2(
                current_velocity.x, -controller.jump_force
            )

        # Consume jump - mark as used to prevent air jumps
        controller._jump_requested = False
        controller._jump_used = True  # Can't jump again until landing
        controller.jump_buffer_timer = 0.0
        controller.coyote_timer = 0.0

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
