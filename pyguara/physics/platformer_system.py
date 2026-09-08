"""System for managing platformer controller physics and state.

The PlatformerSystem updates PlatformerController components each frame,
handling ground detection, movement, jumping, and wall mechanics.

Movement is driven by `CharacterMover`, not the Chipmunk solver: a character
has no `RigidBody`/shape registered with the physics engine at all, only a
`CharacterBody` (velocity, ground state, knockback) and a `Collider` used
purely as a source of dimensions. Gravity is integrated here manually, since
nothing else does it for an entity with no physics body.
"""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.physics.character_mover import CharacterMover
from pyguara.physics.components import CharacterBody, Collider
from pyguara.physics.platformer_controller import (
    PlatformerController,
    PlatformerInput,
    PlatformerState,
)
from pyguara.physics.protocols import IPhysicsEngine

# Default half-extents for a character with no Collider -- matches the
# fallback the old raycast-based system used.
_DEFAULT_HALF_EXTENTS = Vector2(12.0, 20.0)

# Per-tick multiplier applied to a knockback's residual velocity while
# `CharacterBody.external_velocity_timer` is running. ~0.9 at 60Hz decays to
# under 0.2% of the original push within a second, which is fast enough to
# read as a hit rather than a launch, without a visible snap to zero.
EXTERNAL_VELOCITY_DECAY = 0.9


def apply_knockback(body: CharacterBody, velocity: Vector2, duration: float) -> None:
    """Override a character's velocity with a knockback for `duration` seconds.

    Consumed the way the doc that reasoned about this promised: as velocity,
    not an impulse. While the timer is running, `PlatformerSystem` ignores
    input-driven horizontal control and lets `velocity` decay back toward
    zero instead, with gravity still integrating into it underneath.

    Args:
        body: The character's CharacterBody.
        velocity: The knockback's initial velocity.
        duration: How long input control stays suppressed, in seconds.
    """
    body.velocity = velocity
    body.external_velocity = velocity
    body.external_velocity_timer = duration


