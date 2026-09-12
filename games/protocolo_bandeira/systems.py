"""Protocolo Bandeira - Game Systems.

Logic processors for the shooter game.
"""

import math

from games.protocolo_bandeira.ai_behaviors import get_behavior_for_type
from games.protocolo_bandeira.components import (
    AIContext,
    EnemyAI,
    EnemyType,
    EntityTeam,
    Movement,
    Score,
    Weapon,
)
from games.protocolo_bandeira.events import (
    BulletFiredEvent,
    EnemyKilledEvent,
    PlayerDamagedEvent,
    PlayerDeathEvent,
)
from games.protocolo_bandeira.pooling import EnemyPool
from pyguara.ai.behavior_tree import BehaviorTree
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import Poolable
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.action_combat import DamageDealt, Health, apply_damage
from pyguara.kits.projectiles import ProjectileSystem
from pyguara.kits.stats import DamageType


class PlayerControlSystem:
    """Processes player input for movement and shooting."""

    ARENA_PADDING = 30  # Keep player inside arena

    def __init__(self, entity_manager: EntityManager):
        """Initialize the system."""
        self._em = entity_manager
        self._player: Entity | None = None

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

    def get_position(self) -> Vector2 | None:
        """Get player position."""
        if self._player:
            transform = self._player.get_component(Transform)
            if transform:
                return transform.position
        return None


