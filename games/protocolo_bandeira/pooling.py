"""Protocolo Bandeira - Object Pooling.

Pre-allocates entities to avoid garbage collection during gameplay.
"""

from typing import List, Optional, Callable

from pyguara.ecs.manager import EntityManager
from pyguara.ecs.entity import Entity
from pyguara.common.types import Vector2, Color
from pyguara.common.components import Transform

from games.protocolo_bandeira.components import (
    Bullet,
    Poolable,
    ShooterSprite,
    EntityTeam,
)


class ObjectPool:
    """Generic object pool for entities."""

    def __init__(
        self,
        entity_manager: EntityManager,
        pool_name: str,
        initial_size: int,
        factory: Callable[[EntityManager, int], Entity],
    ):
        """Initialize the pool.

        Args:
            entity_manager: The entity manager
            pool_name: Name of this pool
            initial_size: Number of entities to pre-allocate
            factory: Function to create new entities
        """
        self._em = entity_manager
        self._pool_name = pool_name
        self._factory = factory

        # Pool storage
        self._available: List[Entity] = []
        self._active: List[Entity] = []

        # Pre-allocate
        for i in range(initial_size):
            entity = self._factory(self._em, i)
            poolable = entity.get_component(Poolable)
            if poolable:
                poolable.pool_name = pool_name
                poolable.is_active = False
            self._available.append(entity)

    def acquire(self) -> Optional[Entity]:
        """Get an entity from the pool.

        Returns:
            An available entity, or None if pool is exhausted
        """
        if not self._available:
            # Pool exhausted - could expand here
            return None

        entity = self._available.pop()
        poolable = entity.get_component(Poolable)
        if poolable:
            poolable.is_active = True
        self._active.append(entity)
        return entity

    def release(self, entity: Entity) -> None:
        """Return an entity to the pool."""
        if entity in self._active:
            self._active.remove(entity)

        poolable = entity.get_component(Poolable)
        if poolable:
            poolable.is_active = False

        self._available.append(entity)

    def get_active(self) -> List[Entity]:
        """Get all active entities."""
        return self._active.copy()

    @property
    def available_count(self) -> int:
        """Number of available entities."""
        return len(self._available)

    @property
    def active_count(self) -> int:
        """Number of active entities."""
        return len(self._active)


class BulletPool(ObjectPool):
    """Specialized pool for bullet entities."""

    def __init__(self, entity_manager: EntityManager, size: int = 500):
        """Initialize the bullet pool."""
        super().__init__(entity_manager, "bullets", size, self._create_bullet)

    def _create_bullet(self, em: EntityManager, index: int) -> Entity:
        """Create a bullet entity for the pool."""
        entity = em.create_entity(f"bullet_{index}")

        entity.add_component(Transform(position=Vector2(-1000, -1000)))  # Off-screen
        entity.add_component(
            Bullet(
                damage=1,
                owner_team=EntityTeam.NEUTRAL,
                velocity=Vector2.zero(),
                lifetime=3.0,
                active=False,
            )
        )
        entity.add_component(Poolable(pool_name="bullets", is_active=False))
        entity.add_component(
            ShooterSprite(color=Color(255, 255, 100), size=4.0, shape="circle")
        )

        return entity

    def fire_bullet(
        self,
        position: Vector2,
        direction: Vector2,
        speed: float,
        team: EntityTeam,
        damage: int = 1,
    ) -> Optional[Entity]:
        """Fire a bullet from the pool."""
        entity = self.acquire()
        if not entity:
            return None

        transform = entity.get_component(Transform)
        bullet = entity.get_component(Bullet)
        sprite = entity.get_component(ShooterSprite)

        if transform:
            transform.position = position

        if bullet:
            bullet.velocity = direction * speed
            bullet.owner_team = team
            bullet.damage = damage
            bullet.lifetime = 3.0
            bullet.active = True

        # Color based on team
        if sprite:
            if team == EntityTeam.PLAYER:
                sprite.color = Color(100, 200, 255)
            else:
                sprite.color = Color(255, 100, 100)

        return entity


class EnemyPool(ObjectPool):
    """Specialized pool for enemy entities."""

    def __init__(self, entity_manager: EntityManager, size: int = 100):
        """Initialize the enemy pool."""
        super().__init__(entity_manager, "enemies", size, self._create_enemy)

    def _create_enemy(self, em: EntityManager, index: int) -> Entity:
        """Create an enemy entity for the pool."""
        from games.protocolo_bandeira.components import (
            EnemyAI,
            EnemyType,
            Health,
            Movement,
        )

        entity = em.create_entity(f"enemy_{index}")

        entity.add_component(Transform(position=Vector2(-1000, -1000)))
        entity.add_component(
            EnemyAI(
                enemy_type=EnemyType.CHASER,
                detection_range=300.0,
                attack_range=50.0,
                move_speed=80.0,
            )
        )
        entity.add_component(Health(current=1, max_health=1))
        entity.add_component(Movement(speed=80.0))
        entity.add_component(Poolable(pool_name="enemies", is_active=False))
        entity.add_component(
            ShooterSprite(color=Color(200, 50, 50), size=15.0, shape="triangle")
        )

        return entity

    def spawn_enemy(
        self,
        position: Vector2,
        enemy_type: str = "chaser",
        health: int = 1,
    ) -> Optional[Entity]:
        """Spawn an enemy from the pool."""
        from games.protocolo_bandeira.components import EnemyAI, EnemyType, Health

        entity = self.acquire()
        if not entity:
            return None

        transform = entity.get_component(Transform)
        ai = entity.get_component(EnemyAI)
        health_comp = entity.get_component(Health)
        sprite = entity.get_component(ShooterSprite)

        if transform:
            transform.position = position

        if ai:
            # Configure based on enemy type
            if enemy_type == "shooter":
                ai.enemy_type = EnemyType.SHOOTER
                ai.detection_range = 400.0
                ai.attack_range = 250.0
                ai.move_speed = 60.0
                ai.attack_cooldown = 1.5
            elif enemy_type == "bomber":
                ai.enemy_type = EnemyType.BOMBER
                ai.detection_range = 350.0
                ai.attack_range = 30.0
                ai.move_speed = 120.0
            else:  # chaser
                ai.enemy_type = EnemyType.CHASER
                ai.detection_range = 300.0
                ai.attack_range = 40.0
                ai.move_speed = 90.0

            ai.is_alerted = False
            ai.current_cooldown = 0.0

        if health_comp:
            health_comp.current = health
            health_comp.max_health = health

        if sprite:
            # Color based on type
            if enemy_type == "shooter":
                sprite.color = Color(200, 100, 200)
                sprite.shape = "square"
            elif enemy_type == "bomber":
                sprite.color = Color(255, 150, 50)
                sprite.shape = "circle"
            else:
                sprite.color = Color(200, 50, 50)
                sprite.shape = "triangle"

        return entity