class PlatformerSystem:
    """System that updates platformer controller movement and state.

    Ground/wall detection is by overlap probe, not raycast: a character has
    no shape of its own in the engine, so it can never detect itself, which
    is what let ground detection self-detect before this switch. Movement is
    swept by `CharacterMover`, so penetration cannot occur -- overlap is
    resolved before a step is committed, not after the fact.

    Attributes:
        _entity_manager: EntityManager for querying entities.
        _physics_engine: Physics engine for wall-probe overlap queries.
        _mover: CharacterMover doing the actual swept movement.
        _gravity: Manually integrated into each character's velocity, since
            an entity with no RigidBody gets none from the engine.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        physics_engine: IPhysicsEngine,
        gravity: Vector2 | None = None,
    ):
        """Initialize the platformer system.

        Args:
            entity_manager: EntityManager to access entities and components.
            physics_engine: Physics engine for wall-probe overlap queries.
            gravity: Downward acceleration integrated into each character's
                velocity every tick. Defaults to `(0, 900)`.
        """
        self._entity_manager = entity_manager
        self._physics_engine = physics_engine
        self._mover = CharacterMover(physics_engine)
        self._gravity = gravity if gravity is not None else Vector2(0, 900)

    def update(self, delta_time: float) -> None:
        """Update all platformer controllers.

        Args:
            delta_time: Time elapsed since last update (seconds).
        """
        for entity in self._entity_manager.get_entities_with(
            PlatformerController, CharacterBody, Transform
        ):
            controller = entity.get_component(PlatformerController)
            body = entity.get_component(CharacterBody)
            transform = entity.get_component(Transform)
            collider = (
                entity.get_component(Collider)
                if entity.has_component(Collider)
                else None
            )
            half_extents = (
                Vector2(collider.dimensions[0] / 2, collider.dimensions[1] / 2)
                if collider
                else _DEFAULT_HALF_EXTENTS
            )

            # Consume this tick's movement/jump intent
            if controller.pending_input.move < 0:
                controller.facing_right = False
            elif controller.pending_input.move > 0:
                controller.facing_right = True
            controller.move_input = controller.pending_input.move
            if controller.pending_input.jump:
                controller._jump_requested = True
                controller.jump_buffer_timer = controller.jump_buffer

            # Ground/wall detection, from where the character ended up last
            # tick -- movement itself happens at the end of this one.
            self._update_ground_detection(
                controller, body, transform, half_extents, entity.id
            )
            self._update_wall_detection(controller, transform, half_extents, entity.id)

            self._update_timers(controller, delta_time)
            self._update_state(controller)

            self._integrate_gravity(body, delta_time)
            self._tick_knockback(body, delta_time)
            self._apply_movement(controller, body)
            self._handle_jump(controller, body)

            self._move(body, transform, half_extents, delta_time, entity.id)

            # Reset intent for next frame
            controller.pending_input = PlatformerInput()

    def reset_jump_state(self, controller: PlatformerController) -> None:
        """Reset a controller's jump-related state.

        Call this when a character lands or respawns.

        Args:
            controller: PlatformerController component.
        """
        controller._jump_requested = False
        controller.jump_buffer_timer = 0.0
        controller.coyote_timer = 0.0
        controller._can_double_jump = False
        controller._jump_used = False

    def _update_ground_detection(
        self,
        controller: PlatformerController,
        body: CharacterBody,
        transform: Transform,
        half_extents: Vector2,
        entity_id: int | str,
    ) -> None:
        """Detect ground with a one-pixel overlap probe, not a raycast.

        Args:
            controller: PlatformerController component.
            body: CharacterBody, whose `grounded` mirrors the result.
            transform: Transform component.
            half_extents: The character's half width and half height.
            entity_id: The character, excluded from the probe. Harmless to
                pass even though the character has no shape to exclude --
                it just never matches.
        """
        hit = self._mover.probe(
            transform.position, half_extents, Vector2(0, 1), entity_id
        )

        was_grounded = controller.is_grounded
        body.grounded = hit is not None
        controller.is_grounded = body.grounded

        # Reset coyote time when landing
        if controller.is_grounded and not was_grounded:
            controller.coyote_timer = 0.0
            self.reset_jump_state(controller)

        # Start coyote time when leaving ground
        if not controller.is_grounded and was_grounded:
            controller.coyote_timer = controller.coyote_time

    def _update_wall_detection(
        self,
        controller: PlatformerController,
        transform: Transform,
        half_extents: Vector2,
        entity_id: int | str,
    ) -> None:
        """Detect walls with a small overlap query at upper-body height.

        Args:
            controller: PlatformerController component.
            transform: Transform component.
            half_extents: The character's half width and half height.
            entity_id: The character, excluded so it cannot detect itself.
        """
        # A thin box at upper-body height, not the character's full height,
        # so a floor tile stepping up beside the character doesn't itself
        # read as a wall.
        ray_y_offset = -10  # Cast from upper body, not centre
        probe_half = Vector2(controller.wall_check_distance / 2, 10.0)

        left_centre = transform.position + Vector2(
            -(half_extents.x + probe_half.x), ray_y_offset
        )
        right_centre = transform.position + Vector2(
            half_extents.x + probe_half.x, ray_y_offset
        )

        controller.on_wall_left = (
            self._physics_engine.overlap_box(left_centre, probe_half, entity_id)
            is not None
        )
        controller.on_wall_right = (
            self._physics_engine.overlap_box(right_centre, probe_half, entity_id)
            is not None
        )

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

    def _integrate_gravity(self, body: CharacterBody, delta_time: float) -> None:
        """Add gravity to vertical velocity.

        Nothing else does this for a character: it has no RigidBody for the
        physics engine to simulate, so unlike a dynamic body, its own
        velocity is the only place gravity can accumulate.

        Args:
            body: CharacterBody being integrated.
            delta_time: Time elapsed since last update.
        """
        body.velocity = Vector2(
            body.velocity.x, body.velocity.y + self._gravity.y * delta_time
        )

    def _tick_knockback(self, body: CharacterBody, delta_time: float) -> None:
        """Count down and decay an active knockback.

        Args:
            body: CharacterBody possibly mid-knockback.
            delta_time: Time elapsed since last update.
        """
        if body.external_velocity_timer <= 0.0:
            return

        body.external_velocity_timer = max(
            0.0, body.external_velocity_timer - delta_time
        )
        body.external_velocity = Vector2(
            body.external_velocity.x * EXTERNAL_VELOCITY_DECAY,
            body.external_velocity.y * EXTERNAL_VELOCITY_DECAY,
        )

    def _apply_movement(
        self, controller: PlatformerController, body: CharacterBody
    ) -> None:
        """Apply horizontal movement to the character's velocity.

        Args:
            controller: PlatformerController component.
            body: CharacterBody component.
        """
        current_velocity = body.velocity

        if body.external_velocity_timer > 0.0:
            # Knockback in progress: input control is suppressed. Gravity,
            # already integrated into current_velocity.y above, keeps
            # acting underneath it.
            body.velocity = Vector2(body.external_velocity.x, current_velocity.y)
            return

        # Calculate target horizontal velocity
        target_velocity_x = controller.move_input * controller.move_speed

        # Apply air control multiplier if airborne
        if controller.current_state != PlatformerState.GROUNDED:
            target_velocity_x *= controller.air_control

        # Instant stop when no input (prevents sliding and diagonal jumps)
        if controller.move_input == 0:
            new_velocity_x = 0.0
        else:
            # Don't push into walls when airborne -- on the ground, the
            # mover stops horizontal motion at the wall by construction.
            if not controller.is_grounded:
                if (
                    controller.on_wall_left
                    and controller.move_input < 0
                    or controller.on_wall_right
                    and controller.move_input > 0
                ):
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

        body.velocity = Vector2(new_velocity_x, new_velocity_y)

    def _handle_jump(
        self, controller: PlatformerController, body: CharacterBody
    ) -> None:
        """Handle jump logic with coyote time and jump buffering.

        Args:
            controller: PlatformerController component.
            body: CharacterBody component.
        """
        # Check if jump was requested (either this frame or buffered)
        if not controller._jump_requested and controller.jump_buffer_timer <= 0:
            return

        # Wall jump takes priority
        if controller.can_wall_jump():
            self._perform_wall_jump(controller, body)
            return

        # Regular jump
        if controller.can_jump():
            self._perform_jump(controller, body)
            return

        # Clear jump request if couldn't jump
        controller._jump_requested = False

    def _perform_jump(
        self, controller: PlatformerController, body: CharacterBody
    ) -> None:
        """Execute a regular jump.

        Args:
            controller: PlatformerController component.
            body: CharacterBody component.
        """
        # Set upward velocity
        # If no horizontal input, don't preserve horizontal velocity (prevents diagonal jumps)
        if controller.move_input == 0:
            body.velocity = Vector2(0, -controller.jump_force)
        else:
            body.velocity = Vector2(body.velocity.x, -controller.jump_force)

        # Consume jump - mark as used to prevent air jumps
        controller._jump_requested = False
        controller._jump_used = True  # Can't jump again until landing
        controller.jump_buffer_timer = 0.0
        controller.coyote_timer = 0.0

    def _perform_wall_jump(
        self, controller: PlatformerController, body: CharacterBody
    ) -> None:
        """Execute a wall jump.

        Args:
            controller: PlatformerController component.
            body: CharacterBody component.
        """
        # Determine jump direction (away from wall)
        if controller.on_wall_left:
            jump_x = controller.wall_jump_force_x  # Jump right
        else:
            jump_x = -controller.wall_jump_force_x  # Jump left

        # Apply wall jump velocity
        body.velocity = Vector2(jump_x, -controller.wall_jump_force_y)

        # Consume jump
        controller._jump_requested = False
        controller.jump_buffer_timer = 0.0
        controller.coyote_timer = 0.0

    def _move(
        self,
        body: CharacterBody,
        transform: Transform,
        half_extents: Vector2,
        delta_time: float,
        entity_id: int | str,
    ) -> None:
        """Sweep the character by this tick's velocity and write back the result.

        Args:
            body: CharacterBody providing velocity and the remainder
                accumulator, and receiving the updated remainder.
            transform: Transform providing and receiving position.
            half_extents: The character's half width and half height.
            delta_time: Time elapsed since last update.
            entity_id: The character, excluded from overlap tests.
        """
        result = self._mover.move(
            transform.position,
            half_extents,
            body.velocity * delta_time,
            body._remainder,
            entity_id,
        )
        transform.position = result.position
        body._remainder = result.remainder
