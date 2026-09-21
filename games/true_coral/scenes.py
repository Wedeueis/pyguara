"""True Coral - Game Scenes.

Menu, arena, and game-over screens, all three sharing one `Atmosphere`:
the same rainy forest floor, lit the same way, with the same storm running
over it.

The arena scene's `render()` is the one place where the ModernGL backend's
draw ordering shows through. Shape primitives queue up and flush together
at `end_frame()`, while `draw_text` draws the moment it is called -- so
text submitted before a shape still ends up underneath it. Everything
shaped is therefore drawn first, flushed once, and only then is the HUD's
text written over the top.
"""

from __future__ import annotations

import math

from games.true_coral import render
from games.true_coral.atmosphere import Atmosphere
from games.true_coral.bootstrap import WINDOW_HEIGHT, WINDOW_WIDTH
from games.true_coral.components import Food, MoveState, Score
from games.true_coral.events import (
    FoodEatenEvent,
    GameOverEvent,
    SnakeDiedEvent,
    StarEffectEnded,
    StarEffectStarted,
)
from games.true_coral.food_director import FoodDirector
from games.true_coral.systems import (
    BASE_MOVE_RATE,
    MOVE_RATE_STAT,
    SnakeMovementSystem,
    StarEffect,
)
from pyguara.common.grid import Cell
from pyguara.common.modifiers import ModifiableValue
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.floating_text import FloatingText
from pyguara.graphics.components.screen_flash import ScreenFlash
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.window import Window
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import DOWN, ESCAPE, LEFT, RIGHT, UP
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.action_combat import Health, HealthSystem
from pyguara.kits.effects import EffectContainer, EffectSystem
from pyguara.kits.stats import StatBlock, get_stat
from pyguara.kits.trail import Trail, contains, reset
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.components.button import Button
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager

GRID_WIDTH = 20
GRID_HEIGHT = 15
CELL_SIZE = render.CELL_SIZE
GRID_OFFSET_X = (WINDOW_WIDTH - GRID_WIDTH * CELL_SIZE) // 2
GRID_OFFSET_Y = (WINDOW_HEIGHT - GRID_HEIGHT * CELL_SIZE) // 2

ARENA = Rect(
    GRID_OFFSET_X, GRID_OFFSET_Y, GRID_WIDTH * CELL_SIZE, GRID_HEIGHT * CELL_SIZE
)

STARTING_LIVES = 3.0
SNAKE_START_LENGTH = 5

_FOOD_POINTS_COLOR = {
    "larva": render.CREAM,
    "beetle": Color(255, 120, 90),
    "star": render.HEAD_GOLD,
}


def grid_to_world(cell: Cell) -> Vector2:
    """Convert a grid cell to the centre of its screen-space square."""
    x, y = cell
    return Vector2(
        GRID_OFFSET_X + x * CELL_SIZE + CELL_SIZE / 2,
        GRID_OFFSET_Y + y * CELL_SIZE + CELL_SIZE / 2,
    )


class _AtmosphericScene(Scene):
    """A scene that owns an `Atmosphere` and knows when it is on screen.

    `push_scene` leaves the scene underneath in the stack, and the scene
    manager both updates and renders every stacked scene before the
    current one. That was harmless when the menu drew a flat colour and
    did nothing on update; now each scene owns a whole forest and a
    weather system, and a paused one would paint its backdrop over the
    scene above it while its own storm director fought for the shared
    `StormEffect`'s uniforms. A paused scene therefore neither draws nor
    updates.
    """

    def __init__(self, name: str, event_dispatcher: EventDispatcher) -> None:
        """Initialize the scene in its visible state."""
        super().__init__(name, event_dispatcher)
        self.atmosphere: Atmosphere | None = None
        self._visible = True

    def build_atmosphere(self, seed: int | None = None) -> Atmosphere:
        """Create this scene's environment. Call from `on_enter()`.

        Args:
            seed: Seed for weather and scatter, or None for an unseeded run.

        Returns:
            The new atmosphere, also stored on the scene.
        """
        self.atmosphere = Atmosphere(
            self.container,
            self.entity_manager,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            arena=ARENA,
            seed=seed,
        )
        return self.atmosphere

    def on_pause(self) -> None:
        """Stop drawing while another scene is pushed on top."""
        self._visible = False

    def on_resume(self) -> None:
        """Resume drawing when the scene above is popped."""
        self._visible = True

    @property
    def is_visible(self) -> bool:
        """Whether this scene should draw at all this frame."""
        return self._visible


