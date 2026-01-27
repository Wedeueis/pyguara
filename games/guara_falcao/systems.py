"""Guará & Falcão - Game Systems.

Logic processors for the platformer game.
"""

from typing import Optional

from pyguara.ecs.manager import EntityManager
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.common.types import Vector2, Rect
from pyguara.common.components import Transform
from pyguara.physics.platformer_controller import PlatformerController, PlatformerState
from pyguara.graphics.components.camera import Camera2D, CameraFollowConstraints

from games.guara_falcao.components import (
    PlayerState,
    PlayerAnimState,
    Health,
    CameraTarget,
    Collectible,
    ZoneTrigger,
    Score,
    Hazard,
)
from games.guara_falcao.events import (
    PlayerLandedEvent,
    PlayerJumpedEvent,
    PlayerDamagedEvent,
    PlayerDeathEvent,
    CollectiblePickedEvent,
    CheckpointReachedEvent,
)


class PlayerControlSystem:
    """Processes player input and updates PlatformerController."""

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._player: Optional[Entity] = None

        # Track previous grounded state for landing events
        self._was_grounded = False

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def update(self, dt: float, move_input: float, jump_pressed: bool) -> None:
        """Update player based on input.

        Args:
            dt: Delta time
            move_input: Horizontal input (-1 to 1)
            jump_pressed: Whether jump was pressed this frame
        """
        if not self._player:
            return

        controller = self._player.get_component(PlatformerController)
        if not controller:
            return

        # Apply horizontal movement
        if move_input < 0:
            controller.move_left()
        elif move_input > 0:
            controller.move_right()
        else:
            controller.stop_move()

        # Handle jump
        if jump_pressed:
            was_wall_sliding = controller.is_wall_sliding()
            controller.jump()

            # Fire jump event
            if controller._jump_requested:
                self._dispatcher.dispatch(
                    PlayerJumpedEvent(is_wall_jump=was_wall_sliding)
                )

        # Check for landing
        if controller.is_grounded and not self._was_grounded:
            transform = self._player.get_component(Transform)
            if transform:
                self._dispatcher.dispatch(
                    PlayerLandedEvent(position=transform.position)
                )

        self._was_grounded = controller.is_grounded


class AnimationFSMSystem:
    """Updates player animation state based on movement."""

    FALL_VELOCITY_THRESHOLD = 50.0  # Y velocity to trigger fall state
    LAND_DURATION = 0.1  # Duration of land animation

    def __init__(self, entity_manager: EntityManager):
        """Initialize the system."""
        self._em = entity_manager

    def update(self, dt: float) -> None:
        """Update animation states for all entities with PlayerState."""
        for entity in self._em.get_entities_with(PlayerState, PlatformerController):
            state = entity.get_component(PlayerState)
            controller = entity.get_component(PlatformerController)

            state.state_time += dt

            # Update facing direction
            state.facing_right = controller.facing_right

            # Determine animation state based on platformer state
            new_state = self._determine_state(state, controller)
            state.set_state(new_state)

    def _determine_state(
        self, state: PlayerState, controller: PlatformerController
    ) -> PlayerAnimState:
        """Determine the appropriate animation state."""
        # Handle landing animation
        if (
            state.current_state == PlayerAnimState.LAND
            and state.state_time < self.LAND_DURATION
        ):
            return PlayerAnimState.LAND

        # Wall sliding
        if controller.current_state == PlatformerState.WALL_SLIDE:
            return PlayerAnimState.WALL_SLIDE

        # Grounded states
        if controller.is_grounded:
            # Check if we just landed
            if state.current_state in (PlayerAnimState.FALL, PlayerAnimState.JUMP):
                return PlayerAnimState.LAND

            # Moving or idle
            if abs(controller.move_input) > 0.1:
                return PlayerAnimState.RUN
            return PlayerAnimState.IDLE

        # Airborne states
        # Simple heuristic: check if we're going up or down
        # In a real game, we'd check the rigidbody velocity
        if state.current_state == PlayerAnimState.JUMP:
            # Stay in jump until we start falling
            return PlayerAnimState.JUMP

        return PlayerAnimState.FALL


class CameraFollowSystem:
    """Updates camera to follow the player with deadzone and look-ahead."""

    def __init__(self, entity_manager: EntityManager):
        """Initialize the system."""
        self._em = entity_manager
        self._camera: Optional[Camera2D] = None
        self._target: Optional[Entity] = None

    def set_camera(self, camera: Camera2D) -> None:
        """Set the camera instance."""
        self._camera = camera

    def set_target(self, target: Entity) -> None:
        """Set the target entity to follow."""
        self._target = target

    def update(self, dt: float) -> None:
        """Update camera position."""
        if not self._camera or not self._target:
            return

        transform = self._target.get_component(Transform)
        camera_target = self._target.get_component(CameraTarget)
        controller = self._target.get_component(PlatformerController)

        if not transform:
            return

        # Calculate target position with look-ahead
        target_pos = Vector2(transform.position.x, transform.position.y)

        if camera_target:
            # Add vertical offset
            target_pos = Vector2(
                target_pos.x, target_pos.y + camera_target.vertical_offset
            )

            # Add look-ahead based on movement direction
            if controller:
                look_dir = 1.0 if controller.facing_right else -1.0
                target_pos = Vector2(
                    target_pos.x + camera_target.look_ahead * look_dir, target_pos.y
                )

        # Configure follow constraints
        constraints = CameraFollowConstraints(
            deadzone=Rect(-50, -30, 100, 60),  # Platformer-style deadzone
            max_speed=500.0,
            smooth_time=0.15,
        )

        # Use camera's built-in follow
        self._camera.follow(target_pos, constraints)
        self._camera.update(dt)


