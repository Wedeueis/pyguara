"""True Coral - Game Systems.

Logic processors for the puzzle game.
"""

from typing import Dict, Optional, Set, Tuple

from pyguara.ecs.manager import EntityManager
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.common.types import Vector2
from pyguara.animation.tween import Tween, TweenManager
from pyguara.animation.easing import EasingType
from pyguara.common.components import Transform

from games.true_coral.components import (
    GridPosition,
    Block,
    BlockType,
    Pushable,
    Moving,
    MoveHistory,
    LevelState,
)
from games.true_coral.events import (
    PlayerMoveEvent,
    BlockMoveEvent,
    LevelCompleteEvent,
    UndoEvent,
)


# Grid constants
CELL_SIZE = 50
GRID_OFFSET_X = 150
GRID_OFFSET_Y = 100


def grid_to_world(gx: int, gy: int) -> Vector2:
    """Convert grid coordinates to world coordinates."""
    return Vector2(
        GRID_OFFSET_X + gx * CELL_SIZE + CELL_SIZE // 2,
        GRID_OFFSET_Y + gy * CELL_SIZE + CELL_SIZE // 2,
    )


def world_to_grid(wx: float, wy: float) -> Tuple[int, int]:
    """Convert world coordinates to grid coordinates."""
    gx = int((wx - GRID_OFFSET_X) // CELL_SIZE)
    gy = int((wy - GRID_OFFSET_Y) // CELL_SIZE)
    return (gx, gy)


class GridSystem:
    """Manages grid state and validates moves."""

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the grid system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher

        # Grid state: maps (x, y) -> set of entity IDs at that position
        self._grid: Dict[Tuple[int, int], Set[str]] = {}

        # Cache entity references
        self._player: Optional[Entity] = None
        self._move_history: Optional[MoveHistory] = None
        self._level_state: Optional[LevelState] = None

        # Register event handlers
        self._dispatcher.subscribe(PlayerMoveEvent, self._on_player_move)
        self._dispatcher.subscribe(UndoEvent, self._on_undo)

    def rebuild_grid(self) -> None:
        """Rebuild the grid index from entities."""
        self._grid.clear()
        self._player = None

        for entity in self._em.get_entities_with(GridPosition):
            grid_pos = entity.get_component(GridPosition)
            pos_key = grid_pos.to_tuple()

            if pos_key not in self._grid:
                self._grid[pos_key] = set()
            self._grid[pos_key].add(entity.id)

            # Cache player reference
            block = entity.get_component(Block)
            if block and block.block_type == BlockType.PLAYER:
                self._player = entity
                self._move_history = entity.get_component(MoveHistory)

        # Find level state entity
        for entity in self._em.get_entities_with(LevelState):
            self._level_state = entity.get_component(LevelState)
            break

    def get_entities_at(self, x: int, y: int) -> Set[str]:
        """Get all entity IDs at a grid position."""
        return self._grid.get((x, y), set())

    def is_walkable(self, x: int, y: int) -> bool:
        """Check if a position is walkable (no walls)."""
        entities = self.get_entities_at(x, y)
        for eid in entities:
            entity = self._em.get_entity(eid)
            if entity:
                block = entity.get_component(Block)
                if block and block.block_type == BlockType.WALL:
                    return False
        return True

    def get_pushable_at(self, x: int, y: int) -> Optional[Entity]:
        """Get a pushable entity at position, if any."""
        entities = self.get_entities_at(x, y)
        for eid in entities:
            entity = self._em.get_entity(eid)
            if entity and entity.has_component(Pushable):
                return entity
        return None

    def move_entity(self, entity: Entity, new_x: int, new_y: int) -> None:
        """Update an entity's grid position."""
        grid_pos = entity.get_component(GridPosition)
        if not grid_pos:
            return

        old_key = grid_pos.to_tuple()
        new_key = (new_x, new_y)

        # Update grid index
        if old_key in self._grid and entity.id in self._grid[old_key]:
            self._grid[old_key].remove(entity.id)

        if new_key not in self._grid:
            self._grid[new_key] = set()
        self._grid[new_key].add(entity.id)

        # Update component
        grid_pos.x = new_x
        grid_pos.y = new_y

    def _on_player_move(self, event: PlayerMoveEvent) -> None:
        """Handle player move request."""
        if not self._player or self._is_animating():
            return

        player_grid = self._player.get_component(GridPosition)
        if not player_grid:
            return

        dx, dy = event.direction
        new_x = player_grid.x + dx
        new_y = player_grid.y + dy

        # Check if destination has a wall
        if not self.is_walkable(new_x, new_y):
            return

        # Check for pushable
        pushable = self.get_pushable_at(new_x, new_y)
        crate_from = (-1, -1)

        if pushable:
            # Try to push the crate
            push_x = new_x + dx
            push_y = new_y + dy

            # Can we push?
            if not self.is_walkable(push_x, push_y):
                return
            if self.get_pushable_at(push_x, push_y):
                return  # Can't push crate into another crate

            # Record crate position before move
            crate_grid = pushable.get_component(GridPosition)
            if crate_grid:
                crate_from = (crate_grid.x, crate_grid.y)

            # Move crate
            self.move_entity(pushable, push_x, push_y)
            self._dispatcher.dispatch(
                BlockMoveEvent(
                    entity_id=pushable.id,
                    from_pos=(new_x, new_y),
                    to_pos=(push_x, push_y),
                )
            )

        # Record move for undo
        player_from = (player_grid.x, player_grid.y)
        if self._move_history:
            self._move_history.push(player_from, crate_from)

        # Move player
        self.move_entity(self._player, new_x, new_y)
        self._dispatcher.dispatch(
            BlockMoveEvent(
                entity_id=self._player.id,
                from_pos=player_from,
                to_pos=(new_x, new_y),
            )
        )

        # Update move count
        if self._level_state:
            self._level_state.total_moves += 1

        # Check win condition
        self._check_win_condition()

    def _on_undo(self, event: UndoEvent) -> None:
        """Handle undo request."""
        if not self._player or not self._move_history or self._is_animating():
            return

        last_move = self._move_history.pop()
        if not last_move:
            return

        player_from, crate_from = last_move
        player_grid = self._player.get_component(GridPosition)
        if not player_grid:
            return

        # Find crate that was pushed (if any)
        if crate_from != (-1, -1):
            # Player moved from player_from to current position
            # Crate moved from crate_from to player's current position (before undo)
            # So crate is now at player's current position
            crate = self.get_pushable_at(player_grid.x, player_grid.y)
            # Actually, crate would be at player_from + direction
            # This is tricky - let's find the crate in direction from player
            dx = player_grid.x - player_from[0]
            dy = player_grid.y - player_from[1]
            crate_current_x = player_grid.x + dx
            crate_current_y = player_grid.y + dy
            crate = self.get_pushable_at(crate_current_x, crate_current_y)

            if crate:
                self.move_entity(crate, crate_from[0], crate_from[1])
                self._dispatcher.dispatch(
                    BlockMoveEvent(
                        entity_id=crate.id,
                        from_pos=(crate_current_x, crate_current_y),
                        to_pos=crate_from,
                    )
                )

        # Move player back
        current_pos = (player_grid.x, player_grid.y)
        self.move_entity(self._player, player_from[0], player_from[1])
        self._dispatcher.dispatch(
            BlockMoveEvent(
                entity_id=self._player.id,
                from_pos=current_pos,
                to_pos=player_from,
            )
        )

        if self._level_state:
            self._level_state.total_moves = max(0, self._level_state.total_moves - 1)

    def _is_animating(self) -> bool:
        """Check if any entity is currently animating."""
        for entity in self._em.get_entities_with(Moving):
            return True
        return False

    def _check_win_condition(self) -> None:
        """Check if all crates are on goals."""
        goals = set()
        crates = set()

        for entity in self._em.get_entities_with(GridPosition, Block):
            block = entity.get_component(Block)
            grid_pos = entity.get_component(GridPosition)

            if block.block_type == BlockType.GOAL:
                goals.add(grid_pos.to_tuple())
            elif block.block_type == BlockType.CRATE:
                crates.add(grid_pos.to_tuple())

        # Win if all goals have crates
        if goals and crates and goals == crates:
            if self._level_state and not self._level_state.is_complete:
                self._level_state.is_complete = True
                self._dispatcher.dispatch(
                    LevelCompleteEvent(
                        level_index=self._level_state.level_index,
                        total_moves=self._level_state.total_moves,
                    )
                )


class BlockMoveSystem:
    """Animates block movements using tweens."""

    MOVE_DURATION = 0.12  # Seconds per move animation

    def __init__(
        self, entity_manager: EntityManager, event_dispatcher: EventDispatcher
    ):
        """Initialize the block move system."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._tween_manager = TweenManager()

        # Map entity ID to active tween
        self._active_tweens: Dict[str, Tween] = {}

        # Register event handlers
        self._dispatcher.subscribe(BlockMoveEvent, self._on_block_move)

    def update(self, dt: float) -> None:
        """Update all active tweens."""
        self._tween_manager.update(dt)

        # Update entity transforms based on tween progress
        entities_to_remove = []

        for entity_id, tween in self._active_tweens.items():
            entity = self._em.get_entity(entity_id)
            if not entity:
                entities_to_remove.append(entity_id)
                continue

            transform = entity.get_component(Transform)
            moving = entity.get_component(Moving)

            if transform and moving:
                # Get interpolated position from tween
                value = tween.current_value
                if isinstance(value, tuple):
                    transform.position = Vector2(value[0], value[1])

            # Check if complete
            if tween.is_complete:
                entities_to_remove.append(entity_id)
                # Snap to final position and remove Moving component
                if moving:
                    transform.position = moving.to_pos
                    entity.remove_component(Moving)

        for entity_id in entities_to_remove:
            if entity_id in self._active_tweens:
                del self._active_tweens[entity_id]

    def _on_block_move(self, event: BlockMoveEvent) -> None:
        """Handle block move event by creating animation."""
        entity = self._em.get_entity(event.entity_id)
        if not entity:
            return

        from_world = grid_to_world(event.from_pos[0], event.from_pos[1])
        to_world = grid_to_world(event.to_pos[0], event.to_pos[1])

        # Add Moving component
        moving = Moving(from_pos=from_world, to_pos=to_world, progress=0.0)
        if entity.has_component(Moving):
            entity.remove_component(Moving)
        entity.add_component(moving)

        # Create tween
        tween = Tween(
            start_value=(from_world.x, from_world.y),
            end_value=(to_world.x, to_world.y),
            duration=self.MOVE_DURATION,
            easing=EasingType.EASE_OUT_QUAD,
        )
        tween.start()

        self._tween_manager.add(tween)
        self._active_tweens[event.entity_id] = tween


class InputSystem:
    """Processes input and dispatches movement events."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the input system."""
        self._dispatcher = event_dispatcher
        self._move_cooldown = 0.0

    def update(self, dt: float) -> None:
        """Update cooldown."""
        if self._move_cooldown > 0:
            self._move_cooldown -= dt

    def handle_move(self, direction: Tuple[int, int]) -> None:
        """Request player movement in a direction."""
        if self._move_cooldown <= 0:
            self._dispatcher.dispatch(PlayerMoveEvent(direction=direction))
            self._move_cooldown = 0.15  # Prevent rapid-fire moves

    def handle_undo(self) -> None:
        """Request undo."""
        self._dispatcher.dispatch(UndoEvent())