class MenuScene(_AtmosphericScene):
    """Main menu: the title, over a snake coiling in the rain."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the menu scene."""
        super().__init__("MenuScene", event_dispatcher)
        self._segments: list[Vector2] = []

    def on_enter(self) -> None:
        """Create menu UI and the environment behind it."""
        print("True Coral - Menu")
        self.build_atmosphere()

        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        container = BoxContainer(
            position=Vector2(WINDOW_WIDTH / 2 - 110, 430),
            size=Vector2(220, 200),
            spacing=16,
        )

        btn_start = Button("JOGAR", position=Vector2(0, 0), size=Vector2(220, 52))
        btn_start.on_click = self._on_start_click
        container.add_child(btn_start)

        btn_quit = Button("SAIR", position=Vector2(0, 0), size=Vector2(220, 52))
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
        """Quit the game.

        Closes the window rather than `sys.exit()`, so `Application.run()`
        falls out of its loop and runs its normal shutdown/teardown.
        """
        self.container.get(Window).close()

    def on_exit(self) -> None:
        """Clean up scene resources."""
        pass

    def on_resume(self) -> None:
        """Recreate UI when returning from GameScene."""
        super().on_resume()
        self.on_enter()

    def update(self, dt: float) -> None:
        """Advance the weather behind the menu."""
        if self.atmosphere is None or not self.is_visible:
            return
        # Lights are set before the atmosphere updates, because that is
        # what collects them into the light map for this frame; setting
        # them at render time leaves the lighting a frame behind the
        # geometry it is supposed to be lighting.
        self._segments = self._coil(self.atmosphere.time)
        self.atmosphere.set_dynamic_lights(
            [
                # The title is drawn into the world buffer like everything
                # else, so it is subject to the same light map; unlit it
                # reads as grey text on a black screen.
                (Vector2(WINDOW_WIDTH / 2, 172.0), render.AMBER, 320.0, 0.45),
                (self._segments[0], render.HEAD_GOLD, 110.0, 0.6),
            ]
            + [
                (self._segments[i], render.CORAL_RED, 70.0, 0.3)
                for i in range(3, len(self._segments), 5)
            ]
        )
        self.atmosphere.update(dt, self.camera)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the coiling snake, the title, and the storm over both."""
        if not self.is_visible or self.atmosphere is None or self.camera is None:
            return

        atmosphere = self.atmosphere
        atmosphere.draw_ground(world_renderer)
        atmosphere.draw_litter(world_renderer)

        render.draw_snake(
            world_renderer,
            self._segments,
            time=atmosphere.time,
            offset=atmosphere.offset,
            flashing=False,
            star=0.0,
            tongue=math.fmod(atmosphere.time, 2.1) < 0.2,
        )
        atmosphere.sparks.render(world_renderer, atmosphere.offset)
        world_renderer.end_frame()

        world_renderer.draw_text(
            "TRUE CORAL", Vector2(WINDOW_WIDTH / 2 - 168, 132), render.CREAM, size=58
        )
        world_renderer.draw_text(
            "cocar  the  coral  snake",
            Vector2(WINDOW_WIDTH / 2 - 104, 200),
            render.TEAL,
            size=18,
        )

        atmosphere.run_pipeline(self.camera)

    # Segment spacing for the menu snake. Well under a body's diameter,
    # because the body is drawn as capsules between consecutive centres
    # and a sparse curve reads as a pile of sticks rather than a snake.
    COIL_SPACING = 21.0
    COIL_LENGTH = 26

    def _coil(self, time: float) -> list[Vector2]:
        """Return a snake slithering in place across the title screen.

        A travelling sine along a straight spine, head first. Tried as a
        Lissajous figure first, which looks right on paper and wrong on
        screen: it crosses itself and its spacing swings wildly, so the
        body kept breaking apart into separate pieces.
        """
        centre = Vector2(WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 40)
        head_x = centre.x + (self.COIL_LENGTH * self.COIL_SPACING) / 2
        return [
            Vector2(
                head_x - index * self.COIL_SPACING,
                centre.y + math.sin(index * 0.42 - time * 2.6) * 46.0,
            )
            for index in range(self.COIL_LENGTH)
        ]


class GameScene(_AtmosphericScene):
    """Main gameplay arena for True Coral."""

    # How long the tongue is out, and how often it flicks.
    TONGUE_PERIOD = 1.7
    TONGUE_DURATION = 0.18

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
        self._star_timer = 0.0
        self._rng = RandomStream()
        self._popups = FloatingText()
        self._flash = ScreenFlash()
        self._foods: list[tuple[str, Vector2, float]] = []
        self._segments: list[Vector2] = []

    def on_enter(self) -> None:
        """Initialize game systems, the environment, and the snake."""
        print("True Coral - Game Started")

        self.build_atmosphere()

        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

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

        self.event_dispatcher.subscribe(FoodEatenEvent, self._on_food_eaten)
        self.event_dispatcher.subscribe(SnakeDiedEvent, self._on_snake_died)
        self.event_dispatcher.subscribe(GameOverEvent, self._on_game_over)
        self.event_dispatcher.subscribe(StarEffectStarted, self._on_star_started)
        self.event_dispatcher.subscribe(StarEffectEnded, self._on_star_ended)

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

    # ---- feedback --------------------------------------------------

    def _on_food_eaten(self, event: FoodEatenEvent) -> None:
        """Burst, pop a score number, and nudge the screen."""
        if self.atmosphere is None:
            return

        centre = grid_to_world(event.cell)
        color = _FOOD_POINTS_COLOR.get(event.food_type, render.CREAM)
        self.atmosphere.sparks.burst(
            centre,
            color,
            count=18 if event.food_type != "star" else 40,
            speed=190.0,
            life=0.5,
            radius=3.0,
            streak=event.food_type == "star",
        )
        self._popups.spawn(
            f"+{event.points}", centre - Vector2(12, 10), color, size=20, life=0.8
        )
        self.atmosphere.shaker.add(2.5 if event.food_type != "star" else 7.0, 0.18)

    def _on_snake_died(self, event: SnakeDiedEvent) -> None:
        """Throw the body apart and slam the screen red."""
        if self.atmosphere is None or self._snake is None:
            return

        trail = self._snake.get_component(Trail)
        # `positions` is a deque, which does not slice.
        for cell in list(trail.positions)[:8]:
            self.atmosphere.sparks.burst(
                grid_to_world(cell),
                render.CORAL_RED,
                count=10,
                speed=240.0,
                life=0.7,
                radius=3.5,
            )
        self.atmosphere.shaker.add(14.0, 0.45)
        self._flash.trigger(Color(180, 30, 20, 90), duration=0.28)

    def _on_star_started(self, event: StarEffectStarted) -> None:
        """Open the sky: the star's effect is what brings the downpour."""
        self._star_timer = StarEffect.DURATION
        if self.atmosphere is not None:
            self.atmosphere.storm.set_storming(True)

    def _on_star_ended(self, event: StarEffectEnded) -> None:
        """Back to a drizzle."""
        self._star_timer = 0.0
        if self.atmosphere is not None:
            self.atmosphere.storm.set_storming(False)

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
        """Drop this scene's subscriptions."""
        for event_type, handler in (
            (OnActionEvent, self._on_action),
            (FoodEatenEvent, self._on_food_eaten),
            (SnakeDiedEvent, self._on_snake_died),
            (GameOverEvent, self._on_game_over),
            (StarEffectStarted, self._on_star_started),
            (StarEffectEnded, self._on_star_ended),
        ):
            self.event_dispatcher.unsubscribe(event_type, handler)

    def update(self, dt: float) -> None:
        """Update game logic and everything that reacts to it."""
        self._popups.update(dt)
        self._flash.update(dt)

        if not self._is_game_over:
            if self._movement_system:
                self._movement_system.update(dt)

            if self._food_director:
                self._food_director.update(dt)

            if self._effect_system:
                self._effect_system.update(dt)

            if self._health_system:
                self._health_system.update(dt)

            self._star_timer = max(0.0, self._star_timer - dt)

        # Snapshot what the frame will draw, and light it, before the
        # atmosphere collects the light map. Doing this at render time
        # left every moving light one frame behind its subject.
        self._foods = self._food_snapshot()
        self._segments = self._segment_positions()
        if self.atmosphere is not None:
            self.atmosphere.set_dynamic_lights(
                self._lights(self._foods, self._segments, self._star_strength())
            )
            self.atmosphere.update(dt, self.camera)

    # ---- drawing ---------------------------------------------------

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the arena, then drive the lighting half of the pipeline."""
        if not self.is_visible or self.atmosphere is None or self.camera is None:
            return

        atmosphere = self.atmosphere
        offset = atmosphere.offset
        star = self._star_strength()

        atmosphere.draw_ground(world_renderer)
        render.draw_arena(
            world_renderer,
            ARENA,
            time=atmosphere.time,
            offset=offset,
            storm=atmosphere.storm.rain,
        )
        atmosphere.draw_litter(world_renderer)
        render.draw_food(
            world_renderer, self._foods, time=atmosphere.time, offset=offset
        )
        render.draw_snake(
            world_renderer,
            self._segments,
            time=atmosphere.time,
            offset=offset,
            flashing=self._is_flashing(),
            star=star,
            tongue=math.fmod(atmosphere.time, self.TONGUE_PERIOD)
            < self.TONGUE_DURATION,
        )
        atmosphere.sparks.render(world_renderer, offset)
        render.draw_hud_panels(
            world_renderer,
            arena=ARENA,
            lives=self._lives(),
            star_fraction=self._star_timer / StarEffect.DURATION,
            width=WINDOW_WIDTH,
        )
        # The damage flash is a full-screen rect, and rects flush before
        # circles and lines -- so it needs a batch of its own to land on
        # top of the arena rather than under it.
        world_renderer.end_frame()
        self._flash.render(world_renderer, Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))

        # Flush again, so the HUD's text -- which draws immediately -- lands
        # over every shape rather than under it.
        world_renderer.end_frame()

        render.draw_hud_text(
            world_renderer,
            arena=ARENA,
            score=self._score(),
            lives=self._lives(),
            star_fraction=self._star_timer / StarEffect.DURATION,
            storming=atmosphere.storm.is_storming,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
        )
        self._popups.render(world_renderer, self.camera)

        atmosphere.run_pipeline(self.camera)

    def _food_snapshot(self) -> list[tuple[str, Vector2, float]]:
        """Return `(type, centre, phase)` for every piece of prey on the board."""
        foods = []
        for entity in self.entity_manager.get_entities_with(Food):
            food = entity.get_component(Food)
            # Phase from the cell, so each item bobs on its own beat and
            # keeps that beat for as long as it sits there.
            phase = (food.cell[0] * 1.7 + food.cell[1] * 2.9) % math.tau
            foods.append((food.food_type, grid_to_world(food.cell), phase))
        return foods

    def _segment_positions(self) -> list[Vector2]:
        """Return the snake's screen-space centres, head first, interpolated.

        The snake steps four times a second. Drawn on the grid it ticks
        like a spreadsheet, so each segment is drawn part-way into the
        cell ahead of it, by how far the movement clock has run -- the
        interpolation the GDD asks for in 4.2, on the snake's own clock
        rather than the fixed-step one.
        """
        if self._snake is None:
            return []

        trail = self._snake.get_component(Trail)
        move_state = self._snake.get_component(MoveState)
        stats = self._snake.get_component(StatBlock)

        rate = get_stat(stats, MOVE_RATE_STAT, default=BASE_MOVE_RATE)
        alpha = min(1.0, max(0.0, move_state.move_timer * rate))

        cells = trail.positions
        positions = []
        for index, cell in enumerate(cells):
            previous = cells[index + 1] if index + 1 < len(cells) else cell
            target = grid_to_world(cell)
            if abs(previous[0] - cell[0]) + abs(previous[1] - cell[1]) > 1:
                # Not adjacent: the body was teleported (a respawn, or the
                # tail catching up after growth). Sliding between those two
                # cells would drag a segment across the board.
                positions.append(target)
            else:
                positions.append(grid_to_world(previous).lerp(target, alpha))
        return positions

    def _lights(
        self,
        foods: list[tuple[str, Vector2, float]],
        segments: list[Vector2],
        star: float,
    ) -> list[tuple[Vector2, Color, float, float]]:
        """Return this frame's moving lights: the prey and the snake.

        The body is lit every fourth segment rather than every one. A
        light per segment is both redundant -- their radii overlap several
        times over -- and the fastest way to spend the pool on a long
        snake.
        """
        lights: list[tuple[Vector2, Color, float, float]] = []
        for food_type, centre, _ in foods:
            color = render.FOOD_COLORS.get(food_type, render.CREAM)
            radius = 72.0 if food_type == "star" else 56.0
            lights.append((centre, color, radius, 0.5))

        if segments:
            lights.append(
                (segments[0], render.HEAD_GOLD, 88.0 + 30.0 * star, 0.55 + 0.35 * star)
            )
            for index in range(4, len(segments), 4):
                lights.append((segments[index], render.CORAL_RED, 46.0, 0.22))
        return lights

    def _is_flashing(self) -> bool:
        """Whether the snake is mid-blink in its post-hit invincibility."""
        if self._snake is None:
            return False
        health = self._snake.get_component(Health)
        # Only the respawn blink flashes; the star grants invincibility
        # too, and blinking through all six seconds of it is unreadable.
        if self._star_timer > 0.0:
            return False
        return health.is_invincible and int(health.invincible_timer * 8) % 2 == 0

    def _star_strength(self) -> float:
        """Return the star effect's remaining strength, 0..1."""
        return min(1.0, self._star_timer / StarEffect.DURATION)

    def _score(self) -> int:
        """Return the current score."""
        return 0 if self._snake is None else self._snake.get_component(Score).value

    def _lives(self) -> int:
        """Return the remaining lives."""
        if self._snake is None:
            return 0
        return int(self._snake.get_component(Health).current)


