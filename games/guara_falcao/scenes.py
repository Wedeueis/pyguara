"""Guará & Falcão - Game Scenes.

Title and gameplay scenes for the platformer game.
"""

import sys
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
from pyguara.input.keys import UP, LEFT, RIGHT, SPACE, ESCAPE, R
from pyguara.input.events import OnActionEvent
from pyguara.graphics.components.camera import Camera2D
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.platformer_system import PlatformerSystem
from pyguara.scripting.coroutines import CoroutineManager, wait_for_seconds

from games.guara_falcao.components import (
    PlayerState,
    Health,
    Score,
    PlatformSprite,
    CharacterSprite,
    Collectible,
    ZoneTrigger,
)
from games.guara_falcao.systems import (
    PlayerControlSystem,
    AnimationFSMSystem,
    CameraFollowSystem,
    CollectibleSystem,
    CheckpointSystem,
    HealthSystem,
)
from games.guara_falcao.events import (
    PlayerDeathEvent,
    CheckpointReachedEvent,
    CollectiblePickedEvent,
)
from games.guara_falcao.level_builder import LevelBuilder


class TitleScene(Scene):
    """Title screen for Guará & Falcão."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the title scene."""
        super().__init__("TitleScene", event_dispatcher)

    def on_enter(self) -> None:
        """Create title UI."""
        print("Guará & Falcão - Title")
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        # Title
        title = Label("GUARA & FALCAO", position=Vector2(260, 100))
        ui_manager.add_element(title)

        # Subtitle
        subtitle = Label("A Platformer Adventure", position=Vector2(280, 140))
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
        world_renderer.clear(Color(40, 50, 60))


