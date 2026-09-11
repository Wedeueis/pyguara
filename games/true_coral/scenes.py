"""True Coral - Game Scenes.

Menu, arena, and game-over scenes for the snake game.
"""

import sys

from games.true_coral.components import Food, MoveState, Score
from games.true_coral.events import GameOverEvent, StarEffectEnded, StarEffectStarted
from games.true_coral.food_director import FoodDirector
from games.true_coral.systems import BASE_MOVE_RATE, MOVE_RATE_STAT, SnakeMovementSystem
from pyguara.common.modifiers import ModifiableValue
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import DOWN, ESCAPE, LEFT, RIGHT, UP
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.action_combat import Health, HealthSystem
from pyguara.kits.effects import EffectContainer, EffectSystem
from pyguara.kits.stats import StatBlock
from pyguara.kits.trail import Trail, contains, reset
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.components.button import Button
from pyguara.ui.components.text import Label
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager

GRID_WIDTH = 20
GRID_HEIGHT = 15
CELL_SIZE = 32
GRID_OFFSET_X = (800 - GRID_WIDTH * CELL_SIZE) // 2
GRID_OFFSET_Y = (600 - GRID_HEIGHT * CELL_SIZE) // 2

STARTING_LIVES = 3.0
SNAKE_START_LENGTH = 3

# Coral snake banding: two segments of each colour before cycling, matching
# the reference art's red/black/cream rings.
_BAND_COLORS = [Color(230, 60, 30), Color(20, 20, 25), Color(245, 235, 210)]
_HEAD_COLOR = Color(250, 210, 60)

_FOOD_COLORS = {
    "larva": Color(240, 235, 210),
    "beetle": Color(210, 40, 30),
    "star": Color(255, 230, 90),
}


