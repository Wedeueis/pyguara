"""Guará & Falcão - Game Scenes.

Two scenes live here -- the title screen and the game -- and two more in
`menus.py`, pushed over whichever of these is running. Between them they are
the demo's whole point: the same UI system and the same design-system theme
drawing a menu, a HUD and a modal, over a world drawn with nothing but
renderer primitives.

The gameplay underneath is unchanged. `systems.py`, `components.py` and
`level_builder.py` were not touched: what this rewrite replaces is how the
frame looks and how the screens are built, not how the platformer plays.
"""

from __future__ import annotations

import math

from games.guara_falcao import animation, art
from games.guara_falcao.bootstrap import (
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    attach_lighting,
    begin_world,
    configure_pipeline,
)
from games.guara_falcao.components import (
    CharacterSprite,
    Collectible,
    Hazard,
    Health,
    PlatformSprite,
    PlayerAnimState,
    PlayerState,
    ZoneTrigger,
)
from games.guara_falcao.events import (
    CheckpointReachedEvent,
    CollectiblePickedEvent,
    DebugCollidersToggled,
    PlayerDamagedEvent,
    PlayerDeathEvent,
)
from games.guara_falcao.hud import Hud
from games.guara_falcao.level_builder import LevelBuilder
from games.guara_falcao.menus import OptionsScene, PauseScene, Scrim, quit_game
from games.guara_falcao.systems import (
    AnimationFSMSystem,
    CameraFollowSystem,
    CheckpointSystem,
    CollectibleSystem,
    HazardSystem,
    HealthSystem,
    PatrolSystem,
    PlayerControlSystem,
    PlayerStatsSystem,
)
from pyguara.common.components import Transform, render_position, teleport
from pyguara.common.types import Color, Rect, Vector2
from pyguara.config.manager import ConfigManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.animation_system import AnimationSystem
from pyguara.graphics.components.animation import (
    AnimationClip,
    AnimationStateMachine,
)
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.lighting.components import AmbientLight, LightSource
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import ESCAPE, F1, LEFT, RIGHT, SPACE, UP, R
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.effects import EffectSystem
from pyguara.physics.components import CharacterBody
from pyguara.physics.debug_draw import ColliderDebugRenderer
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.platformer_controller import PlatformerController
from pyguara.physics.platformer_system import PlatformerSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.solid_mover import SolidMover
from pyguara.physics.solid_system import SolidSystem
from pyguara.resources.manager import ResourceManager
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager, wait_for_seconds
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import TextAlign, UILayer

AMBIENT = Color(255, 236, 206)
AMBIENT_INTENSITY = 0.84
"""Just under full, and that margin is the whole lighting budget.

The composite multiplies the world by the light map, and the light map is
ambient *plus* every light. At ambient 1.0 anything lit at all lands above
1.0, crosses the bloom threshold and hazes over -- so the frame has to sit
slightly under, leaving the sun and the pickups somewhere to go."""

SUN_COLOR = Color(255, 196, 120)
FRUIT_LIGHT = Color(180, 255, 120)
CHECKPOINT_LIGHT = Color(150, 240, 220)

PICKUP_BOB_HEIGHT = 3.0
PICKUP_BOB_RATE = 2.2
"""How far and how fast a pickup floats, in pixels and radians per second.

Small on purpose: the collection radius is 30px, so a bob big enough to
notice is also big enough to change when a pickup is picked up."""


def _sun(scene: Scene, width: int) -> None:
    """Hang the sun and the ambient term in a scene's world.

    Placed well above the frame: a light *inside* it has a hotspot, and
    anything that walks into a hotspot on a float light map blows out.

    Args:
        scene: The scene whose entity manager to build them in.
        width: Viewport width, for where to put the sun.
    """
    ambient = scene.entity_manager.create_entity("ambient")
    ambient.add_component(AmbientLight(color=AMBIENT, intensity=AMBIENT_INTENSITY))

    sun = scene.entity_manager.create_entity("sun")
    sun.add_component(Transform(position=Vector2(width * 0.74, -180.0)))
    sun.add_component(LightSource(color=SUN_COLOR, radius=900.0, intensity=0.33))