class CollectibleSystem:
    """Handles collectible pickup and scoring."""

    COLLECT_DISTANCE = 30.0  # Distance to collect items

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._player: Optional[Entity] = None

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def update(self, dt: float) -> None:
        """Check for collectible pickups."""
        if not self._player:
            return

        player_transform = self._player.get_component(Transform)
        score = self._player.get_component(Score)

        if not player_transform:
            return

        # Check all collectibles
        to_collect = []
        for entity in self._em.get_entities_with(Collectible, Transform):
            collectible = entity.get_component(Collectible)
            if collectible.collected:
                continue

            transform = entity.get_component(Transform)
            distance = player_transform.position.distance_to(transform.position)

            if distance < self.COLLECT_DISTANCE:
                to_collect.append((entity, collectible))

        # Process collections
        for entity, collectible in to_collect:
            collectible.collected = True

            if score:
                if collectible.collect_type == "coin":
                    score.add_coins(collectible.value)
                elif collectible.collect_type == "health":
                    health = self._player.get_component(Health)
                    if health:
                        health.heal(collectible.value)

            self._dispatcher.dispatch(
                CollectiblePickedEvent(
                    collect_type=collectible.collect_type, value=collectible.value
                )
            )


class CheckpointSystem:
    """Handles checkpoint zone triggers."""

    TRIGGER_DISTANCE = 40.0

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._player: Optional[Entity] = None
        self._current_spawn: Vector2 = Vector2(100, 300)

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def set_initial_spawn(self, spawn_point: Vector2) -> None:
        """Set the initial spawn point."""
        self._current_spawn = spawn_point

    def get_spawn_point(self) -> Vector2:
        """Get the current spawn point."""
        return self._current_spawn

    def update(self, dt: float) -> None:
        """Check for checkpoint triggers."""
        if not self._player:
            return

        player_transform = self._player.get_component(Transform)
        if not player_transform:
            return

        for entity in self._em.get_entities_with(ZoneTrigger, Transform):
            trigger = entity.get_component(ZoneTrigger)
            if trigger.triggered:
                continue

            transform = entity.get_component(Transform)
            distance = player_transform.position.distance_to(transform.position)

            if distance < self.TRIGGER_DISTANCE:
                trigger.triggered = True
                self._current_spawn = trigger.spawn_point

                self._dispatcher.dispatch(
                    CheckpointReachedEvent(
                        zone_name=trigger.zone_name, spawn_point=trigger.spawn_point
                    )
                )


class HealthSystem:
    """Manages player health and death."""

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher

    def update(self, dt: float) -> None:
        """Update health timers."""
        for entity in self._em.get_entities_with(Health):
            health = entity.get_component(Health)
            if health.invincible_time > 0:
                health.invincible_time -= dt

    def damage_player(self, player: Entity, damage: int = 1) -> None:
        """Apply damage to player."""
        health = player.get_component(Health)
        if not health:
            return

        alive = health.take_damage(damage)

        self._dispatcher.dispatch(
            PlayerDamagedEvent(damage=damage, remaining_health=health.current)
        )

        if not alive:
            self._dispatcher.dispatch(PlayerDeathEvent())


class HazardSystem:
    """Handles hazard collision detection and damage."""

    HAZARD_DISTANCE = 20.0  # Distance to trigger hazard damage

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._player: Optional[Entity] = None

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def update(self, dt: float) -> None:
        """Check for hazard collisions."""
        if not self._player:
            return

        player_transform = self._player.get_component(Transform)
        player_health = self._player.get_component(Health)

        if not player_transform or not player_health:
            return

        # Skip if player is invincible
        if player_health.invincible_time > 0:
            return

        # Check all hazards
        for entity in self._em.get_entities_with(Hazard, Transform):
            hazard = entity.get_component(Hazard)
            transform = entity.get_component(Transform)

            distance = player_transform.position.distance_to(transform.position)

            if distance < self.HAZARD_DISTANCE:
                # Apply damage
                alive = player_health.take_damage(hazard.damage)

                self._dispatcher.dispatch(
                    PlayerDamagedEvent(
                        damage=hazard.damage, remaining_health=player_health.current
                    )
                )

                if not alive:
                    self._dispatcher.dispatch(PlayerDeathEvent())
                break  # Only one hazard can damage per frame