class EnemyAISystem:
    """Updates enemy AI using behavior trees."""

    SHOOTER_BULLET_SPEED = 300.0
    SHOOTER_BULLET_DAMAGE = 1.0
    SHOOTER_BULLET_LIFE = 3.0
    SHOOTER_BULLET_HIT_RADIUS = 15.0

    def __init__(
        self,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
        enemy_pool: EnemyPool,
        projectile_system: ProjectileSystem,
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._enemy_pool = enemy_pool
        self._projectile_system = projectile_system

        # Behavior trees per enemy type (cached)
        self._behavior_trees: dict[str, BehaviorTree] = {}

        # Player reference
        self._player_position: Vector2 | None = None

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
                detection_range=ai.detection_range,
                attack_range=ai.attack_range,
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
        if ai.enemy_type == EnemyType.SHOOTER:
            # Fire a projectile at the player
            if self._player_position:
                direction = self._player_position - transform.position
                if direction.magnitude > 0:
                    direction = direction.normalize()
                    self._projectile_system.spawn(
                        None,
                        transform.position,
                        direction * self.SHOOTER_BULLET_SPEED,
                        damage=self.SHOOTER_BULLET_DAMAGE,
                        damage_type=DamageType.PHYSICAL,
                        life=self.SHOOTER_BULLET_LIFE,
                        hit_radius=self.SHOOTER_BULLET_HIT_RADIUS,
                        team="enemy",
                        attacker=entity.id,
                    )
        elif ai.enemy_type == EnemyType.BOMBER:
            # Bomber will be destroyed when colliding, handled in collision system
            pass
        # Chaser melee damage is handled in collision system


class CollisionSystem:
    """Handles enemy-vs-player melee contact, and reacts to any DamageDealt.

    Bullet-vs-target collision is `ProjectileSystem`'s own job (spatial-hash
    query + `apply_damage()`, #114) -- this system only detects the contact
    `kits/projectiles`/`kits/action_combat` have no vocabulary for (an enemy
    standing on the player). Both paths converge on the same `DamageDealt`
    event, so `_on_damage_dealt()` is the single place that reacts to a
    kill or a player death, regardless of what dealt the damage.
    """

    ENEMY_HIT_RADIUS = 20.0
    PLAYER_HIT_RADIUS = 15.0
    PLAYER_INVINCIBILITY_DURATION = 1.0
    BOMBER_DAMAGE = 2.0
    MELEE_DAMAGE = 1.0

    def __init__(
        self,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
        enemy_pool: EnemyPool,
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._enemy_pool = enemy_pool
        self._player: Entity | None = None
        self._wave_manager = None  # Set externally

        self._dispatcher.subscribe(DamageDealt, self._on_damage_dealt)

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def set_wave_manager(self, manager) -> None:
        """Set wave manager for kill tracking."""
        self._wave_manager = manager

    def update(self, dt: float) -> None:
        """Check for melee-range enemy/player contact."""
        self._check_enemy_player_collisions()

    def _check_enemy_player_collisions(self) -> None:
        """Check enemy vs player collisions (melee)."""
        if not self._player:
            return

        player_transform = self._player.get_component(Transform)
        player_health = self._player.get_component(Health)

        if not player_transform or not player_health:
            return

        bombers_to_release = []

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
                if enemy_ai and enemy_ai.enemy_type == EnemyType.BOMBER:
                    # Bomber explodes -- it dies unconditionally on contact,
                    # not via apply_damage() against its own Health, same as
                    # before this went through kits/action_combat.
                    self._damage_player(player_health, self.BOMBER_DAMAGE)
                    bombers_to_release.append(enemy_entity)

                    self._dispatcher.dispatch(
                        EnemyKilledEvent(position=enemy_transform.position, points=50)
                    )
                    if self._wave_manager:
                        self._wave_manager.on_enemy_killed()
                else:
                    # Regular melee
                    self._damage_player(player_health, self.MELEE_DAMAGE)

        for entity in bombers_to_release:
            self._enemy_pool.release(entity)

    def _damage_player(self, health: Health, damage: float) -> None:
        """Apply melee/bomber damage to the player through the combat pipeline."""
        if not self._player:
            return
        apply_damage(
            self._dispatcher,
            self._player.id,
            health,
            damage,
            DamageType.TRUE,  # Never mitigated, same as before this kit existed.
            invincibility_duration=self.PLAYER_INVINCIBILITY_DURATION,
        )

    def _on_damage_dealt(self, event: DamageDealt) -> None:
        """React to any hit -- bullet or melee -- once apply_damage() lands it."""
        target = self._em.get_entity(event.target)
        if target is None:
            return

        if self._player and event.target == self._player.id:
            if event.amount > 0:
                health = target.get_component(Health)
                self._dispatcher.dispatch(
                    PlayerDamagedEvent(
                        damage=int(event.amount),
                        remaining_health=int(health.current) if health else 0,
                    )
                )
            if event.killed:
                score = self._player.get_component(Score)
                self._dispatcher.dispatch(
                    PlayerDeathEvent(
                        final_score=score.value if score else 0,
                        total_kills=score.kills if score else 0,
                    )
                )
            return

        if event.killed and target.has_component(EnemyAI):
            enemy_transform = target.get_component(Transform)
            self._dispatcher.dispatch(
                EnemyKilledEvent(
                    position=enemy_transform.position
                    if enemy_transform
                    else Vector2.zero(),
                    points=100,
                )
            )
            self._enemy_pool.release(target)
            if self._wave_manager:
                self._wave_manager.on_enemy_killed()


class WeaponSystem:
    """Handles weapon firing."""

    BULLET_LIFE = 3.0
    BULLET_HIT_RADIUS = 15.0

    def __init__(
        self,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
        projectile_system: ProjectileSystem,
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._projectile_system = projectile_system
        self._player: Entity | None = None

    def set_player(self, player: Entity) -> None:
        """Set the player entity."""
        self._player = player

    def fire(self, position: Vector2, direction: Vector2) -> bool:
        """Fire player weapon.

        Args:
            position: Fire position
            direction: Fire direction (normalized)

        Returns:
            True if the weapon was off cooldown and fired. Unlike the
            pooled-entity bullets this replaced, `ProjectileSystem.spawn()`
            has no way to report pool exhaustion, so a full pool (unlikely
            at this game's bullet counts) still resets the cooldown and
            dispatches `BulletFiredEvent` even though nothing rendered.
        """
        if not self._player:
            return False

        weapon = self._player.get_component(Weapon)
        if not weapon or not weapon.can_fire():
            return False

        self._projectile_system.spawn(
            None,
            position,
            direction * weapon.bullet_speed,
            damage=float(weapon.bullet_damage),
            damage_type=DamageType.PHYSICAL,
            life=self.BULLET_LIFE,
            hit_radius=self.BULLET_HIT_RADIUS,
            team="player",
            attacker=self._player.id,
        )
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


class ScoreSystem:
    """Tracks player score."""

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._player: Entity | None = None

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