class TitleScene(Scene):
    """The title screen: a live Cerrado behind a carved wordmark."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the title scene."""
        super().__init__("TitleScene", event_dispatcher)
        self._camera = Camera2D(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._lighting: LightingSystem | None = None
        self._elapsed = 0.0
        self._visible = True
        self._walk: animation.Filmstrip | None = None
        self._fly: animation.Filmstrip | None = None

    def on_enter(self) -> None:
        """Build the backdrop's lights, the walker and the menu."""
        self._lighting = LightingSystem(self.entity_manager)
        _sun(self, WINDOW_WIDTH)
        attach_lighting(self.container, self._lighting)
        # The same clips the game plays, so the title and the level look
        # like one game. No entities here to hang components on, so these
        # are plain `Animator`s advanced by hand.
        clips = animation.load_clips(self.container.get(ResourceManager))
        self._walk = animation.Filmstrip(clips[animation.RUN])
        self._fly = animation.Filmstrip(clips[animation.FALCAO])
        self._build_menu()

    def on_resume(self) -> None:
        """Rebuild the menu after returning from the game or the options."""
        super().on_resume()
        self._visible = True
        if self._lighting:
            attach_lighting(self.container, self._lighting)
        self._build_menu()

    def _build_menu(self) -> None:
        """The wordmark plate, the button column and the badge."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        # A light touch of the same scrim the pause menu uses, so the
        # wordmark has something to sit on. At full strength it is a modal
        # wash and would bury the backdrop it is meant to settle.
        ui_manager.add_element(
            Scrim(WINDOW_WIDTH, WINDOW_HEIGHT, strength=0.32), UILayer.BACKDROP
        )

        plate_width, plate_height = 520, 132
        plate_x = (WINDOW_WIDTH - plate_width) // 2
        plate = BevelPanel(
            Vector2(plate_x, 96), Vector2(plate_width, plate_height), border_width=3
        )
        # Centred against the plate's own width, not a guessed x offset --
        # a guess is wrong the moment the text, the font or the plate
        # changes, and it was: the title measured 28px off-centre.
        plate.add_child(
            Label(
                "GUARÁ & FALCÃO",
                Vector2(plate_x, 126),
                font_size=44,
                width=plate_width,
                align=TextAlign.CENTER,
            )
        )
        plate.add_child(
            Label(
                "PYGUARA SOLAR ENGINE",
                Vector2(plate_x, 184),
                font_size=16,
                width=plate_width,
                align=TextAlign.CENTER,
            )
        )
        ui_manager.add_element(plate, UILayer.CONTENT)

        column = BoxContainer(
            Vector2((WINDOW_WIDTH - 260) // 2, 288),
            Vector2(260, 220),
            spacing=14,
        )
        for text, skin, handler in (
            ("Play", Skins.SAGE, self._on_play),
            ("Options", Skins.WOOD, self._on_options),
            ("Quit", Skins.WOOD, self._on_quit),
        ):
            button = BevelButton(text, Vector2(0, 0), Vector2(260, 52), skin=skin)
            button.on_click = handler
            column.add_child(button)
        ui_manager.add_element(column, UILayer.CONTENT)

        badge_width = 210
        badge_x = (WINDOW_WIDTH - badge_width) // 2
        badge = BevelPanel(
            Vector2(badge_x, 536), Vector2(badge_width, 34), border_width=1
        )
        badge.add_child(
            Label(
                "BUILT ON PYGUARA",
                Vector2(badge_x, 546),
                font_size=12,
                width=badge_width,
                align=TextAlign.CENTER,
            )
        )
        ui_manager.add_element(badge, UILayer.CONTENT)

        # Focus the first button, so the screen is usable without a mouse
        # and the focus ring has somewhere to start.
        ui_manager.set_focus(column.children[0])

    def _on_play(self, _element: object) -> None:
        """Start a run."""
        scene_manager = self.container.get(SceneManager)
        scene_manager.register(GameScene(self.event_dispatcher))
        scene_manager.push_scene("GameScene")

    def _on_options(self, _element: object) -> None:
        """Open the options panel over the title."""
        scene_manager = self.container.get(SceneManager)
        scene_manager.register(
            OptionsScene(self.event_dispatcher, WINDOW_WIDTH, WINDOW_HEIGHT)
        )
        scene_manager.push_scene("OptionsScene")

    def _on_quit(self, _element: object) -> None:
        """Leave."""
        quit_game(self.container)

    def on_exit(self) -> None:
        """Clean up scene resources."""

    def on_pause(self) -> None:
        """Stop drawing while the game or the options sit on top.

        Two scenes both drawing a full-screen backdrop is wasted work, and
        the one underneath cannot run the render pipeline without stealing
        the buffer the one above is drawing into.
        """
        super().on_pause()
        self._visible = False

    def update(self, dt: float) -> None:
        """Drift the backdrop, and walk the guará across it."""
        self._elapsed += dt
        if self._lighting:
            self._lighting.update(dt)
        for strip in (self._walk, self._fly):
            if strip is not None:
                strip.advance(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the Cerrado behind the menu."""
        if not self._visible:
            return

        begin_world(self.container)
        drift = self._elapsed * 12.0

        art.draw_sky(world_renderer, WINDOW_WIDTH, WINDOW_HEIGHT)
        art.draw_sun(world_renderer, WINDOW_WIDTH, WINDOW_HEIGHT)
        world_renderer.end_frame()

        art.draw_parallax(world_renderer, drift, WINDOW_WIDTH, WINDOW_HEIGHT)
        world_renderer.end_frame()

        # The hero and the companion, walking the near band -- after a
        # flush, so the canopies behind them stay behind them.
        ground = WINDOW_HEIGHT * 0.72 + 40
        walker = Vector2(
            WINDOW_WIDTH * 0.2 + math.sin(self._elapsed * 0.4) * 60.0, ground - 46
        )
        if self._walk is not None and self._fly is not None:
            scale = animation.DRAW_SCALE
            world_renderer.draw_texture(
                self._walk.sprite.texture,
                walker,
                scale=Vector2(scale, scale),
            )
            fly = animation.FALCAO_DRAW_SCALE
            world_renderer.draw_texture(
                self._fly.sprite.texture,
                walker + animation.falcao_offset(True, self._elapsed),
                scale=Vector2(fly, fly),
            )

        world_renderer.end_frame()
        configure_pipeline(self.container, self._camera)


class GameScene(Scene):
    """Main gameplay scene for Guará & Falcão."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the game scene."""
        super().__init__("GameScene", event_dispatcher)

        # Systems
        self._physics_system: PhysicsSystem | None = None
        self._platformer_system: PlatformerSystem | None = None
        self._solid_system: SolidSystem | None = None
        self._patrol_system: PatrolSystem | None = None
        self._collider_debug: ColliderDebugRenderer | None = None
        self._show_colliders = False
        self._player_control: PlayerControlSystem | None = None
        self._animation_fsm: AnimationFSMSystem | None = None
        self._animation_system: AnimationSystem | None = None
        self._player_animation: AnimationStateMachine | None = None
        self._clips: dict[str, AnimationClip] = {}
        self._falcao_id: str | None = None
        self._camera_follow: CameraFollowSystem | None = None
        self._collectible_system: CollectibleSystem | None = None
        self._checkpoint_system: CheckpointSystem | None = None
        self._health_system: HealthSystem | None = None
        self._hazard_system: HazardSystem | None = None
        self._effect_system: EffectSystem | None = None
        self._player_stats_system: PlayerStatsSystem | None = None
        self._lighting: LightingSystem | None = None

        # Game state
        self._camera: Camera2D | None = None
        self._player_id: str | None = None
        self._level_builder: LevelBuilder | None = None
        self._input_manager: InputManager | None = None
        self._coroutine_manager: CoroutineManager | None = None
        self._hud: Hud | None = None
        self._elapsed = 0.0

        # Each pickup's resting height, so the bob is a displacement from
        # somewhere rather than an accumulating drift.
        self._pickup_home: dict[str, float] = {}

        # Game flags
        self._is_dead = False
        self._level_complete = False

        # Input state tracking (for HOLD actions)
        self._move_left_held = False
        self._move_right_held = False
        self._jump_pressed = False

    def on_enter(self) -> None:
        """Initialize game systems and load level."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        self._input_manager = self.container.get(InputManager)
        self._coroutine_manager = self.container.get(CoroutineManager)

        self._setup_input()

        # Initialize physics with gravity for side-scroller
        physics_engine = self.container.get(IPhysicsEngine)
        physics_config = self.container.get(ConfigManager).config.physics

        self._physics_system = PhysicsSystem(
            engine=physics_engine,
            entity_manager=self.entity_manager,
            event_dispatcher=self.event_dispatcher,
            gravity=Vector2(physics_config.gravity_x, physics_config.gravity_y),
        )

        solid_mover = SolidMover(
            self.entity_manager, physics_engine, self.event_dispatcher
        )
        self._platformer_system = PlatformerSystem(
            entity_manager=self.entity_manager,
            physics_engine=physics_engine,
            gravity=Vector2(physics_config.gravity_x, physics_config.gravity_y),
            solid_mover=solid_mover,
        )
        self._solid_system = SolidSystem(self.entity_manager, solid_mover)
        self._patrol_system = PatrolSystem(self.entity_manager)

        # Initialize game systems
        self._player_control = PlayerControlSystem(
            self.entity_manager, self.event_dispatcher
        )
        self._animation_fsm = AnimationFSMSystem(self.entity_manager)
        # The engine's own, which advances `Animator`/`AnimationStateMachine`.
        # It runs after `AnimationFSMSystem`, which is what decides the
        # state it will play.
        self._animation_system = AnimationSystem(
            self.entity_manager, self.event_dispatcher
        )
        self._camera_follow = CameraFollowSystem(self.entity_manager)
        self._collectible_system = CollectibleSystem(
            self.entity_manager, self.event_dispatcher
        )
        self._checkpoint_system = CheckpointSystem(
            self.entity_manager, self.event_dispatcher
        )
        self._health_system = HealthSystem(self.entity_manager, self.event_dispatcher)
        self._hazard_system = HazardSystem(self.entity_manager, self.event_dispatcher)
        self._effect_system = EffectSystem(self.entity_manager, self.event_dispatcher)
        self._player_stats_system = PlayerStatsSystem(self.entity_manager)

        # Setup camera
        self._camera = Camera2D(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._camera_follow.set_camera(self._camera)

        # Loaded before the first `_link_player`, which is what attaches
        # them. `ResourceManager` caches, so a respawn or a second entry
        # into the scene re-reads nothing.
        self._clips = animation.load_clips(self.container.get(ResourceManager))

        # Build level
        self._level_builder = LevelBuilder()
        spawn_point = self._level_builder.load_level(self.entity_manager)

        self._player_id = self._level_builder.create_player(
            self.entity_manager, spawn_point
        )
        self._link_player()

        # Lighting: the sun, plus a small light on every pickup so bloom
        # makes them findable from across a wide level.
        self._lighting = LightingSystem(self.entity_manager)
        _sun(self, WINDOW_WIDTH)
        self._prepare_pickups()
        attach_lighting(self.container, self._lighting)

        # Register events
        self.event_dispatcher.subscribe(PlayerDeathEvent, self._on_player_death)
        self.event_dispatcher.subscribe(PlayerDamagedEvent, self._on_player_damaged)
        self.event_dispatcher.subscribe(CheckpointReachedEvent, self._on_checkpoint)
        self.event_dispatcher.subscribe(CollectiblePickedEvent, self._on_collectible)
        self.event_dispatcher.subscribe(DebugCollidersToggled, self._on_collider_toggle)

        self._setup_hud()

    def on_resume(self) -> None:
        """Rebuild the HUD and reclaim the light pass after a menu closes."""
        if self._lighting:
            attach_lighting(self.container, self._lighting)
        self._setup_hud()

    def _link_player(self) -> None:
        """Point every system that needs the player at the current one."""
        if not self._player_id:
            return
        player = self.entity_manager.get_entity(self._player_id)
        if not player:
            return
        self._player_control.set_player(player)  # type: ignore[union-attr]
        self._camera_follow.set_target(player)  # type: ignore[union-attr]
        self._collectible_system.set_player(player)  # type: ignore[union-attr]
        self._checkpoint_system.set_player(player)  # type: ignore[union-attr]
        self._hazard_system.set_player(player)  # type: ignore[union-attr]
        # A respawned player is a new entity, so it needs its own
        # animator -- the clips themselves are cached by the resource
        # manager and shared.
        self._player_animation = animation.attach(player, self._clips)

        # The companion is an entity of its own with a plain `Animator`
        # and no state machine -- one clip, nothing to decide. The
        # engine's `AnimationSystem` drives both paths.
        if self._falcao_id:
            self.entity_manager.remove_entity(self._falcao_id)
        falcao = self.entity_manager.create_entity("falcao")
        animation.attach_falcao(falcao, self._clips)
        self._falcao_id = falcao.id

    def _prepare_pickups(self) -> None:
        """Light every pickup, and remember the height it floats around.

        The bob lives on the transform rather than in the drawing, so the
        sprite, the light and the collection radius all agree on where the
        fruit is. Doing it at draw time made the fruit drift away from its
        own glow.
        """
        self._pickup_home.clear()
        for entity in self.entity_manager.get_entities_with(Transform, Collectible):
            collectible = entity.get_component(Collectible)
            self._pickup_home[entity.id] = entity.get_component(Transform).position.y
            color = (
                FRUIT_LIGHT if collectible.collect_type == "coin" else CHECKPOINT_LIGHT
            )
            # Small and soft. A pickup is meant to catch the eye across a
            # level, not to be a second sun -- at radius 120 / intensity
            # 0.7 each fruit blew a white hole through the bloom pass, and
            # a row of them merged into one wash.
            entity.add_component(LightSource(color=color, radius=34.0, intensity=0.14))

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
        im.register_action("toggle_colliders", ActionType.PRESS)

        im.bind_input(InputDevice.KEYBOARD, LEFT, "move_left")
        im.bind_input(InputDevice.KEYBOARD, RIGHT, "move_right")
        im.bind_input(InputDevice.KEYBOARD, SPACE, "jump")
        im.bind_input(InputDevice.KEYBOARD, UP, "jump")
        im.bind_input(InputDevice.KEYBOARD, R, "restart")
        im.bind_input(InputDevice.KEYBOARD, ESCAPE, "back")
        im.bind_input(InputDevice.KEYBOARD, F1, "toggle_colliders")

        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        """Handle input action events.

        Pushing an overlay (the pause menu) with `pause_below=True` freezes
        this scene's `update()`/`fixed_update()`, but not its subscription to
        the shared `EventDispatcher` -- it keeps receiving `OnActionEvent`
        underneath the overlay. Without this guard, an action like "back"
        reaches `_open_pause()` again while already paused, which re-registers
        and re-pushes a second `PauseScene` on top of the first.
        """
        if self.container.get(SceneManager).current_scene is not self:
            return

        action = event.action_name
        is_pressed = event.value > 0

        if action == "move_left":
            self._move_left_held = is_pressed
        elif action == "move_right":
            self._move_right_held = is_pressed
        elif action == "jump" and is_pressed:
            self._jump_pressed = True
        elif action == "restart" and is_pressed and not self._is_dead:
            self._restart_level()
        elif action == "back" and is_pressed:
            self._open_pause()
        elif action == "toggle_colliders" and is_pressed:
            self._show_colliders = not self._show_colliders

    def _on_collider_toggle(self, event: DebugCollidersToggled) -> None:
        """Honour the options panel's developer toggle."""
        self._show_colliders = event.shown

    def _open_pause(self) -> None:
        """Push the pause menu over this scene.

        `pause_below=True` stops this scene updating while leaving it
        rendering, which is the whole trick: the menu sits over a frozen
        game rather than over a black screen.
        """
        scene_manager = self.container.get(SceneManager)
        scene_manager.register(
            PauseScene(self.event_dispatcher, WINDOW_WIDTH, WINDOW_HEIGHT)
        )
        scene_manager.push_scene("PauseScene", pause_below=True)

    def set_show_colliders(self, shown: bool) -> None:
        """Turn collider outlines on or off.

        Args:
            shown: Whether to draw them.
        """
        self._show_colliders = shown

    def _setup_hud(self) -> None:
        """Build the HUD on its own layer."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear(UILayer.HUD)

        total = len(list(self.entity_manager.get_entities_with(Transform, Collectible)))
        self._hud = Hud(ui_manager, total_collectibles=total)
        self._hud.pause_button.on_click = lambda _element: self._open_pause()

    def _on_player_death(self, event: PlayerDeathEvent) -> None:
        """Handle player death."""
        self._is_dead = True
        if self._coroutine_manager:
            self._coroutine_manager.start_coroutine(self._death_sequence())

    def _death_sequence(self):
        """Death and respawn coroutine."""
        yield wait_for_seconds(1.0)

        if self._checkpoint_system and self._player_id:
            spawn = self._checkpoint_system.get_spawn_point()
            player = self.entity_manager.get_entity(self._player_id)
            if player:
                transform = player.get_component(Transform)
                health = player.get_component(Health)
                body = player.get_component(CharacterBody)
                controller = player.get_component(PlatformerController)

                if transform:
                    # teleport(), not assignment: a respawn is not motion, and
                    # interpolating it would draw the player sliding back
                    # across the level for a frame.
                    teleport(transform, spawn)

                # Reset velocity so the fall that killed the player doesn't
                # carry over into the respawn.
                if body:
                    body.velocity = Vector2.zero()

                if health:
                    health.current = health.max_health
                    health.invincible_time = 1.0

                if controller and self._platformer_system:
                    self._platformer_system.reset_jump_state(controller)
                    controller.is_grounded = False

        self._is_dead = False

    def _on_checkpoint(self, event: CheckpointReachedEvent) -> None:
        """Handle checkpoint reached."""
        if event.zone_name == "goal":
            self._level_complete = True
            if self._coroutine_manager:
                self._coroutine_manager.start_coroutine(self._complete_sequence())

    def _complete_sequence(self):
        """Level complete coroutine."""
        ui_manager = self.container.get(UIManager)
        banner_width = 420
        banner_x = (WINDOW_WIDTH - banner_width) // 2
        banner = BevelPanel(
            Vector2(banner_x, WINDOW_HEIGHT // 2 - 60),
            Vector2(banner_width, 96),
            border_width=3,
            shadow=True,
        )
        banner.add_child(
            Label(
                "LEVEL COMPLETE",
                Vector2(banner_x, WINDOW_HEIGHT // 2 - 26),
                font_size=32,
                width=banner_width,
                align=TextAlign.CENTER,
            )
        )
        ui_manager.add_element(banner, UILayer.OVERLAY)

        yield wait_for_seconds(2.0)

        ui_manager.clear()
        self.container.get(SceneManager).pop_scene()

    def _on_collectible(self, event: CollectiblePickedEvent) -> None:
        """Handle collectible pickup."""

    def on_exit(self) -> None:
        """Cleanup."""
        if self._physics_system:
            self._physics_system.cleanup()
        self.container.get(UIManager).clear(UILayer.HUD)

    def fixed_update(self, fixed_dt: float) -> None:
        """Run fixed timestep update for physics."""
        if self._is_dead or self._level_complete:
            return

        move_input = 0.0
        if self._move_left_held:
            move_input = -1.0
        elif self._move_right_held:
            move_input = 1.0

        if self._player_control:
            self._player_control.update(fixed_dt, move_input, self._jump_pressed)

        self._jump_pressed = False

        # 1. Whatever authors a solid's motion (patrol, here) runs first.
        if self._patrol_system:
            self._patrol_system.update(fixed_dt)

        # 2. Push those Transform changes into the engine before anything
        #    queries it this tick -- solids are still ordinary Chipmunk
        #    kinematic bodies, so raycasts/overlap queries against them
        #    need to see where they already are.
        if self._physics_system:
            self._physics_system.sync_kinematic_transforms()

        # 3. Solids carry/push whatever they touched.
        if self._solid_system:
            self._solid_system.update(fixed_dt)

        # 4. The character's own movement, swept by CharacterMover against
        #    this tick's (already current) geometry.
        if self._platformer_system:
            self._platformer_system.update(fixed_dt)

        # 5. Step the simulation, for whatever is still a genuine Chipmunk
        #    dynamic body -- nothing character-adjacent is, any more.
        if self._physics_system:
            self._physics_system.update(fixed_dt)

    def update(self, dt: float) -> None:
        """Update game logic."""
        self._elapsed += dt

        if self._is_dead or self._level_complete:
            if self._coroutine_manager:
                self._coroutine_manager.update(dt)
            return

        self._advance_player_animation(dt)

        for system in (
            self._camera_follow,
            self._collectible_system,
            self._checkpoint_system,
            self._health_system,
            self._hazard_system,
            self._effect_system,
            self._player_stats_system,
            self._lighting,
            self._coroutine_manager,
        ):
            if system is not None:
                system.update(dt)

        self._animate_pickups()

        if self._hud and self._player_id:
            self._hud.update(self.entity_manager.get_entity(self._player_id))

    def _advance_player_animation(self, dt: float) -> None:
        """Decide the player's clip, then advance it.

        Three steps in a fixed order, which is why they are here rather
        than in the systems tuple above: `AnimationFSMSystem` works out
        what the player is doing, `animation.drive` picks the clip for
        it, and the engine's `AnimationSystem` advances the frames. Any
        other order draws the previous frame's pose.

        Args:
            dt: Seconds since the last frame.
        """
        if self._animation_fsm is not None:
            self._animation_fsm.update(dt)

        player = (
            self.entity_manager.get_entity(self._player_id) if self._player_id else None
        )
        if player is not None and self._player_animation is not None:
            state = player.get_component(PlayerState)
            if state is not None:
                animation.drive(self._player_animation, state.current_state)

        if self._animation_system is not None:
            self._animation_system.update(dt)

    def _on_player_damaged(self, event: PlayerDamagedEvent) -> None:
        """Play the recoil.

        Driven by the event, not by `Health.invincible_time`: being hit
        happens once and being invincible lasts seconds, so a
        state-driven recoil would loop until it wore off.
        """
        if self._player_animation is not None:
            animation.recoil(self._player_animation)

    def _animate_pickups(self) -> None:
        """Float the uncollected pickups, and put out the collected ones.

        Two jobs, one loop, because they are the same question asked of the
        same entity: a pickup is either still there -- in which case it
        bobs and glows -- or it is gone. Nothing removes a collected
        entity, it is only flagged, so its light would otherwise burn on at
        full strength over an empty patch of air. That lingering glow is
        what "the fruit did not disappear" looks like.
        """
        for entity in self.entity_manager.get_entities_with(Transform, Collectible):
            light = entity.get_component(LightSource)
            collected = entity.get_component(Collectible).collected

            if collected:
                if light is not None and light.enabled:
                    light.enabled = False
                continue

            home = self._pickup_home.get(entity.id)
            if home is None:
                continue

            # Offset per entity so a row of fruit does not bob in unison,
            # which reads as one object rather than several.
            phase = self._elapsed * PICKUP_BOB_RATE + hash(entity.id) % 100 / 16.0
            transform = entity.get_component(Transform)
            # A new vector, not `position.y = ...`: `Vector2` is immutable.
            transform.position = Vector2(
                transform.position.x,
                home + math.sin(phase) * PICKUP_BOB_HEIGHT,
            )

    def _restart_level(self) -> None:
        """Restart the current level."""
        entity_ids = [e.id for e in self.entity_manager.get_all_entities()]
        for eid in entity_ids:
            self.entity_manager.remove_entity(eid)
        self._is_dead = False
        self._level_complete = False

        if self._level_builder:
            spawn_point = self._level_builder.load_level(self.entity_manager)
            self._player_id = self._level_builder.create_player(
                self.entity_manager, spawn_point
            )
            self._link_player()
            if self._checkpoint_system:
                self._checkpoint_system.set_initial_spawn(spawn_point)

        _sun(self, WINDOW_WIDTH)
        self._prepare_pickups()
        self._setup_hud()

    # ---- drawing --------------------------------------------------------

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the level, then run the light and post passes over it."""
        camera_offset = Vector2.zero()
        if self._camera:
            camera_offset = self._camera.position - Vector2(
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2
            )

        begin_world(self.container)

        # One `end_frame()` per depth layer. The backend draws every
        # rectangle, then every circle, then every line -- so without a
        # flush between these groups the tree canopies (circles) cover the
        # platforms (rectangles) they stand behind, and a fruit covers the
        # player. Submission order alone does not decide it.
        art.draw_sky(world_renderer, WINDOW_WIDTH, WINDOW_HEIGHT)
        art.draw_sun(world_renderer, WINDOW_WIDTH, WINDOW_HEIGHT)
        world_renderer.end_frame()

        art.draw_parallax(world_renderer, camera_offset.x, WINDOW_WIDTH, WINDOW_HEIGHT)
        world_renderer.end_frame()

        self._draw_platforms(world_renderer, camera_offset)
        world_renderer.end_frame()

        self._draw_pickups(world_renderer, camera_offset)
        self._draw_zones(world_renderer, camera_offset)
        world_renderer.end_frame()

        self._draw_player(world_renderer, camera_offset)

        if self._show_colliders:
            if self._collider_debug is None:
                self._collider_debug = ColliderDebugRenderer(self.entity_manager)
            self._collider_debug.render(world_renderer, camera_offset)

        # Shapes are batched and flushed here; anything drawn after this
        # lands on top of them. The HUD is widgets on the UI layer, which
        # composites later still.
        world_renderer.end_frame()
        configure_pipeline(
            self.container, self._camera or Camera2D(WINDOW_WIDTH, WINDOW_HEIGHT)
        )

    def _screen_rect(
        self, transform: Transform, size: Vector2, offset: Vector2
    ) -> Rect:
        """The screen rectangle for a centred sprite.

        Args:
            transform: The entity's transform.
            size: Its sprite size.
            offset: The camera offset.

        Returns:
            The rectangle to draw into.
        """
        position = transform.position - offset
        return Rect(
            int(position.x - size.x // 2),
            int(position.y - size.y // 2),
            int(size.x),
            int(size.y),
        )

    def _draw_platforms(self, renderer: IRenderer, offset: Vector2) -> None:
        """Draw solid tiles as earth and platforms as planks."""
        for entity in self.entity_manager.get_entities_with(Transform, PlatformSprite):
            sprite = entity.get_component(PlatformSprite)
            rect = self._screen_rect(
                entity.get_component(Transform), sprite.size, offset
            )
            if rect.width <= 34 and rect.height <= 34:
                art.draw_ground_tile(
                    renderer, rect, entity.get_component(Transform).position.x
                )
            else:
                art.draw_plank(renderer, rect)

    def _draw_pickups(self, renderer: IRenderer, offset: Vector2) -> None:
        """Draw uncollected pickups, and the hazards."""
        for entity in self.entity_manager.get_entities_with(
            Transform, CharacterSprite, Collectible
        ):
            collectible = entity.get_component(Collectible)
            if collectible.collected:
                continue
            transform = entity.get_component(Transform)
            position = transform.position - offset
            art.draw_pickup(
                renderer,
                Vector2(position.x, position.y),
                11.0,
                collectible.collect_type,
            )

        for entity in self.entity_manager.get_entities_with(
            Transform, CharacterSprite, Hazard
        ):
            sprite = entity.get_component(CharacterSprite)
            art.draw_hazard(
                renderer,
                self._screen_rect(entity.get_component(Transform), sprite.size, offset),
            )

    def _draw_zones(self, renderer: IRenderer, offset: Vector2) -> None:
        """Draw checkpoints and the goal."""
        for entity in self.entity_manager.get_entities_with(
            Transform, CharacterSprite, ZoneTrigger
        ):
            sprite = entity.get_component(CharacterSprite)
            trigger = entity.get_component(ZoneTrigger)
            rect = self._screen_rect(
                entity.get_component(Transform), sprite.size, offset
            )
            if trigger.zone_name == "goal":
                art.draw_goal(renderer, rect, self._elapsed)
            else:
                art.draw_checkpoint(renderer, rect, trigger.triggered)

    def _draw_player(self, renderer: IRenderer, offset: Vector2) -> None:
        """Draw the guará, and the falcão riding above."""
        if not self._player_id:
            return
        player = self.entity_manager.get_entity(self._player_id)
        if not player:
            return

        transform = player.get_component(Transform)
        sprite = player.get_component(CharacterSprite)
        state = player.get_component(PlayerState)
        health = player.get_component(Health)
        if transform is None or sprite is None:
            return

        # render_position, not position: drawing the raw fixed-tick position
        # makes motion stutter whenever the display rate is not locked to
        # the 60Hz physics rate.
        position = render_position(transform, self.render_alpha) - offset

        facing = state.facing_right if state else True

        # The invincibility blink. It used to be a white flash, which
        # `draw_texture` cannot do -- it carries no tint -- so the sprite
        # flickers instead, which is what the genre does anyway.
        if health is not None and not animation.blink_visible(health.invincible_time):
            return

        frame = player.get_component(Sprite)
        if frame is None or frame.texture is None:
            return

        anim = state.current_state if state else PlayerAnimState.IDLE

        # Lifted so the guará stands on the platform rather than sinking
        # into it: the slicer stands every frame on the bottom of its
        # canvas, and `draw_texture` centres on what it is given.
        feet = position.y + animation.draw_offset(sprite.size.y)

        # One scale for every clip -- every frame shares a canvas, so a
        # state change cannot resize the character. Mirrored by a negative
        # x, which is `IRenderer.draw_texture`'s contract.
        scale = animation.DRAW_SCALE
        renderer.draw_texture(
            frame.texture,
            Vector2(position.x, feet),
            scale=Vector2(scale if facing else -scale, scale),
        )
        self._draw_falcao(renderer, Vector2(position.x, feet), facing, anim)

    def _draw_falcao(
        self,
        renderer: IRenderer,
        centre: Vector2,
        facing_right: bool,
        anim: PlayerAnimState,
    ) -> None:
        """Draw the companion, when it is flying rather than riding.

        The guará's idle frames already have the falcão perched on its
        back, so it only appears here once the guará moves.
        """
        if not animation.falcao_visible(anim) or not self._falcao_id:
            return
        falcao = self.entity_manager.get_entity(self._falcao_id)
        if falcao is None:
            return
        frame = falcao.get_component(Sprite)
        if frame is None or frame.texture is None:
            return
        offset = animation.falcao_offset(facing_right, self._elapsed)
        scale = animation.FALCAO_DRAW_SCALE
        renderer.draw_texture(
            frame.texture,
            centre + offset,
            scale=Vector2(scale if facing_right else -scale, scale),
        )
