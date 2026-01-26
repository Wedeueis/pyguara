"""Guará & Falcão - Level Builder.

Creates level entities from tilemap data.
"""

from pathlib import Path
from typing import Dict, Any, Optional

from pyguara.ecs.manager import EntityManager
from pyguara.common.types import Vector2, Color
from pyguara.common.components import Transform
from pyguara.physics.components import RigidBody, Collider
from pyguara.physics.types import BodyType
from pyguara.physics.platformer_controller import PlatformerController

from games.guara_falcao.components import (
    PlayerState,
    Health,
    Score,
    CameraTarget,
    PlatformSprite,
    CharacterSprite,
    Collectible,
    ZoneTrigger,
    Hazard,
)


# Tile size in pixels
TILE_SIZE = 32

# Tile types
TILE_EMPTY = 0
TILE_SOLID = 1
TILE_PLATFORM = 2  # One-way platform
TILE_SPAWN = 3
TILE_COIN = 4
TILE_CHECKPOINT = 5
TILE_HAZARD = 6
TILE_GOAL = 7


class LevelBuilder:
    """Builds level entities from tilemap data."""

    def __init__(self, levels_dir: Optional[Path] = None):
        """Initialize the level builder."""
        if levels_dir is None:
            levels_dir = Path(__file__).parent / "assets" / "levels"
        self._levels_dir = levels_dir
        self._spawn_point = Vector2(100, 300)

    def create_default_level(self) -> Dict[str, Any]:
        """Create a default level layout."""
        # Simple platformer level
        level = {
            "name": "Tutorial Valley",
            "width": 40,
            "height": 20,
            "tiles": [],
            "player_spawn": [4, 14],
            "collectibles": [[8, 14], [12, 12], [18, 10], [25, 14]],
            "checkpoints": [[15, 14]],
            "goal": [38, 14],
        }

        # Create tilemap (20 rows, 40 columns)
        tiles = [[0] * 40 for _ in range(20)]

        # Ground (row 15)
        for x in range(40):
            tiles[15][x] = TILE_SOLID
            tiles[16][x] = TILE_SOLID
            tiles[17][x] = TILE_SOLID
            tiles[18][x] = TILE_SOLID
            tiles[19][x] = TILE_SOLID

        # Platforms
        # First platform
        for x in range(10, 15):
            tiles[12][x] = TILE_SOLID

        # Second platform (higher)
        for x in range(16, 22):
            tiles[9][x] = TILE_SOLID

        # Third platform
        for x in range(24, 30):
            tiles[12][x] = TILE_SOLID

        # Pit
        for x in range(32, 35):
            for y in range(15, 20):
                tiles[y][x] = TILE_EMPTY

        # Add hazard at bottom of pit
        tiles[19][33] = TILE_HAZARD

        # Walls on sides
        for y in range(15):
            tiles[y][0] = TILE_SOLID
            tiles[y][39] = TILE_SOLID

        level["tiles"] = tiles
        return level

    def load_level(
        self, entity_manager: EntityManager, level_data: Optional[Dict] = None
    ) -> Vector2:
        """Load a level into the entity manager.

        Args:
            entity_manager: The entity manager to populate
            level_data: Level data dict (uses default if None)

        Returns:
            Player spawn position
        """
        if level_data is None:
            level_data = self.create_default_level()

        tiles = level_data.get("tiles", [])
        spawn = level_data.get("player_spawn", [4, 14])
        self._spawn_point = Vector2(spawn[0] * TILE_SIZE, spawn[1] * TILE_SIZE)

        # Process tilemap
        for y, row in enumerate(tiles):
            for x, tile in enumerate(row):
                if tile == TILE_SOLID:
                    self._create_solid_tile(entity_manager, x, y)
                elif tile == TILE_HAZARD:
                    self._create_hazard(entity_manager, x, y)

        # Create collectibles
        for pos in level_data.get("collectibles", []):
            self._create_collectible(entity_manager, pos[0], pos[1])

        # Create checkpoints
        for pos in level_data.get("checkpoints", []):
            self._create_checkpoint(entity_manager, pos[0], pos[1])

        # Create goal
        goal_pos = level_data.get("goal")
        if goal_pos:
            self._create_goal(entity_manager, goal_pos[0], goal_pos[1])

        return self._spawn_point

    def _create_solid_tile(
        self, entity_manager: EntityManager, gx: int, gy: int
    ) -> None:
        """Create a solid tile entity."""
        entity = entity_manager.create_entity(f"tile_{gx}_{gy}")

        world_x = gx * TILE_SIZE + TILE_SIZE // 2
        world_y = gy * TILE_SIZE + TILE_SIZE // 2

        entity.add_component(Transform(position=Vector2(world_x, world_y)))
        entity.add_component(RigidBody(body_type=BodyType.STATIC))
        entity.add_component(Collider(dimensions=[TILE_SIZE, TILE_SIZE]))
        entity.add_component(
            PlatformSprite(color=Color(70, 80, 90), size=Vector2(TILE_SIZE, TILE_SIZE))
        )

    def _create_hazard(self, entity_manager: EntityManager, gx: int, gy: int) -> None:
        """Create a hazard entity."""
        entity = entity_manager.create_entity(f"hazard_{gx}_{gy}")

        world_x = gx * TILE_SIZE + TILE_SIZE // 2
        world_y = gy * TILE_SIZE + TILE_SIZE // 2

        entity.add_component(Transform(position=Vector2(world_x, world_y)))
        entity.add_component(RigidBody(body_type=BodyType.STATIC))
        entity.add_component(
            Collider(dimensions=[TILE_SIZE, TILE_SIZE], is_sensor=True)
        )
        entity.add_component(Hazard(damage=999, knockback_force=0.0))  # Instant kill
        entity.add_component(
            PlatformSprite(color=Color(200, 50, 50), size=Vector2(TILE_SIZE, TILE_SIZE))
        )

    def _create_collectible(
        self, entity_manager: EntityManager, gx: int, gy: int
    ) -> None:
        """Create a coin collectible."""
        entity = entity_manager.create_entity(f"coin_{gx}_{gy}")

        world_x = gx * TILE_SIZE + TILE_SIZE // 2
        world_y = gy * TILE_SIZE + TILE_SIZE // 2

        entity.add_component(Transform(position=Vector2(world_x, world_y)))
        entity.add_component(Collectible(value=1, collect_type="coin"))
        entity.add_component(
            CharacterSprite(color=Color(255, 220, 50), size=Vector2(16, 16))
        )

    def _create_checkpoint(
        self, entity_manager: EntityManager, gx: int, gy: int
    ) -> None:
        """Create a checkpoint trigger."""
        entity = entity_manager.create_entity(f"checkpoint_{gx}_{gy}")

        world_x = gx * TILE_SIZE + TILE_SIZE // 2
        world_y = gy * TILE_SIZE + TILE_SIZE // 2

        entity.add_component(Transform(position=Vector2(world_x, world_y)))
        entity.add_component(
            ZoneTrigger(
                zone_name=f"checkpoint_{gx}_{gy}",
                spawn_point=Vector2(world_x, world_y - TILE_SIZE),
            )
        )
        entity.add_component(
            CharacterSprite(color=Color(100, 200, 100), size=Vector2(8, 32))
        )

    def _create_goal(self, entity_manager: EntityManager, gx: int, gy: int) -> None:
        """Create a goal trigger."""
        entity = entity_manager.create_entity("goal")

        world_x = gx * TILE_SIZE + TILE_SIZE // 2
        world_y = gy * TILE_SIZE + TILE_SIZE // 2

        entity.add_component(Transform(position=Vector2(world_x, world_y)))
        entity.add_component(
            ZoneTrigger(
                zone_name="goal",
                spawn_point=Vector2(world_x, world_y),
            )
        )
        entity.add_component(
            CharacterSprite(color=Color(50, 200, 255), size=Vector2(16, 48))
        )

    def create_player(
        self, entity_manager: EntityManager, spawn_pos: Optional[Vector2] = None
    ) -> str:
        """Create the player entity.

        Args:
            entity_manager: The entity manager
            spawn_pos: Spawn position (uses level spawn if None)

        Returns:
            Player entity ID
        """
        if spawn_pos is None:
            spawn_pos = self._spawn_point

        player = entity_manager.create_entity("player")

        # Transform
        player.add_component(Transform(position=spawn_pos))

        # Physics
        player.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=1.0))
        player.add_component(Collider(dimensions=[24, 40]))

        # Platformer controller with game-feel tuning
        # Note: ground_check_distance must be > half player height (20) to detect ground
        # from the player's center position
        player.add_component(
            PlatformerController(
                move_speed=180.0,
                jump_force=350.0,
                max_fall_speed=450.0,
                acceleration=0.2,
                air_control=0.8,
                coyote_time=0.15,
                jump_buffer=0.1,
                wall_slide_enabled=True,
                wall_slide_speed=60.0,
                wall_jump_enabled=True,
                ground_check_distance=25.0,  # Must exceed half player height (20) + margin
                wall_check_distance=16.0,  # Must exceed half player width (12) + margin
            )
        )

        # Game components
        player.add_component(PlayerState())
        player.add_component(Health(current=3, max_health=3))
        player.add_component(Score())
        player.add_component(CameraTarget(look_ahead=40.0, vertical_offset=-20.0))

        # Visual
        player.add_component(
            CharacterSprite(
                color=Color(200, 120, 80),  # Guará (maned wolf) orange-brown
                size=Vector2(24, 40),
            )
        )

        return player.id

    def get_spawn_point(self) -> Vector2:
        """Get the level's spawn point."""
        return self._spawn_point