class GameScene(Scene):
    """Main gameplay scene for Guará & Falcão."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the game scene."""
        super().__init__("GameScene", event_dispatcher)

        # Systems
        self._physics_system: Optional[PhysicsSystem] = None
        self._platformer_system: Optional[PlatformerSystem] = None
        self._player_control: Optional[PlayerControlSystem] = None
        self._animation_fsm: Optional[AnimationFSMSystem] = None
        self._camera_follow: Optional[CameraFollowSystem] = None
        self._collectible_system: Optional[CollectibleSystem] = None
        self._checkpoint_system: Optional[CheckpointSystem] = None
        self._health_system: Optional[HealthSystem] = None

        # Game state
        self._camera: Optional[Camera2D] = None
        self._player_id: Optional[str] = None
        self._level_builder: Optional[LevelBuilder] = None
        self._input_manager: Optional[InputManager] = None
        self._coroutine_manager: Optional[CoroutineManager] = None

        # Game flags
        self._is_dead = False
        self._level_complete = False

        # Input state tracking (for HOLD actions)
        self._move_left_held = False
        self._move_right_held = False
        self._jump_pressed = False

    def on_enter(self) -> None:
        """Initialize game systems and load level."""
        print("Guará & Falcão - Game Started")

        # Get managers
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        self._input_manager = self.container.get(InputManager)
        self._coroutine_manager = self.container.get(CoroutineManager)

        # Setup input
        self._setup_input()

        # Initialize physics
        physics_engine = self.container.get(IPhysicsEngine)

        self._physics_system = PhysicsSystem(
            engine=physics_engine,
            entity_manager=self.entity_manager,
            event_dispatcher=self.event_dispatcher,
        )

        # Set gravity AFTER PhysicsSystem init (which resets gravity to 0,0)
        physics_engine.gravity = Vector2(0, 800)

        self._platformer_system = PlatformerSystem(
            entity_manager=self.entity_manager,
            physics_engine=physics_engine,
        )

        # Initialize game systems
        self._player_control = PlayerControlSystem(
            self.entity_manager, self.event_dispatcher
        )
        self._animation_fsm = AnimationFSMSystem(self.entity_manager)
        self._camera_follow = CameraFollowSystem(self.entity_manager)
        self._collectible_system = CollectibleSystem(
            self.entity_manager, self.event_dispatcher
        )
        self._checkpoint_system = CheckpointSystem(
            self.entity_manager, self.event_dispatcher
        )
        self._health_system = HealthSystem(self.entity_manager, self.event_dispatcher)

        # Setup camera
        self._camera = Camera2D(800, 600)
        self._camera_follow.set_camera(self._camera)

        # Build level
        self._level_builder = LevelBuilder()
        spawn_point = self._level_builder.load_level(self.entity_manager)

        # Create player
        self._player_id = self._level_builder.create_player(
            self.entity_manager, spawn_point
        )

        # Link player to systems
        player = self.entity_manager.get_entity(self._player_id)
        if player:
            self._player_control.set_player(player)
            self._camera_follow.set_target(player)
            self._collectible_system.set_player(player)
            self._checkpoint_system.set_player(player)

        # Register events
        self.event_dispatcher.subscribe(PlayerDeathEvent, self._on_player_death)
        self.event_dispatcher.subscribe(CheckpointReachedEvent, self._on_checkpoint)
        self.event_dispatcher.subscribe(CollectiblePickedEvent, self._on_collectible)

        # Setup HUD
        self._setup_hud()

    def _setup_input(self) -> None:
        """Configure input bindings."""
        im = self._input_manager
        if not im:
            return

        im.register_action("move_left", ActionType.HOLD)
        im.register_action("move_right", ActionType.HOLD)
        im.register_action("jump", ActionType.PRESS)
        im.register_action("restart", ActionType.PRESS)
        im.register_action("back", ActionType.PRESS)

        im.bind_input(InputDevice.KEYBOARD, LEFT, "move_left")
        im.bind_input(InputDevice.KEYBOARD, RIGHT, "move_right")
        im.bind_input(InputDevice.KEYBOARD, SPACE, "jump")
        im.bind_input(InputDevice.KEYBOARD, UP, "jump")
        im.bind_input(InputDevice.KEYBOARD, R, "restart")
        im.bind_input(InputDevice.KEYBOARD, ESCAPE, "back")

        # Subscribe to action events
        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        """Handle input action events."""
        action = event.action_name
        is_pressed = event.value > 0

        # Track hold states for movement
        if action == "move_left":
            self._move_left_held = is_pressed
        elif action == "move_right":
            self._move_right_held = is_pressed
        elif action == "jump" and is_pressed:
            self._jump_pressed = True
        elif action == "restart" and is_pressed and not self._is_dead:
            self._restart_level()
        elif action == "back" and is_pressed:
            self.container.get(SceneManager).pop_scene()

    def _setup_hud(self) -> None:
        """Create HUD elements."""
        ui_manager = self.container.get(UIManager)

        # Instructions
        instructions = Label(
            "Arrows/Space: Move & Jump | R: Restart | ESC: Menu",
            position=Vector2(20, 560),
        )
        ui_manager.add_element(instructions)

    def _on_player_death(self, event: PlayerDeathEvent) -> None:
        """Handle player death."""
        self._is_dead = True
        if self._coroutine_manager:
            self._coroutine_manager.start_coroutine(self._death_sequence())

    def _death_sequence(self):
        """Death and respawn coroutine."""
        yield wait_for_seconds(1.0)

        # Respawn at checkpoint
        if self._checkpoint_system and self._player_id:
            spawn = self._checkpoint_system.get_spawn_point()
            player = self.entity_manager.get_entity(self._player_id)
            if player:
                transform = player.get_component(Transform)
                health = player.get_component(Health)
                if transform:
                    transform.position = spawn
                if health:
                    health.current = health.max_health
                    health.invincible_time = 1.0

        self._is_dead = False

    def _on_checkpoint(self, event: CheckpointReachedEvent) -> None:
        """Handle checkpoint reached."""
        print(f"Checkpoint reached: {event.zone_name}")

        if event.zone_name == "goal":
            self._level_complete = True
            if self._coroutine_manager:
                self._coroutine_manager.start_coroutine(self._complete_sequence())

    def _complete_sequence(self):
        """Level complete coroutine."""
        ui_manager = self.container.get(UIManager)
        label = Label("LEVEL COMPLETE!", position=Vector2(280, 250))
        ui_manager.add_element(label)

        yield wait_for_seconds(2.0)

        self.container.get(SceneManager).pop_scene()

    def _on_collectible(self, event: CollectiblePickedEvent) -> None:
        """Handle collectible pickup."""
        print(f"Collected {event.collect_type}: +{event.value}")

    def on_exit(self) -> None:
        """Cleanup."""
        if self._physics_system:
            self._physics_system.cleanup()

    def fixed_update(self, fixed_dt: float) -> None:
        """Run fixed timestep update for physics."""
        if self._physics_system:
            self._physics_system.update(fixed_dt)

    def update(self, dt: float) -> None:
        """Update game logic."""
        if self._is_dead or self._level_complete:
            if self._coroutine_manager:
                self._coroutine_manager.update(dt)
            return

        # Calculate move input from held keys
        move_input = 0.0
        if self._move_left_held:
            move_input = -1.0
        elif self._move_right_held:
            move_input = 1.0

        # Update systems
        if self._player_control:
            self._player_control.update(dt, move_input, self._jump_pressed)

        # Reset jump flag after it's been consumed
        self._jump_pressed = False

        if self._platformer_system:
            self._platformer_system.update(dt)

        if self._animation_fsm:
            self._animation_fsm.update(dt)

        if self._camera_follow:
            self._camera_follow.update(dt)

        if self._collectible_system:
            self._collectible_system.update(dt)

        if self._checkpoint_system:
            self._checkpoint_system.update(dt)

        if self._health_system:
            self._health_system.update(dt)

        if self._coroutine_manager:
            self._coroutine_manager.update(dt)

    def _restart_level(self) -> None:
        """Restart the current level."""
        entity_ids = [e.id for e in self.entity_manager.get_all_entities()]
        for eid in entity_ids:
            self.entity_manager.remove_entity(eid)
        self._is_dead = False
        self._level_complete = False

        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        if self._level_builder:
            spawn_point = self._level_builder.load_level(self.entity_manager)
            self._player_id = self._level_builder.create_player(
                self.entity_manager, spawn_point
            )

            player = self.entity_manager.get_entity(self._player_id)
            if player:
                self._player_control.set_player(player)
                self._camera_follow.set_target(player)
                self._collectible_system.set_player(player)
                self._checkpoint_system.set_player(player)

        self._setup_hud()

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the game."""
        world_renderer.clear(Color(35, 45, 55))

        # Get camera transform
        camera_offset = Vector2.zero()
        if self._camera:
            camera_offset = self._camera.position - Vector2(400, 300)

        # Render platforms
        for entity in self.entity_manager.get_entities_with(Transform, PlatformSprite):
            transform = entity.get_component(Transform)
            sprite = entity.get_component(PlatformSprite)

            # Apply camera offset
            screen_pos = transform.position - camera_offset

            rect = Rect(
                screen_pos.x - sprite.size.x // 2,
                screen_pos.y - sprite.size.y // 2,
                sprite.size.x,
                sprite.size.y,
            )
            world_renderer.draw_rect(rect, sprite.color)

        # Render collectibles (not collected)
        for entity in self.entity_manager.get_entities_with(
            Transform, CharacterSprite, Collectible
        ):
            collectible = entity.get_component(Collectible)
            if collectible.collected:
                continue

            transform = entity.get_component(Transform)
            sprite = entity.get_component(CharacterSprite)

            screen_pos = transform.position - camera_offset

            rect = Rect(
                screen_pos.x - sprite.size.x // 2,
                screen_pos.y - sprite.size.y // 2,
                sprite.size.x,
                sprite.size.y,
            )
            world_renderer.draw_rect(rect, sprite.color)

        # Render checkpoints/goals
        for entity in self.entity_manager.get_entities_with(
            Transform, CharacterSprite, ZoneTrigger
        ):
            transform = entity.get_component(Transform)
            sprite = entity.get_component(CharacterSprite)
            trigger = entity.get_component(ZoneTrigger)

            screen_pos = transform.position - camera_offset

            # Change color if triggered
            color = sprite.color
            if trigger.triggered:
                color = Color(150, 255, 150)

            rect = Rect(
                screen_pos.x - sprite.size.x // 2,
                screen_pos.y - sprite.size.y // 2,
                sprite.size.x,
                sprite.size.y,
            )
            world_renderer.draw_rect(rect, color)

        # Render player
        if self._player_id:
            player = self.entity_manager.get_entity(self._player_id)
            if player:
                transform = player.get_component(Transform)
                sprite = player.get_component(CharacterSprite)
                state = player.get_component(PlayerState)
                health = player.get_component(Health)

                if transform and sprite:
                    screen_pos = transform.position - camera_offset

                    # Flash when invincible
                    color = sprite.color
                    if health and health.invincible_time > 0:
                        # Flash every 0.1 seconds
                        if int(health.invincible_time * 10) % 2 == 0:
                            color = Color(255, 255, 255)

                    rect = Rect(
                        screen_pos.x - sprite.size.x // 2,
                        screen_pos.y - sprite.size.y // 2,
                        sprite.size.x,
                        sprite.size.y,
                    )
                    world_renderer.draw_rect(rect, color)

                    # Draw direction indicator
                    if state:
                        indicator_x = (
                            screen_pos.x + 15
                            if state.facing_right
                            else screen_pos.x - 15
                        )
                        indicator_rect = Rect(
                            indicator_x - 4,
                            screen_pos.y - sprite.size.y // 2 + 5,
                            8,
                            8,
                        )
                        world_renderer.draw_rect(indicator_rect, Color(255, 200, 150))

        # Render HUD
        self._render_hud(world_renderer)

    def _render_hud(self, renderer: IRenderer) -> None:
        """Render HUD elements."""
        if not self._player_id:
            return

        player = self.entity_manager.get_entity(self._player_id)
        if not player:
            return

        health = player.get_component(Health)
        score = player.get_component(Score)

        # Health hearts
        if health:
            for i in range(health.max_health):
                x = 20 + i * 25
                color = Color(200, 50, 50) if i < health.current else Color(80, 80, 80)
                rect = Rect(x, 20, 20, 20)
                renderer.draw_rect(rect, color)

        # Score/coins
        if score:
            # Simple coin counter (ideally we'd use text)
            for i in range(min(score.coins_collected, 10)):
                x = 700 - i * 15
                rect = Rect(x, 20, 12, 12)
                renderer.draw_rect(rect, Color(255, 220, 50))
