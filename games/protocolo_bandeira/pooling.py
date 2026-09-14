"""Protocolo Bandeira - Enemy Pooling.

Pre-allocates enemy entities to avoid garbage collection during gameplay,
on top of `pyguara.ecs.pool.EntityPool` -- this module owns only the
enemy-specific factory (which components an enemy carries, how
`spawn_enemy()` configures one per `EnemyType`). Bullets no longer pool
ECS entities at all; they're `kits.projectiles.Projectile`s instead.
"""

from games.protocolo_bandeira.components import (
    EnemyAI,
    EnemyType,
    Movement,
    ShooterSprite,
)
from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import EntityPool, Poolable
from pyguara.kits.action_combat import Health, Hurtbox
from pyguara.spatial import SpatialTracked


class EnemyPool(EntityPool):
    """Specialized pool for enemy entities."""

    def __init__(self, entity_manager: EntityManager, size: int = 100):
        """Initialize the enemy pool."""
        super().__init__(entity_manager, "enemies", size, self._create_enemy)

    def _create_enemy(self, em: EntityManager, index: int) -> Entity:
        """Create an enemy entity for the pool."""
        entity = em.create_entity(f"enemy_{index}")

        # Origin, not a far-off corner. An idle pooled entity used to stay
        # in every query it matched, so this pool parked its enemies out of
        # sight at (-1000, -1000) to keep them from being hit, drawn or
        # counted. `EntityPool` disables them now, so they match nothing
        # and there is nowhere they need to be parked.
        entity.add_component(Transform(position=Vector2.zero()))
        entity.add_component(
            EnemyAI(
                enemy_type=EnemyType.CHASER,
                detection_range=1400.0,
                attack_range=50.0,
                move_speed=80.0,
            )
        )
        entity.add_component(Health(current=1.0, max_health=1.0))
        entity.add_component(Hurtbox(team="enemy"))
        entity.add_component(SpatialTracked())
        entity.add_component(Movement(speed=80.0))
        entity.add_component(Poolable())
        entity.add_component(
            ShooterSprite(color=Color(200, 50, 50), size=15.0, shape="triangle")
        )

        return entity

    def spawn_enemy(
        self,
        position: Vector2,
        enemy_type: str = "chaser",
        health: float = 1.0,
    ) -> Entity | None:
        """Spawn an enemy from the pool."""
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
            # Detection reaches across the whole arena: these are wave
            # spawns, released off the field and expected to come for the
            # player. A short radius leaves them wandering the margin they
            # spawned in, never entering the fight.
            if enemy_type == "shooter":
                ai.enemy_type = EnemyType.SHOOTER
                ai.detection_range = 1400.0
                ai.attack_range = 320.0
                ai.move_speed = 70.0
                ai.attack_cooldown = 1.5
            elif enemy_type == "bomber":
                ai.enemy_type = EnemyType.BOMBER
                ai.detection_range = 1400.0
                ai.attack_range = 30.0
                ai.move_speed = 135.0
            else:  # chaser
                ai.enemy_type = EnemyType.CHASER
                ai.detection_range = 1400.0
                ai.attack_range = 40.0
                ai.move_speed = 105.0

            ai.is_alerted = False
            ai.current_cooldown = 0.0

        if health_comp:
            health_comp.current = health
            health_comp.max_health = health
            health_comp.invincible_timer = 0.0

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
