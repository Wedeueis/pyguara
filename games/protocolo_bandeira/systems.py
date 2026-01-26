"""Protocolo Bandeira - Game Systems.

Logic processors for the shooter game.
"""

import math
from typing import Dict, Optional

from pyguara.ecs.manager import EntityManager
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.common.types import Vector2
from pyguara.common.components import Transform
from pyguara.ai.behavior_tree import BehaviorTree

from games.protocolo_bandeira.components import (
    Weapon,
    Bullet,
    EnemyAI,
    Health,
    Movement,
    Poolable,
    Score,
    EntityTeam,
    AIContext,
)
from games.protocolo_bandeira.events import (
    EnemyKilledEvent,
    PlayerDamagedEvent,
    PlayerDeathEvent,
    BulletFiredEvent,
)
from games.protocolo_bandeira.pooling import BulletPool, EnemyPool
from games.protocolo_bandeira.ai_behaviors import get_behavior_for_type


class PlayerControlSystem:
    """Processes player input for movement and shooting."""

    ARENA_PADDING = 30  # Keep player inside arena

    def __init__(self, entity_manager: EntityManager):
        """Initialize the system."""
        self._em = entity_manager
        self._player: Optional[Entity] = None

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def update(
        self, dt: float, move_dir: Vector2, aim_dir: Vector2, shoot: bool
    ) -> None:
        """Update player based on input.

        Args:
            dt: Delta time
            move_dir: Movement direction (normalized)
            aim_dir: Aim direction (normalized)
            shoot: Whether fire button is held
        """
        if not self._player:
            return

        transform = self._player.get_component(Transform)
        movement = self._player.get_component(Movement)
        weapon = self._player.get_component(Weapon)

        if not transform or not movement:
            return

        # Movement
        movement.velocity = move_dir * movement.speed

        # Update position
        new_pos = transform.position + movement.velocity * dt

        # Clamp to arena bounds
        new_pos = Vector2(
            max(self.ARENA_PADDING, min(800 - self.ARENA_PADDING, new_pos.x)),
            max(self.ARENA_PADDING, min(600 - self.ARENA_PADDING, new_pos.y)),
        )
        transform.position = new_pos

        # Update facing angle
        if aim_dir.magnitude > 0:
            movement.facing_angle = math.atan2(aim_dir.y, aim_dir.x)

        # Weapon cooldown
        if weapon:
            weapon.cooldown = max(0, weapon.cooldown - dt)

    def get_position(self) -> Optional[Vector2]:
        """Get player position."""
        if self._player:
            transform = self._player.get_component(Transform)
            if transform:
                return transform.position
        return None


class BulletSystem:
    """Updates bullet positions and handles lifetime."""

    def __init__(self, entity_manager: EntityManager, bullet_pool: BulletPool):
        """Initialize the system."""
        self._em = entity_manager
        self._pool = bullet_pool
        self._to_release = []

    def update(self, dt: float) -> None:
        """Update all active bullets."""
        self._to_release.clear()

        for entity in self._pool.get_active():
            bullet = entity.get_component(Bullet)
            transform = entity.get_component(Transform)
            poolable = entity.get_component(Poolable)

            if not bullet or not transform or not poolable:
                continue

            if not bullet.active:
                continue

            # Update position
            transform.position = transform.position + bullet.velocity * dt

            # Update lifetime
            bullet.lifetime -= dt

            # Check bounds and lifetime
            pos = transform.position
            if (
                bullet.lifetime <= 0
                or pos.x < -50
                or pos.x > 850
                or pos.y < -50
                or pos.y > 650
            ):
                self._to_release.append(entity)

        # Release expired bullets
        for entity in self._to_release:
            bullet = entity.get_component(Bullet)
            if bullet:
                bullet.active = False
            self._pool.release(entity)


