"""Protocolo Bandeira - Game Scenes.

Menu, Arena, and Game Over scenes for the shooter game.
"""

import sys
import math
from typing import Optional

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
from pyguara.input.keys import W, A, S, D, UP, DOWN, LEFT, RIGHT, SPACE, ESCAPE
from pyguara.input.events import OnActionEvent
from pyguara.scripting.coroutines import CoroutineManager, wait_for_seconds

from games.protocolo_bandeira.components import (
    Weapon,
    Health,
    Movement,
    Score,
    ShooterSprite,
    Poolable,
    Bullet,
)
from games.protocolo_bandeira.systems import (
    PlayerControlSystem,
    BulletSystem,
    EnemyAISystem,
    CollisionSystem,
    WeaponSystem,
    ScoreSystem,
)
from games.protocolo_bandeira.pooling import BulletPool, EnemyPool
from games.protocolo_bandeira.wave_manager import WaveManager
from games.protocolo_bandeira.events import (
    PlayerDeathEvent,
    WaveCompleteEvent,
)


class MenuScene(Scene):
    """Main menu for Protocolo Bandeira."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the menu scene."""
        super().__init__("MenuScene", event_dispatcher)

    def on_enter(self) -> None:
        """Create menu UI."""
        print("Protocolo Bandeira - Menu")
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        # Title
        title = Label("PROTOCOLO BANDEIRA", position=Vector2(240, 100))
        ui_manager.add_element(title)

        # Subtitle
        subtitle = Label("Arena Shooter", position=Vector2(320, 140))
        ui_manager.add_element(subtitle)

        # Button container
        container = BoxContainer(
            position=Vector2(300, 240), size=Vector2(200, 200), spacing=15
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
        arena_scene = ArenaScene(self.event_dispatcher)
        scene_manager.register(arena_scene)
        scene_manager.push_scene("ArenaScene")

    def _on_quit_click(self, el) -> None:
        """Quit the game."""
        sys.exit(0)

    def on_exit(self) -> None:
        """Clean up scene resources."""
        pass

    def on_resume(self) -> None:
        """Recreate UI when returning from ArenaScene."""
        self.on_enter()

    def update(self, dt: float) -> None:
        """Update logic."""
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the scene."""
        world_renderer.clear(Color(20, 25, 35))


class ArenaScene(Scene):
    """Main gameplay arena for Protocolo Bandeira."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the arena scene."""
        super().__init__("ArenaScene", event_dispatcher)

        # Pools
        self._bullet_pool: Optional[BulletPool] = None
        self._enemy_pool: Optional[EnemyPool] = None

        # Systems
        self._player_control: Optional[PlayerControlSystem] = None
        self._bullet_system: Optional[BulletSystem] = None
        self._enemy_ai: Optional[EnemyAISystem] = None
        self._collision_system: Optional[CollisionSystem] = None
        self._weapon_system: Optional[WeaponSystem] = None
        self._score_system: Optional[ScoreSystem] = None

        # Wave manager
        self._wave_manager: Optional[WaveManager] = None

        # Game state
        self._player_id: Optional[str] = None
        self._input_manager: Optional[InputManager] = None
        self._coroutine_manager: Optional[CoroutineManager] = None
        self._is_game_over = False
        self._wave_transition = False

        # Input state tracking
        self._move_up_held = False
        self._move_down_held = False
        self._move_left_held = False
        self._move_right_held = False
        self._fire_held = False

    def on_enter(self) -> None:
        """Initialize game systems and start first wave."""
        print("Protocolo Bandeira - Arena Started")

        # Get managers
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        self._input_manager = self.container.get(InputManager)
        self._coroutine_manager = self.container.get(CoroutineManager)

        # Setup input
        self._setup_input()

        # Create pools
        self._bullet_pool = BulletPool(self.entity_manager, size=500)
        self._enemy_pool = EnemyPool(self.entity_manager, size=100)

        # Create systems
        self._player_control = PlayerControlSystem(self.entity_manager)
        self._bullet_system = BulletSystem(self.entity_manager, self._bullet_pool)
        self._enemy_ai = EnemyAISystem(
            self.entity_manager,
            self.event_dispatcher,
            self._enemy_pool,
            self._bullet_pool,
        )
        self._collision_system = CollisionSystem(
            self.entity_manager,
            self.event_dispatcher,
            self._bullet_pool,
            self._enemy_pool,
        )
        self._weapon_system = WeaponSystem(
            self.entity_manager,
            self.event_dispatcher,
            self._bullet_pool,
        )
        self._score_system = ScoreSystem(self.entity_manager, self.event_dispatcher)

        # Create wave manager
        self._wave_manager = WaveManager(self._enemy_pool, self.event_dispatcher)
        self._collision_system.set_wave_manager(self._wave_manager)

        # Create player
        self._create_player()

        # Register events
        self.event_dispatcher.subscribe(PlayerDeathEvent, self._on_player_death)
        self.event_dispatcher.subscribe(WaveCompleteEvent, self._on_wave_complete)

        # Setup HUD
        self._setup_hud()

        # Start first wave
        self._wave_manager.start_wave(1)

    def _setup_input(self) -> None:
        """Configure input bindings."""
        im = self._input_manager
        if not im:
            return

        # Movement (WASD + Arrows)
        im.register_action("move_up", ActionType.HOLD)
        im.register_action("move_down", ActionType.HOLD)
        im.register_action("move_left", ActionType.HOLD)
        im.register_action("move_right", ActionType.HOLD)
        im.register_action("fire", ActionType.HOLD)
        im.register_action("back", ActionType.PRESS)

        im.bind_input(InputDevice.KEYBOARD, W, "move_up")
        im.bind_input(InputDevice.KEYBOARD, UP, "move_up")
        im.bind_input(InputDevice.KEYBOARD, S, "move_down")
        im.bind_input(InputDevice.KEYBOARD, DOWN, "move_down")
        im.bind_input(InputDevice.KEYBOARD, A, "move_left")
        im.bind_input(InputDevice.KEYBOARD, LEFT, "move_left")
        im.bind_input(InputDevice.KEYBOARD, D, "move_right")
        im.bind_input(InputDevice.KEYBOARD, RIGHT, "move_right")
        im.bind_input(InputDevice.KEYBOARD, SPACE, "fire")
        im.bind_input(InputDevice.KEYBOARD, ESCAPE, "back")

        # Subscribe to action events
        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        """Handle input action events."""
        action = event.action_name
        is_pressed = event.value > 0

        # Track hold states
        if action == "move_up":
            self._move_up_held = is_pressed
        elif action == "move_down":
            self._move_down_held = is_pressed
        elif action == "move_left":
            self._move_left_held = is_pressed
        elif action == "move_right":
            self._move_right_held = is_pressed
        elif action == "fire":
            self._fire_held = is_pressed
        elif action == "back" and is_pressed:
            self.container.get(SceneManager).pop_scene()

    def _create_player(self) -> None:
        """Create the player entity."""
        player = self.entity_manager.create_entity("player")

        player.add_component(Transform(position=Vector2(400, 300)))
        player.add_component(Movement(speed=200.0))
        player.add_component(
            Weapon(
                fire_rate=0.15,
                bullet_speed=500.0,
                bullet_damage=1,
            )
        )
        player.add_component(Health(current=5, max_health=5))
        player.add_component(Score())
        player.add_component(
            ShooterSprite(color=Color(100, 200, 255), size=15.0, shape="triangle")
        )

        self._player_id = player.id

        # Link to systems
        self._player_control.set_player(player)
        self._collision_system.set_player(player)
        self._weapon_system.set_player(player)
        self._score_system.set_player(player)

    def _setup_hud(self) -> None:
        """Create HUD elements."""
        ui_manager = self.container.get(UIManager)

        instructions = Label(
            "WASD/Arrows: Move | SPACE: Shoot | ESC: Menu",
            position=Vector2(20, 560),
        )
        ui_manager.add_element(instructions)

    def _on_player_death(self, event: PlayerDeathEvent) -> None:
        """Handle player death."""
        self._is_game_over = True
        scene_manager = self.container.get(SceneManager)
        game_over_scene = GameOverScene(
            self.event_dispatcher,
            final_score=event.final_score,
            total_kills=event.total_kills,
        )
        scene_manager.register(game_over_scene)
        scene_manager.switch_to("GameOverScene")

    def _on_wave_complete(self, event: WaveCompleteEvent) -> None:
        """Handle wave completion."""
        self._wave_transition = True
        if self._coroutine_manager:
            self._coroutine_manager.start_coroutine(
                self._wave_transition_sequence(event.wave_number)
            )

    def _wave_transition_sequence(self, completed_wave: int):
        """Coroutine for wave transition."""
        # Brief pause
        yield wait_for_seconds(1.5)

        # Start next wave
        self._wave_transition = False
        if self._wave_manager:
            self._wave_manager.start_wave(completed_wave + 1)
            if self._score_system:
                self._score_system.update_wave(completed_wave + 1)

    def on_exit(self) -> None:
        """Cleanup."""
        pass

    def update(self, dt: float) -> None:
        """Update game logic."""
        if self._is_game_over:
            return

        # Update coroutines
        if self._coroutine_manager:
            self._coroutine_manager.update(dt)

        # Calculate move direction from held keys
        move_dir = Vector2.zero()
        aim_dir = Vector2.zero()

        if self._move_up_held:
            move_dir = move_dir + Vector2(0, -1)
        if self._move_down_held:
            move_dir = move_dir + Vector2(0, 1)
        if self._move_left_held:
            move_dir = move_dir + Vector2(-1, 0)
        if self._move_right_held:
            move_dir = move_dir + Vector2(1, 0)

        fire = self._fire_held

        # Normalize movement
        if move_dir.magnitude > 0:
            move_dir = move_dir.normalize()
            aim_dir = move_dir  # Aim in movement direction

        # Update systems
        if self._player_control:
            self._player_control.update(dt, move_dir, aim_dir, fire)

            # Get player position for AI
            player_pos = self._player_control.get_position()
            if player_pos and self._enemy_ai:
                self._enemy_ai.set_player_position(player_pos)

            # Handle firing
            if fire and player_pos and aim_dir.magnitude > 0:
                if self._weapon_system:
                    self._weapon_system.fire(player_pos, aim_dir)

        if self._bullet_system:
            self._bullet_system.update(dt)

        if self._enemy_ai:
            self._enemy_ai.update(dt)

        if self._collision_system:
            self._collision_system.update(dt)

        # Update wave manager
        if self._wave_manager and not self._wave_transition:
            player_pos = (
                self._player_control.get_position()
                if self._player_control
                else Vector2(400, 300)
            )
            self._wave_manager.update(dt, player_pos)

        # Update health timers
        if self._player_id:
            player = self.entity_manager.get_entity(self._player_id)
            if player:
                health = player.get_component(Health)
                if health and health.invincible_time > 0:
                    health.invincible_time -= dt

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the game."""
        world_renderer.clear(Color(15, 20, 30))

        # Draw arena border
        border_color = Color(50, 60, 80)
        world_renderer.draw_rect(Rect(0, 0, 800, 5), border_color)
        world_renderer.draw_rect(Rect(0, 595, 800, 5), border_color)
        world_renderer.draw_rect(Rect(0, 0, 5, 600), border_color)
        world_renderer.draw_rect(Rect(795, 0, 5, 600), border_color)

        # Draw bullets
        if self._bullet_pool:
            for entity in self._bullet_pool.get_active():
                bullet = entity.get_component(Bullet)
                transform = entity.get_component(Transform)
                sprite = entity.get_component(ShooterSprite)

                if not bullet or not bullet.active or not transform or not sprite:
                    continue

                self._draw_shape(world_renderer, transform.position, sprite)

        # Draw enemies
        if self._enemy_pool:
            for entity in self._enemy_pool.get_active():
                poolable = entity.get_component(Poolable)
                if not poolable or not poolable.is_active:
                    continue

                transform = entity.get_component(Transform)
                sprite = entity.get_component(ShooterSprite)

                if not transform or not sprite:
                    continue

                self._draw_shape(world_renderer, transform.position, sprite)

        # Draw player
        if self._player_id:
            player = self.entity_manager.get_entity(self._player_id)
            if player:
                transform = player.get_component(Transform)
                sprite = player.get_component(ShooterSprite)
                health = player.get_component(Health)
                movement = player.get_component(Movement)

                if transform and sprite:
                    # Flash when invincible
                    color = sprite.color
                    if health and health.invincible_time > 0:
                        if int(health.invincible_time * 10) % 2 == 0:
                            color = Color(255, 255, 255)

                    # Draw player with direction indicator
                    self._draw_shape(
                        world_renderer, transform.position, sprite, color=color
                    )

                    # Draw aim direction
                    if movement:
                        aim_end = transform.position + Vector2(
                            math.cos(movement.facing_angle) * 25,
                            math.sin(movement.facing_angle) * 25,
                        )
                        world_renderer.draw_line(
                            transform.position, aim_end, Color(200, 200, 200), width=2
                        )

        # Render HUD
        self._render_hud(world_renderer)

    def _draw_shape(
        self,
        renderer: IRenderer,
        pos: Vector2,
        sprite: ShooterSprite,
        color: Optional[Color] = None,
    ) -> None:
        """Draw a shape at position."""
        c = color or sprite.color
        size = sprite.size

        if sprite.shape == "square":
            rect = Rect(pos.x - size, pos.y - size, size * 2, size * 2)
            renderer.draw_rect(rect, c)
        else:  # circle or triangle - approximate with rect
            rect = Rect(pos.x - size, pos.y - size, size * 2, size * 2)
            renderer.draw_rect(rect, c)

    def _render_hud(self, renderer: IRenderer) -> None:
        """Render HUD elements."""
        if not self._player_id:
            return

        player = self.entity_manager.get_entity(self._player_id)
        if not player:
            return

        health = player.get_component(Health)
        score = player.get_component(Score)

        # Health bar
        if health:
            bar_width = 150
            bar_height = 15
            filled = (health.current / health.max_health) * bar_width

            # Background
            renderer.draw_rect(Rect(20, 20, bar_width, bar_height), Color(80, 80, 80))
            # Filled
            if filled > 0:
                renderer.draw_rect(
                    Rect(20, 20, int(filled), bar_height), Color(200, 50, 50)
                )

        # Score display (using rectangles since we don't have text)
        if score:
            # Wave indicator
            for i in range(min(score.wave, 10)):
                rect = Rect(700 - i * 12, 20, 10, 10)
                renderer.draw_rect(rect, Color(100, 200, 100))

            # Kill counter (simplified)
            kills_display = min(score.kills, 20)
            for i in range(kills_display):
                x = 20 + (i % 10) * 8
                y = 45 + (i // 10) * 8
                renderer.draw_rect(Rect(x, y, 6, 6), Color(255, 200, 50))


class GameOverScene(Scene):
    """Game over screen."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        final_score: int = 0,
        total_kills: int = 0,
    ):
        """Initialize the game over scene."""
        super().__init__("GameOverScene", event_dispatcher)
        self._final_score = final_score
        self._total_kills = total_kills

    def on_enter(self) -> None:
        """Create game over UI."""
        print(f"Game Over! Score: {self._final_score}, Kills: {self._total_kills}")
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        # Title
        title = Label("GAME OVER", position=Vector2(320, 150))
        ui_manager.add_element(title)

        # Stats
        score_label = Label(f"Score: {self._final_score}", position=Vector2(330, 220))
        ui_manager.add_element(score_label)

        kills_label = Label(f"Kills: {self._total_kills}", position=Vector2(340, 260))
        ui_manager.add_element(kills_label)

        # Buttons
        container = BoxContainer(
            position=Vector2(300, 320), size=Vector2(200, 150), spacing=15
        )

        btn_retry = Button("RETRY", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_retry.on_click = self._on_retry_click
        container.add_child(btn_retry)

        btn_menu = Button("MENU", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_menu.on_click = self._on_menu_click
        container.add_child(btn_menu)

        container.layout()
        ui_manager.add_element(container)

    def _on_retry_click(self, el) -> None:
        """Retry the game."""
        scene_manager = self.container.get(SceneManager)
        arena_scene = ArenaScene(self.event_dispatcher)
        scene_manager.register(arena_scene)
        scene_manager.switch_to("ArenaScene")

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
        world_renderer.clear(Color(30, 20, 20))