def grid_to_world(cell: tuple[int, int]) -> Vector2:
    """Convert a grid cell to the centre of its screen-space square."""
    x, y = cell
    return Vector2(
        GRID_OFFSET_X + x * CELL_SIZE + CELL_SIZE / 2,
        GRID_OFFSET_Y + y * CELL_SIZE + CELL_SIZE / 2,
    )


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

        title = Label("TRUE CORAL", position=Vector2(300, 100))
        ui_manager.add_element(title)

        subtitle = Label("cocar the coral snake", position=Vector2(300, 140))
        ui_manager.add_element(subtitle)

        container = BoxContainer(
            position=Vector2(300, 240), size=Vector2(200, 200), spacing=15
        )

        btn_start = Button("START GAME", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_start.on_click = self._on_start_click
        container.add_child(btn_start)

        btn_quit = Button("QUIT", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_quit.on_click = self._on_quit_click
        container.add_child(btn_quit)

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
        """Clean up scene resources."""
        pass

    def on_resume(self) -> None:
        """Recreate UI when returning from GameScene."""
        self.on_enter()

    def update(self, dt: float) -> None:
        """Update logic."""
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the scene."""
        world_renderer.clear(Color(15, 20, 18))


class GameScene(Scene):
    """Main gameplay arena for True Coral."""

    RAIN_SPAWN_RATE = 40.0  # New drops per second while the star is active
    RAIN_FALL_SPEED = 260.0

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the game scene."""
        super().__init__("GameScene", event_dispatcher)
        self._movement_system: SnakeMovementSystem | None = None
        self._health_system: HealthSystem | None = None
        self._effect_system: EffectSystem | None = None
        self._food_director: FoodDirector | None = None
        self._input_manager: InputManager | None = None
        self._snake: Entity | None = None
        self._is_game_over = False
        self._rain_active = False
        self._rain_drops: list[list[float]] = []  # [x, y] pairs
        self._rng = RandomStream()

    def on_enter(self) -> None:
        """Initialize game systems and the snake."""
        print("True Coral - Game Started")

        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        self._input_manager = self.container.get(InputManager)
        self._setup_input()

        self._snake = self._create_snake()
        trail = self._snake.get_component(Trail)

        self._food_director = FoodDirector(
            self.entity_manager,
            GRID_WIDTH,
            GRID_HEIGHT,
            is_cell_free=lambda cell: not contains(trail, cell),
            rng=self._rng,
        )

        self._movement_system = SnakeMovementSystem(
            self.entity_manager,
            self.event_dispatcher,
            self._food_director,
            GRID_WIDTH,
            GRID_HEIGHT,
        )
        self._movement_system.set_snake(self._snake)

        self._health_system = HealthSystem(self.entity_manager)
        self._effect_system = EffectSystem(self.entity_manager, self.event_dispatcher)

        self.event_dispatcher.subscribe(GameOverEvent, self._on_game_over)
        self.event_dispatcher.subscribe(StarEffectStarted, self._on_star_started)
        self.event_dispatcher.subscribe(StarEffectEnded, self._on_star_ended)

        self._setup_hud()

    def _create_snake(self) -> Entity:
        """Create the snake entity at the arena's centre."""
        entity = self.entity_manager.create_entity("snake")
        cx, cy = GRID_WIDTH // 2, GRID_HEIGHT // 2

        entity.add_component(Trail())
        reset(
            entity.get_component(Trail),
            [(cx - i, cy) for i in range(SNAKE_START_LENGTH)],
        )
        entity.add_component(MoveState(direction=(1, 0)))
        entity.add_component(Health(current=STARTING_LIVES, max_health=STARTING_LIVES))
        entity.add_component(
            StatBlock(stats={MOVE_RATE_STAT: ModifiableValue(BASE_MOVE_RATE)})
        )
        entity.add_component(EffectContainer())
        entity.add_component(Score())

        return entity

    def _setup_input(self) -> None:
        """Configure input bindings."""
        im = self._input_manager
        if not im:
            return

        im.register_action("move_up", ActionType.PRESS)
        im.register_action("move_down", ActionType.PRESS)
        im.register_action("move_left", ActionType.PRESS)
        im.register_action("move_right", ActionType.PRESS)
        im.register_action("back", ActionType.PRESS)

        im.bind_input(InputDevice.KEYBOARD, UP, "move_up")
        im.bind_input(InputDevice.KEYBOARD, DOWN, "move_down")
        im.bind_input(InputDevice.KEYBOARD, LEFT, "move_left")
        im.bind_input(InputDevice.KEYBOARD, RIGHT, "move_right")
        im.bind_input(InputDevice.KEYBOARD, ESCAPE, "back")

        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        """Handle input action events."""
        if event.value <= 0:
            return

        action = event.action_name
        if action == "back":
            self.container.get(SceneManager).pop_scene()
            return

        if self._is_game_over or not self._movement_system:
            return

        direction = {
            "move_up": (0, -1),
            "move_down": (0, 1),
            "move_left": (-1, 0),
            "move_right": (1, 0),
        }.get(action)
        if direction is not None:
            self._movement_system.queue_direction(direction)

    def _setup_hud(self) -> None:
        """Create HUD elements."""
        ui_manager = self.container.get(UIManager)

        instructions = Label(
            "Arrows: Move | ESC: Menu",
            position=Vector2(20, 570),
        )
        ui_manager.add_element(instructions)

    def _on_star_started(self, event: StarEffectStarted) -> None:
        """Start the rain overlay."""
        self._rain_active = True

    def _on_star_ended(self, event: StarEffectEnded) -> None:
        """Stop spawning new rain -- existing drops finish falling on their own."""
        self._rain_active = False

    def _on_game_over(self, event: GameOverEvent) -> None:
        """Handle the snake running out of lives."""
        self._is_game_over = True
        scene_manager = self.container.get(SceneManager)
        game_over_scene = GameOverScene(
            self.event_dispatcher, final_score=event.final_score
        )
        scene_manager.register(game_over_scene)
        scene_manager.switch_to("GameOverScene")

    def on_exit(self) -> None:
        """Cleanup."""
        pass

    def update(self, dt: float) -> None:
        """Update game logic."""
        if self._is_game_over:
            return

        if self._movement_system:
            self._movement_system.update(dt)

        if self._food_director:
            self._food_director.update(dt)

        if self._effect_system:
            self._effect_system.update(dt)

        if self._health_system:
            self._health_system.update(dt)

        self._update_rain(dt)

    def _update_rain(self, dt: float) -> None:
        """Advance falling rain drops, spawning new ones while the star is active."""
        if self._rain_active:
            to_spawn = self.RAIN_SPAWN_RATE * dt
            while to_spawn >= 1.0:
                to_spawn -= 1.0
                x = self._rng.uniform(
                    GRID_OFFSET_X, GRID_OFFSET_X + GRID_WIDTH * CELL_SIZE
                )
                self._rain_drops.append([x, float(GRID_OFFSET_Y)])

        for drop in self._rain_drops:
            drop[1] += self.RAIN_FALL_SPEED * dt

        bottom = GRID_OFFSET_Y + GRID_HEIGHT * CELL_SIZE
        self._rain_drops = [d for d in self._rain_drops if d[1] < bottom]

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the game."""
        world_renderer.clear(Color(10, 14, 12))

        arena = Rect(
            GRID_OFFSET_X,
            GRID_OFFSET_Y,
            GRID_WIDTH * CELL_SIZE,
            GRID_HEIGHT * CELL_SIZE,
        )
        world_renderer.draw_rect(arena, Color(20, 28, 24))

        self._render_food(world_renderer)
        self._render_snake(world_renderer)
        self._render_rain(world_renderer)
        self._render_hud(world_renderer)

    def _render_food(self, world_renderer: IRenderer) -> None:
        for entity in self.entity_manager.get_entities_with(Food):
            food = entity.get_component(Food)
            center = grid_to_world(food.cell)
            color = _FOOD_COLORS.get(food.food_type, Color(255, 255, 255))
            radius = CELL_SIZE * (0.3 if food.food_type == "larva" else 0.38)
            world_renderer.draw_circle(center, radius, color)

            if food.food_type == "star":
                arm = CELL_SIZE * 0.5
                world_renderer.draw_line(
                    center - Vector2(arm, 0), center + Vector2(arm, 0), color, width=2
                )
                world_renderer.draw_line(
                    center - Vector2(0, arm), center + Vector2(0, arm), color, width=2
                )

    def _render_snake(self, world_renderer: IRenderer) -> None:
        if not self._snake:
            return

        trail = self._snake.get_component(Trail)
        health = self._snake.get_component(Health)
        flashing = health.is_invincible and int(health.invincible_timer * 8) % 2 == 0

        for index, cell in enumerate(trail.positions):
            center = grid_to_world(cell)
            if index == 0:
                color = Color(255, 255, 255) if flashing else _HEAD_COLOR
                radius = CELL_SIZE * 0.42
            else:
                color = _BAND_COLORS[(index // 2) % len(_BAND_COLORS)]
                if flashing:
                    color = Color(255, 255, 255)
                radius = CELL_SIZE * 0.38
            world_renderer.draw_circle(center, radius, color)

        if len(trail.positions) > 0:
            head_center = grid_to_world(trail.head)
            dx, dy = self._snake.get_component(MoveState).direction
            eye_offset = Vector2(dy, -dx) * (CELL_SIZE * 0.18)
            forward = Vector2(dx, dy) * (CELL_SIZE * 0.15)
            for sign in (1, -1):
                eye_pos = head_center + forward + eye_offset * sign
                world_renderer.draw_circle(eye_pos, CELL_SIZE * 0.06, Color(10, 10, 10))

    def _render_rain(self, world_renderer: IRenderer) -> None:
        color = Color(150, 220, 255, 180)
        for x, y in self._rain_drops:
            world_renderer.draw_line(Vector2(x, y), Vector2(x, y + 10), color, width=2)

    def _render_hud(self, world_renderer: IRenderer) -> None:
        if not self._snake:
            return

        score = self._snake.get_component(Score)
        health = self._snake.get_component(Health)

        world_renderer.draw_text(
            f"Score: {score.value}", Vector2(20, 20), Color(255, 255, 255)
        )
        world_renderer.draw_text(
            f"Lives: {int(health.current)}", Vector2(20, 44), Color(255, 120, 110)
        )
        if health.is_invincible:
            world_renderer.draw_text("IMMORTAL", Vector2(700, 20), Color(255, 230, 90))


class GameOverScene(Scene):
    """Game over screen."""

    def __init__(self, event_dispatcher: EventDispatcher, final_score: int = 0):
        """Initialize the game over scene."""
        super().__init__("GameOverScene", event_dispatcher)
        self._final_score = final_score

    def on_enter(self) -> None:
        """Create game over UI."""
        print(f"Game Over! Score: {self._final_score}")
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        title = Label("GAME OVER", position=Vector2(320, 150))
        ui_manager.add_element(title)

        score_label = Label(f"Score: {self._final_score}", position=Vector2(330, 220))
        ui_manager.add_element(score_label)

        container = BoxContainer(
            position=Vector2(300, 300), size=Vector2(200, 150), spacing=15
        )

        btn_retry = Button("RETRY", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_retry.on_click = self._on_retry_click
        container.add_child(btn_retry)

        btn_menu = Button("MENU", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_menu.on_click = self._on_menu_click
        container.add_child(btn_menu)

        ui_manager.add_element(container)

    def _on_retry_click(self, el) -> None:
        """Retry the game."""
        scene_manager = self.container.get(SceneManager)
        game_scene = GameScene(self.event_dispatcher)
        scene_manager.register(game_scene)
        scene_manager.switch_to("GameScene")

    def _on_menu_click(self, el) -> None:
        """Return to menu."""
        scene_manager = self.container.get(SceneManager)
        scene_manager.pop_scene()

    def on_exit(self) -> None:
        """Cleanup."""
        pass

    def update(self, dt: float) -> None:
        """Update logic."""
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the scene."""
        world_renderer.clear(Color(20, 25, 35))