class GameOverScene(_AtmosphericScene):
    """Game over screen, in the same rain the run ended in."""

    def __init__(self, event_dispatcher: EventDispatcher, final_score: int = 0):
        """Initialize the game over scene."""
        super().__init__("GameOverScene", event_dispatcher)
        self._final_score = final_score

    def on_enter(self) -> None:
        """Create game over UI."""
        print(f"Game Over! Score: {self._final_score}")
        self.build_atmosphere()

        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        container = BoxContainer(
            position=Vector2(WINDOW_WIDTH / 2 - 110, 420),
            size=Vector2(220, 150),
            spacing=16,
        )

        btn_retry = Button("DE NOVO", position=Vector2(0, 0), size=Vector2(220, 52))
        btn_retry.on_click = self._on_retry_click
        container.add_child(btn_retry)

        btn_menu = Button("MENU", position=Vector2(0, 0), size=Vector2(220, 52))
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
        """Advance the weather behind the results."""
        if self.atmosphere is not None and self.is_visible:
            # One light on the result text, for the same reason the menu
            # lights its title: it is drawn into the world buffer and gets
            # multiplied by the light map like everything else.
            self.atmosphere.set_dynamic_lights(
                [(Vector2(WINDOW_WIDTH / 2, 270.0), render.AMBER, 300.0, 0.4)]
            )
            self.atmosphere.update(dt, self.camera)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the empty arena and the final score."""
        if not self.is_visible or self.atmosphere is None or self.camera is None:
            return

        atmosphere = self.atmosphere
        atmosphere.draw_ground(world_renderer)
        render.draw_arena(
            world_renderer,
            ARENA,
            time=atmosphere.time,
            offset=atmosphere.offset,
            storm=atmosphere.storm.rain,
        )
        atmosphere.draw_litter(world_renderer)
        atmosphere.sparks.render(world_renderer, atmosphere.offset)
        world_renderer.end_frame()

        world_renderer.draw_text(
            "FIM DE JOGO",
            Vector2(WINDOW_WIDTH / 2 - 176, 220),
            render.CORAL_RED,
            size=54,
        )
        world_renderer.draw_text(
            f"PONTOS  {self._final_score:06d}",
            Vector2(WINDOW_WIDTH / 2 - 108, 300),
            render.CREAM,
            size=24,
        )

        atmosphere.run_pipeline(self.camera)
