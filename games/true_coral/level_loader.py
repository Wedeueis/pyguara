"""True Coral - Level Loader.

Loads puzzle levels from JSON files.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from pyguara.ecs.manager import EntityManager
from pyguara.common.types import Color
from pyguara.common.components import Transform

from games.true_coral.components import (
    GridPosition,
    Block,
    BlockType,
    Pushable,
    MoveHistory,
    LevelState,
    GridSprite,
)
from games.true_coral.systems import grid_to_world


# Character mappings for level data
CHAR_MAP = {
    "#": BlockType.WALL,
    ".": BlockType.GOAL,
    "$": BlockType.CRATE,
    "@": BlockType.PLAYER,
    " ": BlockType.FLOOR,
    "*": "CRATE_ON_GOAL",  # Crate already on goal
    "+": "PLAYER_ON_GOAL",  # Player on goal
}

# Colors for each block type
COLOR_MAP = {
    BlockType.WALL: Color(60, 60, 80),
    BlockType.GOAL: Color(100, 180, 100),
    BlockType.CRATE: Color(180, 120, 60),
    BlockType.PLAYER: Color(80, 140, 200),
    BlockType.FLOOR: Color(40, 40, 50),
}


class LevelLoader:
    """Loads and manages puzzle levels."""

    def __init__(self, levels_dir: Optional[Path] = None):
        """Initialize the level loader."""
        if levels_dir is None:
            levels_dir = Path(__file__).parent / "assets" / "levels"
        self._levels_dir = levels_dir
        self._levels: List[Dict[str, Any]] = []
        self._current_level = 0

    def discover_levels(self) -> int:
        """Find all level files in the levels directory."""
        self._levels.clear()

        if not self._levels_dir.exists():
            # Create default levels
            self._create_default_levels()

        level_files = sorted(self._levels_dir.glob("level_*.json"))
        for lf in level_files:
            try:
                with open(lf, "r") as f:
                    level_data = json.load(f)
                    level_data["_path"] = str(lf)
                    self._levels.append(level_data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Failed to load level {lf}: {e}")

        if not self._levels:
            self._create_default_levels()
            return self.discover_levels()

        return len(self._levels)

    def _create_default_levels(self) -> None:
        """Create default level files if none exist."""
        self._levels_dir.mkdir(parents=True, exist_ok=True)

        # Level 1: Simple intro
        level1 = {
            "name": "First Steps",
            "author": "PyGuara",
            "grid": [
                "########",
                "#      #",
                "# @$ . #",
                "#      #",
                "########",
            ],
        }

        # Level 2: Two crates
        level2 = {
            "name": "Double Trouble",
            "author": "PyGuara",
            "grid": [
                "##########",
                "#        #",
                "# @$$..  #",
                "#        #",
                "##########",
            ],
        }

        # Level 3: Corner puzzle
        level3 = {
            "name": "Corner Case",
            "author": "PyGuara",
            "grid": [
                "########",
                "#.     #",
                "#.#  $ #",
                "#  $@  #",
                "#  #   #",
                "########",
            ],
        }

        # Level 4: Classic layout
        level4 = {
            "name": "Classic",
            "author": "PyGuara",
            "grid": [
                "  #####",
                "###   #",
                "#.@$  #",
                "### $.#",
                "#.##$ #",
                "# # . ##",
                "#$  $$.#",
                "#   .  #",
                "########",
            ],
        }

        for i, level in enumerate([level1, level2, level3, level4], 1):
            path = self._levels_dir / f"level_{i:02d}.json"
            with open(path, "w") as f:
                json.dump(level, f, indent=2)

    def get_level_count(self) -> int:
        """Get total number of levels."""
        return len(self._levels)

    def get_current_level(self) -> int:
        """Get current level index."""
        return self._current_level

    def set_current_level(self, index: int) -> None:
        """Set current level index."""
        self._current_level = max(0, min(index, len(self._levels) - 1))

    def next_level(self) -> bool:
        """Advance to next level. Returns True if there is a next level."""
        if self._current_level < len(self._levels) - 1:
            self._current_level += 1
            return True
        return False

    def load_level(self, entity_manager: EntityManager, level_index: int = -1) -> bool:
        """Load a level into the entity manager.

        Args:
            entity_manager: The entity manager to populate
            level_index: Level to load (-1 for current)

        Returns:
            True if level loaded successfully
        """
        if level_index < 0:
            level_index = self._current_level

        if level_index >= len(self._levels):
            return False

        level_data = self._levels[level_index]
        grid = level_data.get("grid", [])

        # Create level state entity
        state_entity = entity_manager.create_entity("level_state")
        state_entity.add_component(LevelState(level_index=level_index))

        # Parse grid
        for y, row in enumerate(grid):
            for x, char in enumerate(row):
                block_type = CHAR_MAP.get(char)
                if block_type is None:
                    continue

                # Handle special combined states
                create_goal = False
                if block_type == "CRATE_ON_GOAL":
                    block_type = BlockType.CRATE
                    create_goal = True
                elif block_type == "PLAYER_ON_GOAL":
                    block_type = BlockType.PLAYER
                    create_goal = True

                # Create goal underneath if needed
                if create_goal:
                    self._create_block_entity(
                        entity_manager, x, y, BlockType.GOAL, is_floor=True
                    )

                # Create floor under most entities
                if block_type not in (BlockType.WALL, BlockType.FLOOR):
                    self._create_block_entity(
                        entity_manager, x, y, BlockType.FLOOR, is_floor=True
                    )

                # Create the main entity
                self._create_block_entity(
                    entity_manager,
                    x,
                    y,
                    block_type,
                    is_floor=(block_type == BlockType.FLOOR),
                )

        return True

    def _create_block_entity(
        self,
        entity_manager: EntityManager,
        x: int,
        y: int,
        block_type: BlockType,
        is_floor: bool = False,
    ) -> None:
        """Create a block entity at the given grid position."""
        name = f"{block_type.name.lower()}_{x}_{y}"
        if is_floor:
            name = f"floor_{x}_{y}"

        entity = entity_manager.create_entity(name)

        # Grid position
        entity.add_component(GridPosition(x=x, y=y))

        # Block type
        entity.add_component(Block(block_type=block_type))

        # World transform
        world_pos = grid_to_world(x, y)
        entity.add_component(Transform(position=world_pos))

        # Sprite
        color = COLOR_MAP.get(block_type, Color(255, 255, 255))
        entity.add_component(GridSprite(color=color, is_floor=is_floor))

        # Special components
        if block_type == BlockType.CRATE:
            entity.add_component(Pushable())
        elif block_type == BlockType.PLAYER:
            entity.add_component(MoveHistory())

    def get_level_name(self, level_index: int = -1) -> str:
        """Get the name of a level."""
        if level_index < 0:
            level_index = self._current_level
        if level_index < len(self._levels):
            return self._levels[level_index].get("name", f"Level {level_index + 1}")
        return "Unknown"
