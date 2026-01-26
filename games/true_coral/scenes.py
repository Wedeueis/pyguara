"""True Coral - Game Scenes.

Menu and gameplay scenes for the puzzle game.
"""

import sys
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.common.types import Vector2, Color, Rect
from pyguara.common.components import Transform
from pyguara.ui.manager import UIManager
from pyguara.ui.layout import BoxContainer
from pyguara.ui.components.button import Button
from pyguara.ui.components.label import Label
from pyguara.input.manager import InputManager
from pyguara.input.types import InputDevice, ActionType
from pyguara.input.keys import UP, DOWN, LEFT, RIGHT, Z, R, ESCAPE
from pyguara.input.events import OnActionEvent
from pyguara.scripting.coroutines import CoroutineManager, wait_for_seconds

from games.true_coral.components import (
    Block,
    BlockType,
    GridSprite,
    LevelState,
)
from games.true_coral.systems import (
    GridSystem,
    BlockMoveSystem,
    InputSystem,
    CELL_SIZE,
)
from games.true_coral.events import (
    LevelCompleteEvent,
    RestartLevelEvent,
    NextLevelEvent,
)
from games.true_coral.level_loader import LevelLoader


class MenuScene(Scene):
    """Main menu for True Coral."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the menu scene."""
        super().__init__("MenuScene", event_dispatcher)

    def on_enter(self) -> None:
        """Create menu UI."""
        print("True Coral - Menu")
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        # Title
        title = Label("TRUE CORAL", position=Vector2(280, 100))
        ui_manager.add_element(title)

        # Subtitle
        subtitle = Label("A Sokoban Puzzle", position=Vector2(300, 140))
        ui_manager.add_element(subtitle)

        # Button container
        container = BoxContainer(
            position=Vector2(300, 220), size=Vector2(200, 200), spacing=15
        )

        btn_start = Button("START GAME", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_start.on_click = self._on_start_click
        container.add_child(btn_start)

        btn_quit = Button("QUIT", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_quit.on_click = self._on_quit_click
        container.add_child(btn_quit)

        container.layout()
        ui_manager.add_element(container)

    def _on_start_click(self, el) -> None:
        """Start the game."""
        scene_manager = self.container.get(SceneManager)
        game_scene = GameScene(self.event_dispatcher)
        scene_manager.register(game_scene)
        scene_manager.push_scene("GameScene")

    def _on_quit_click(self, el) -> None:
        """Quit the game."""
        sys.exit(0)

    def on_exit(self) -> None:
        """Cleanup."""
        pass

    def update(self, dt: float) -> None:
        """Update logic."""
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the scene."""
        world_renderer.clear(Color(30, 40, 50))


class GameScene(Scene):
    """Main gameplay scene for True Coral."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the game scene."""
        super().__init__("GameScene", event_dispatcher)
        self._grid_system: GridSystem | None = None
        self._move_system: BlockMoveSystem | None = None
        self._input_system: InputSystem | None = None
        self._level_loader: LevelLoader | None = None
        self._coroutine_manager: CoroutineManager | None = None
        self._show_complete_ui = False
        self._input_manager: InputManager | None = None

    def on_enter(self) -> None:
        """Initialize game systems and load first level."""
        print("True Coral - Game Started")

        # Get managers
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        self._input_manager = self.container.get(InputManager)
        self._coroutine_manager = self.container.get(CoroutineManager)

        # Setup input bindings
        self._setup_input()

        # Initialize systems
        self._grid_system = GridSystem(self.entity_manager, self.event_dispatcher)
        self._move_system = BlockMoveSystem(self.entity_manager, self.event_dispatcher)
        self._input_system = InputSystem(self.event_dispatcher)

        # Initialize level loader
        self._level_loader = LevelLoader()
        self._level_loader.discover_levels()

        # Register events
        self.event_dispatcher.subscribe(LevelCompleteEvent, self._on_level_complete)
        self.event_dispatcher.subscribe(RestartLevelEvent, self._on_restart_level)
        self.event_dispatcher.subscribe(NextLevelEvent, self._on_next_level)

        # Load first level
        self._load_current_level()

        # Setup HUD
        self._setup_hud()

    def _setup_input(self) -> None:
        """Configure input bindings."""
        im = self._input_manager
        if not im:
            return

        # Movement actions
        im.register_action("move_up", ActionType.PRESS)
        im.register_action("move_down", ActionType.PRESS)
        im.register_action("move_left", ActionType.PRESS)
        im.register_action("move_right", ActionType.PRESS)
        im.register_action("undo", ActionType.PRESS)
        im.register_action("restart", ActionType.PRESS)
        im.register_action("back", ActionType.PRESS)

        im.bind_input(InputDevice.KEYBOARD, UP, "move_up")
        im.bind_input(InputDevice.KEYBOARD, DOWN, "move_down")
        im.bind_input(InputDevice.KEYBOARD, LEFT, "move_left")
        im.bind_input(InputDevice.KEYBOARD, RIGHT, "move_right")
        im.bind_input(InputDevice.KEYBOARD, Z, "undo")
        im.bind_input(InputDevice.KEYBOARD, R, "restart")
        im.bind_input(InputDevice.KEYBOARD, ESCAPE, "back")

        # Subscribe to action events
        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        """Handle input action events."""
        if self._show_complete_ui or not self._input_system:
            return

        # Only react to press events (value > 0)
        if event.value <= 0:
            return

        action = event.action_name

        if action == "move_up":
            self._input_system.handle_move((0, -1))
        elif action == "move_down":
            self._input_system.handle_move((0, 1))
        elif action == "move_left":
            self._input_system.handle_move((-1, 0))
        elif action == "move_right":
            self._input_system.handle_move((1, 0))
        elif action == "undo":
            self._input_system.handle_undo()
        elif action == "restart":
            self.event_dispatcher.dispatch(RestartLevelEvent())
        elif action == "back":
            self.container.get(SceneManager).pop_scene()

    def _setup_hud(self) -> None:
        """Create HUD elements."""
        ui_manager = self.container.get(UIManager)

        # Level name
        level_name = self._level_loader.get_level_name() if self._level_loader else ""
        label = Label(f"Level: {level_name}", position=Vector2(20, 20))
        ui_manager.add_element(label)

        # Instructions
        instructions = Label(
            "Arrows: Move | Z: Undo | R: Restart | ESC: Menu",
            position=Vector2(20, 560),
        )
        ui_manager.add_element(instructions)

    def _load_current_level(self) -> None:
        """Load the current level."""
        # Clear entities (except level_state which will be recreated)
        entity_ids = [e.id for e in self.entity_manager.get_all_entities()]
        for eid in entity_ids:
            self.entity_manager.remove_entity(eid)
        self._show_complete_ui = False

        if self._level_loader:
            self._level_loader.load_level(self.entity_manager)

        if self._grid_system:
            self._grid_system.rebuild_grid()

    def _on_level_complete(self, event: LevelCompleteEvent) -> None:
        """Handle level completion."""
        print(f"Level {event.level_index + 1} complete in {event.total_moves} moves!")
        self._show_complete_ui = True

        # Show completion UI after a short delay
        if self._coroutine_manager:
            self._coroutine_manager.start_coroutine(self._show_completion_sequence())

    def _show_completion_sequence(self):
        """Coroutine to show completion message."""
        yield wait_for_seconds(0.5)

        ui_manager = self.container.get(UIManager)

        # Completion overlay
        label = Label("LEVEL COMPLETE!", position=Vector2(280, 250))
        ui_manager.add_element(label)

        yield wait_for_seconds(1.0)

        # Check for next level
        if self._level_loader and self._level_loader.next_level():
            self.event_dispatcher.dispatch(NextLevelEvent())
        else:
            # All levels complete
            label2 = Label("ALL LEVELS COMPLETE!", position=Vector2(260, 290))
            ui_manager.add_element(label2)

    def _on_restart_level(self, event: RestartLevelEvent) -> None:
        """Handle level restart."""
        self._load_current_level()
        self._refresh_hud()

    def _on_next_level(self, event: NextLevelEvent) -> None:
        """Handle next level transition."""
        self._load_current_level()
        self._refresh_hud()

    def _refresh_hud(self) -> None:
        """Refresh HUD after level change."""
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()
        self._setup_hud()

    def on_exit(self) -> None:
        """Cleanup."""
        pass

    def update(self, dt: float) -> None:
        """Update game logic."""
        # Update input cooldowns
        if self._input_system:
            self._input_system.update(dt)

        # Update systems
        if self._move_system:
            self._move_system.update(dt)

        # Update coroutines
        if self._coroutine_manager:
            self._coroutine_manager.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the game."""
        world_renderer.clear(Color(25, 30, 35))

        # Render floor tiles first (lower z-order)
        for entity in self.entity_manager.get_entities_with(Transform, GridSprite):
            sprite = entity.get_component(GridSprite)
            if not sprite.is_floor:
                continue

            transform = entity.get_component(Transform)
            block = entity.get_component(Block)

            # Draw floor/goal as filled rect
            size = CELL_SIZE - 4
            rect = Rect(
                transform.position.x - size // 2,
                transform.position.y - size // 2,
                size,
                size,
            )

            # Goals have a special marker
            if block and block.block_type == BlockType.GOAL:
                # Draw goal marker (X pattern or different color)
                world_renderer.draw_rect(rect, sprite.color)
                # Draw inner marker
                inner_size = size // 3
                inner_rect = Rect(
                    transform.position.x - inner_size // 2,
                    transform.position.y - inner_size // 2,
                    inner_size,
                    inner_size,
                )
                world_renderer.draw_rect(inner_rect, Color(150, 220, 150))
            else:
                world_renderer.draw_rect(rect, sprite.color)

        # Render blocks (walls, crates, player)
        for entity in self.entity_manager.get_entities_with(Transform, GridSprite):
            sprite = entity.get_component(GridSprite)
            if sprite.is_floor:
                continue

            transform = entity.get_component(Transform)
            block = entity.get_component(Block)

            size = CELL_SIZE - 4
            if block and block.block_type == BlockType.PLAYER:
                size = CELL_SIZE - 8  # Slightly smaller player

            rect = Rect(
                transform.position.x - size // 2,
                transform.position.y - size // 2,
                size,
                size,
            )
            world_renderer.draw_rect(rect, sprite.color)

            # Draw highlights/shadows for depth
            if block and block.block_type in (BlockType.CRATE, BlockType.PLAYER):
                # Top highlight
                highlight_rect = Rect(
                    transform.position.x - size // 2 + 2,
                    transform.position.y - size // 2 + 2,
                    size - 4,
                    4,
                )
                highlight_color = Color(
                    min(255, sprite.color.r + 40),
                    min(255, sprite.color.g + 40),
                    min(255, sprite.color.b + 40),
                )
                world_renderer.draw_rect(highlight_rect, highlight_color)

        # Render move counter
        level_state = None
        for entity in self.entity_manager.get_entities_with(LevelState):
            level_state = entity.get_component(LevelState)
            break

        if level_state:
            # This would ideally use proper text rendering
            # For now we use the UI system
            pass