class EnemyAISystem:
    """Updates enemy AI using behavior trees."""

    def __init__(
        self,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
        enemy_pool: EnemyPool,
        bullet_pool: BulletPool,
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._enemy_pool = enemy_pool
        self._bullet_pool = bullet_pool

        # Behavior trees per enemy type (cached)
        self._behavior_trees: Dict[str, BehaviorTree] = {}

        # Player reference
        self._player_position: Optional[Vector2] = None

    def set_player_position(self, position: Vector2) -> None:
        """Update player position for AI."""
        self._player_position = position

    def update(self, dt: float) -> None:
        """Update all enemy AI."""
        for entity in self._enemy_pool.get_active():
            ai = entity.get_component(EnemyAI)
            transform = entity.get_component(Transform)
            movement = entity.get_component(Movement)
            poolable = entity.get_component(Poolable)

            if not ai or not transform or not poolable or not poolable.is_active:
                continue

            # Calculate distance to player
            distance = float("inf")
            if self._player_position:
                distance = transform.position.distance_to(self._player_position)

            # Create AI context
            context = AIContext(
                entity_id=entity.id,
                position=transform.position,
                player_position=self._player_position,
                distance_to_player=distance,
                dt=dt,
                is_alerted=ai.is_alerted,
            )

            # Initialize behavior tree for this enemy if needed
            tree_key = f"{entity.id}_{ai.enemy_type.name}"
            if tree_key not in self._behavior_trees:
                self._behavior_trees[tree_key] = get_behavior_for_type(ai.enemy_type)

            tree = self._behavior_trees[tree_key]

            # Run behavior tree
            tree.tick(context)

            # Apply movement from context
            if hasattr(context, "move_direction") and context.move_direction:
                if movement:
                    movement.velocity = context.move_direction * ai.move_speed
                    transform.position = transform.position + movement.velocity * dt

                    # Keep in arena
                    transform.position = Vector2(
                        max(20, min(780, transform.position.x)),
                        max(20, min(580, transform.position.y)),
                    )

            # Handle attack
            ai.current_cooldown = max(0, ai.current_cooldown - dt)
            if hasattr(context, "should_attack") and context.should_attack:
                if ai.current_cooldown <= 0:
                    self._perform_attack(entity, ai, transform)
                    ai.current_cooldown = ai.attack_cooldown

            # Update alert state
            ai.is_alerted = distance < ai.detection_range

    def _perform_attack(
        self, entity: Entity, ai: EnemyAI, transform: Transform
    ) -> None:
        """Perform enemy attack."""
        from games.protocolo_bandeira.components import EnemyType

        if ai.enemy_type == EnemyType.SHOOTER:
            # Fire bullet at player
            if self._player_position:
                direction = self._player_position - transform.position
                if direction.magnitude > 0:
                    direction = direction.normalize()
                    self._bullet_pool.fire_bullet(
                        transform.position,
                        direction,
                        300.0,
                        EntityTeam.ENEMY,
                        damage=1,
                    )
        elif ai.enemy_type == EnemyType.BOMBER:
            # Bomber will be destroyed when colliding, handled in collision system
            pass
        # Chaser melee damage is handled in collision system


class CollisionSystem:
    """Handles collision detection and resolution."""

    BULLET_HIT_RADIUS = 15.0
    ENEMY_HIT_RADIUS = 20.0
    PLAYER_HIT_RADIUS = 15.0

    def __init__(
        self,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
        bullet_pool: BulletPool,
        enemy_pool: EnemyPool,
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._bullet_pool = bullet_pool
        self._enemy_pool = enemy_pool
        self._player: Optional[Entity] = None
        self._wave_manager = None  # Set externally

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def set_wave_manager(self, manager) -> None:
        """Set wave manager for kill tracking."""
        self._wave_manager = manager

    def update(self, dt: float) -> None:
        """Check for collisions."""
        self._check_bullet_collisions()
        self._check_enemy_player_collisions()

    def _check_bullet_collisions(self) -> None:
        """Check bullet vs entity collisions."""
        bullets_to_release = []
        enemies_to_release = []

        for bullet_entity in self._bullet_pool.get_active():
            bullet = bullet_entity.get_component(Bullet)
            bullet_transform = bullet_entity.get_component(Transform)

            if not bullet or not bullet_transform or not bullet.active:
                continue

            # Check against enemies (player bullets)
            if bullet.owner_team == EntityTeam.PLAYER:
                for enemy_entity in self._enemy_pool.get_active():
                    enemy_poolable = enemy_entity.get_component(Poolable)
                    if not enemy_poolable or not enemy_poolable.is_active:
                        continue

                    enemy_transform = enemy_entity.get_component(Transform)
                    enemy_health = enemy_entity.get_component(Health)

                    if not enemy_transform or not enemy_health:
                        continue

                    distance = bullet_transform.position.distance_to(
                        enemy_transform.position
                    )

                    if distance < self.BULLET_HIT_RADIUS + self.ENEMY_HIT_RADIUS:
                        # Hit!
                        bullets_to_release.append(bullet_entity)
                        alive = enemy_health.take_damage(bullet.damage)

                        if not alive:
                            enemies_to_release.append(enemy_entity)
                            self._dispatcher.dispatch(
                                EnemyKilledEvent(
                                    position=enemy_transform.position, points=100
                                )
                            )

                            # Notify wave manager
                            if self._wave_manager:
                                self._wave_manager.on_enemy_killed()

                        break  # Bullet can only hit one target

            # Check against player (enemy bullets)
            elif bullet.owner_team == EntityTeam.ENEMY and self._player:
                player_transform = self._player.get_component(Transform)
                player_health = self._player.get_component(Health)

                if player_transform and player_health:
                    distance = bullet_transform.position.distance_to(
                        player_transform.position
                    )

                    if distance < self.BULLET_HIT_RADIUS + self.PLAYER_HIT_RADIUS:
                        bullets_to_release.append(bullet_entity)
                        self._damage_player(player_health, bullet.damage)

        # Release bullets
        for entity in bullets_to_release:
            bullet = entity.get_component(Bullet)
            if bullet:
                bullet.active = False
            self._bullet_pool.release(entity)

        # Release enemies
        for entity in enemies_to_release:
            self._enemy_pool.release(entity)

    def _check_enemy_player_collisions(self) -> None:
        """Check enemy vs player collisions (melee)."""
        if not self._player:
            return

        player_transform = self._player.get_component(Transform)
        player_health = self._player.get_component(Health)

        if not player_transform or not player_health:
            return

        enemies_to_release = []

        for enemy_entity in self._enemy_pool.get_active():
            enemy_poolable = enemy_entity.get_component(Poolable)
            if not enemy_poolable or not enemy_poolable.is_active:
                continue

            enemy_transform = enemy_entity.get_component(Transform)
            enemy_ai = enemy_entity.get_component(EnemyAI)

            if not enemy_transform:
                continue

            distance = player_transform.position.distance_to(enemy_transform.position)

            if distance < self.PLAYER_HIT_RADIUS + self.ENEMY_HIT_RADIUS:
                from games.protocolo_bandeira.components import EnemyType

                # Melee damage
                if enemy_ai and enemy_ai.enemy_type == EnemyType.BOMBER:
                    # Bomber explodes
                    self._damage_player(player_health, 2)
                    enemies_to_release.append(enemy_entity)

                    self._dispatcher.dispatch(
                        EnemyKilledEvent(position=enemy_transform.position, points=50)
                    )
                    if self._wave_manager:
                        self._wave_manager.on_enemy_killed()
                else:
                    # Regular melee
                    self._damage_player(player_health, 1)

        for entity in enemies_to_release:
            self._enemy_pool.release(entity)

    def _damage_player(self, health: Health, damage: int) -> None:
        """Apply damage to player."""
        if health.invincible_time > 0:
            return

        alive = health.take_damage(damage)
        health.invincible_time = 1.0

        self._dispatcher.dispatch(
            PlayerDamagedEvent(damage=damage, remaining_health=health.current)
        )

        if not alive:
            score = self._player.get_component(Score) if self._player else None
            self._dispatcher.dispatch(
                PlayerDeathEvent(
                    final_score=score.value if score else 0,
                    total_kills=score.kills if score else 0,
                )
            )


class WeaponSystem:
    """Handles weapon firing."""

    def __init__(
        self,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
        bullet_pool: BulletPool,
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._bullet_pool = bullet_pool
        self._player: Optional[Entity] = None

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def fire(self, position: Vector2, direction: Vector2) -> bool:
        """Fire player weapon.

        Args:
            position: Fire position
            direction: Fire direction (normalized)

        Returns:
            True if bullet was fired
        """
        if not self._player:
            return False

        weapon = self._player.get_component(Weapon)
        if not weapon or not weapon.can_fire():
            return False

        # Fire bullet
        entity = self._bullet_pool.fire_bullet(
            position,
            direction,
            weapon.bullet_speed,
            EntityTeam.PLAYER,
            weapon.bullet_damage,
        )

        if entity:
            weapon.fire()
            self._dispatcher.dispatch(
                BulletFiredEvent(
                    position=position,
                    direction=direction,
                    team=EntityTeam.PLAYER,
                    damage=weapon.bullet_damage,
                )
            )
            return True

        return False


class ScoreSystem:
    """Tracks player score."""

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._player: Optional[Entity] = None

        # Register events
        self._dispatcher.subscribe(EnemyKilledEvent, self._on_enemy_killed)

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def _on_enemy_killed(self, event: EnemyKilledEvent) -> None:
        """Handle enemy killed event."""
        if self._player:
            score = self._player.get_component(Score)
            if score:
                score.add_kill(event.points)

    def update_wave(self, wave: int) -> None:
        """Update wave number in score."""
        if self._player:
            score = self._player.get_component(Score)
            if score:
                score.wave = wave
