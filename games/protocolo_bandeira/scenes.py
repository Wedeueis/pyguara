"""Protocolo Bandeira - Game Scenes.

Menu, arena and game-over screens, all three sharing one `ArenaFX`: the
same patch of cerrado, lit the same way, with the same heat rising off it.

The arena scene is where the engine's draw ordering shows through. The
ModernGL backend queues shape primitives into one bucket per shape type
and flushes them at `end_frame()`, while `draw_text` draws the moment it
is called -- so text submitted before a shape still ends up underneath it.
Everything shaped is therefore drawn first, in layers separated by
flushes, and only then is the HUD's text written over the top. See
`render.py`, which is where that rule is actually enforced.

The other thing worth knowing is that none of the game's rules know that
any of this exists. Every bit of feedback -- sparks, shake, hit-stop,
damage numbers, the screen flash -- hangs off events the combat systems
were already dispatching, so `systems.py` never grew a line about how a
hit should look.
"""

from __future__ import annotations

import math

from games.protocolo_bandeira import render
from games.protocolo_bandeira.arena_fx import ArenaFX
from games.protocolo_bandeira.bootstrap import WINDOW_HEIGHT, WINDOW_WIDTH
from games.protocolo_bandeira.components import (
    EnemyAI,
    EnemyType,
    Movement,
    Score,
    ShooterSprite,
    Weapon,
)
from games.protocolo_bandeira.events import (
    BulletFiredEvent,
    EnemyKilledEvent,
    PlayerDeathEvent,
    WaveCompleteEvent,
    WaveStartEvent,
)
from games.protocolo_bandeira.pooling import EnemyPool
from games.protocolo_bandeira.systems import (
    CollisionSystem,
    EnemyAISystem,
    PlayerControlSystem,
    ScoreSystem,
    WeaponSystem,
)
from games.protocolo_bandeira.wave_manager import WaveManager
from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.pool import Poolable
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.window import Window
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import DOWN, ESCAPE, LEFT, RIGHT, SPACE, UP, A, D, S, W
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.action_combat import DamageDealt, Health, HealthSystem, Hurtbox
from pyguara.kits.projectiles import ProjectileSystem
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager, wait_for_seconds
from pyguara.spatial import SpatialIndexSystem, SpatialTracked
from pyguara.ui.components.button import Button
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager

# The play area, with an arcade bezel above and below it.
ARENA = Rect(26, 104, WINDOW_WIDTH - 52, WINDOW_HEIGHT - 104 - 72)

# Seconds a kill keeps the chain alive. Long enough to survive crossing
# the arena, short enough that it has to be worked for.
COMBO_WINDOW = 2.6

# Hit-stop, in seconds. A kill is a few frames at 60Hz; a bomber is more.
KILL_FREEZE = 0.055
BOMBER_FREEZE = 0.1
PLAYER_HIT_FREEZE = 0.12

# The muzzle flash's own decay, in seconds.
FLASH_DECAY = 0.07

# Best score this session, shared across runs so the game-over screen has
# something to beat. Module-level rather than persisted: this is a demo,
# and `persistence/` is a different demo's subject.
_high_score = 0


def _enemy_kind(enemy_type: EnemyType) -> str:
    """Map the AI's enemy type onto the renderer's vocabulary."""
    if enemy_type == EnemyType.SHOOTER:
        return "shooter"
    if enemy_type == EnemyType.BOMBER:
        return "bomber"
    return "chaser"


class _ClearingScene(Scene):
    """A scene that owns an `ArenaFX` and knows when it is on screen.

    `push_scene` leaves the scene underneath in the stack, and the scene
    manager both updates and renders every stacked scene before the
    current one. That was harmless when the menu drew a flat colour and
    did nothing on update; now each scene owns a whole clearing and drives
    the render graph, and a paused one would paint its ground over the
    scene above it while fighting for the shared `HeatHazeEffect`'s
    uniforms. A paused scene therefore neither draws nor updates.
    """

    def __init__(self, name: str, event_dispatcher: EventDispatcher) -> None:
        """Initialize the scene in its visible state."""
        super().__init__(name, event_dispatcher)
        self.fx: ArenaFX | None = None
        self._visible = True

    def build_fx(self, seed: int | None = None) -> ArenaFX:
        """Create this scene's environment. Call from `on_enter()`.

        Args:
            seed: Seed for the scatter and sparks, or None for an
                unseeded run.

        Returns:
            The new environment, also stored on the scene.
        """
        self.fx = ArenaFX(
            self.container,
            self.entity_manager,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            arena=ARENA,
            seed=seed,
        )
        return self.fx

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


class MenuScene(_ClearingScene):
    """Main menu: the title, over an anteater patrolling its clearing."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the menu scene."""
        super().__init__("MenuScene", event_dispatcher)
        self._ants: list[render.EnemyView] = []

    def on_enter(self) -> None:
        """Create menu UI and the clearing behind it."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        self.build_fx(seed=7)

        container = BoxContainer(
            position=Vector2(380, 420), size=Vector2(200, 200), spacing=15
        )

        btn_start = Button("START", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_start.on_click = self._on_start_click
        container.add_child(btn_start)

        btn_quit = Button("QUIT", position=Vector2(0, 0), size=Vector2(200, 50))
        btn_quit.on_click = self._on_quit_click
        container.add_child(btn_quit)

        ui_manager.add_element(container)

        # A few ants circling, so the menu is a place rather than a plate.
        self._ants = [
            render.EnemyView(
                kind="chaser" if index % 3 else "shooter",
                position=Vector2.zero(),
                angle=0.0,
                phase=index * 1.7,
                flash=0.0,
            )
            for index in range(6)
        ]

    def _on_start_click(self, el) -> None:
        """Start the game."""
        scene_manager = self.container.get(SceneManager)
        arena_scene = ArenaScene(self.event_dispatcher)
        scene_manager.register(arena_scene)
        scene_manager.push_scene("ArenaScene")

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
        """Recreate UI when returning from the arena."""
        super().on_resume()
        self.on_enter()

    def update(self, dt: float) -> None:
        """Walk the demo ants around the anteater."""
        if not self.is_visible or self.fx is None:
            return

        time = self.fx.time
        centre = Vector2(ARENA.centerx, ARENA.centery + 60)
        for index, ant in enumerate(self._ants):
            orbit = 150.0 + index * 26.0
            speed = 0.42 + index * 0.06
            angle = time * speed + index * 1.05
            ant.position = centre + Vector2(
                math.cos(angle) * orbit, math.sin(angle) * orbit * 0.55
            )
            # Facing is the tangent of the orbit, so they walk forwards.
            ant.angle = angle + math.pi / 2

        self.fx.set_dynamic_lights([(centre, Color(255, 190, 120), 190.0, 0.7)])
        self.fx.update(dt, self.camera)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the clearing behind the menu."""
        if not self.is_visible or self.fx is None or self.camera is None:
            return

        fx = self.fx
        fx.draw_ground(world_renderer)
        render.draw_enemies(world_renderer, self._ants, time=fx.time, offset=fx.offset)
        render.draw_anteater(
            world_renderer,
            Vector2(ARENA.centerx, ARENA.centery + 60),
            math.sin(fx.time * 0.4) * 0.9 - math.pi / 2,
            time=fx.time,
            offset=fx.offset,
            moving=False,
        )
        fx.sparks.render(world_renderer, fx.offset)
        world_renderer.end_frame()

        # Drawn into the world buffer rather than as a UI `Label`, so the
        # title is inside the pipeline: it blooms, and the heat bends it.
        # UI widgets are drawn after the final blit and would pick up
        # neither.
        world_renderer.draw_text(
            "PROTOCOLO", Vector2(WINDOW_WIDTH / 2 - 196, 120), render.TEXT, size=62
        )
        world_renderer.draw_text(
            "BANDEIRA", Vector2(WINDOW_WIDTH / 2 - 174, 184), render.GOLD, size=62
        )
        world_renderer.draw_text(
            "o tamanduá segura a linha",
            Vector2(WINDOW_WIDTH / 2 - 118, 258),
            render.DUST_PALE,
            size=18,
        )

        fx.run_pipeline(self.camera)


class ArenaScene(_ClearingScene):
    """Main gameplay arena for Protocolo Bandeira."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the arena scene."""
        super().__init__("ArenaScene", event_dispatcher)

        # Pools
        self._enemy_pool: EnemyPool | None = None

        # Non-physics spatial index, shared by SpatialIndexSystem and
        # ProjectileSystem's hit-check.
        self._spatial_index: SpatialHash | None = None

        # Systems
        self._player_control: PlayerControlSystem | None = None
        self._spatial_index_system: SpatialIndexSystem | None = None
        self._projectile_system: ProjectileSystem | None = None
        self._health_system: HealthSystem | None = None
        self._enemy_ai: EnemyAISystem | None = None
        self._collision_system: CollisionSystem | None = None
        self._weapon_system: WeaponSystem | None = None
        self._score_system: ScoreSystem | None = None

        # Wave manager
        self._wave_manager: WaveManager | None = None

        # Game state
        self._player_id: str | None = None
        self._input_manager: InputManager | None = None
        self._coroutine_manager: CoroutineManager | None = None
        self._is_game_over = False
        self._wave_transition = False

        # Presentation state -- none of it known to the game's rules.
        self._muzzle_flash = 0.0
        self._enemy_flash: dict[str, float] = {}
        self._enemy_facing: dict[str, float] = {}
        self._combo = 0
        self._combo_timer = 0.0
        self._banner = ""
        self._banner_timer = 0.0

        # Input state tracking
        self._move_up_held = False
        self._move_down_held = False
        self._move_left_held = False
        self._move_right_held = False
        self._fire_held = False

    def on_enter(self) -> None:
        """Initialize game systems and start the first wave."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        self.build_fx()

        self._input_manager = self.container.get(InputManager)
        self._coroutine_manager = self.container.get(CoroutineManager)

        self._setup_input()

        self._enemy_pool = EnemyPool(self.entity_manager, size=100)

        # Spatial index + the systems that read/write it
        self._spatial_index = self.container.get(SpatialHash)
        self._spatial_index_system = SpatialIndexSystem(
            self.entity_manager, self._spatial_index, self.event_dispatcher
        )
        self._projectile_system = ProjectileSystem(
            self.entity_manager,
            self.event_dispatcher,
            self._spatial_index,
            capacity=500,
        )

        self._player_control = PlayerControlSystem(self.entity_manager, ARENA)
        self._health_system = HealthSystem(self.entity_manager)
        self._enemy_ai = EnemyAISystem(
            self.entity_manager,
            self.event_dispatcher,
            self._enemy_pool,
            self._projectile_system,
            ARENA,
        )
        self._collision_system = CollisionSystem(
            self.entity_manager,
            self.event_dispatcher,
            self._enemy_pool,
        )
        self._weapon_system = WeaponSystem(
            self.entity_manager,
            self.event_dispatcher,
            self._projectile_system,
        )
        self._score_system = ScoreSystem(self.entity_manager, self.event_dispatcher)

        self._wave_manager = WaveManager(self._enemy_pool, self.event_dispatcher, ARENA)
        self._collision_system.set_wave_manager(self._wave_manager)

        self._create_player()

        # Rules events
        self.event_dispatcher.subscribe(PlayerDeathEvent, self._on_player_death)
        self.event_dispatcher.subscribe(WaveCompleteEvent, self._on_wave_complete)

        # Feedback events -- the entire juice layer hangs off these three,
        # all of which the combat systems were already dispatching.
        self.event_dispatcher.subscribe(DamageDealt, self._on_damage)
        self.event_dispatcher.subscribe(EnemyKilledEvent, self._on_enemy_killed)
        self.event_dispatcher.subscribe(BulletFiredEvent, self._on_bullet_fired)
        self.event_dispatcher.subscribe(WaveStartEvent, self._on_wave_start)

        self._setup_hud()
        self._wave_manager.start_wave(1)

    def _setup_input(self) -> None:
        """Configure input bindings."""
        im = self._input_manager
        if not im:
            return

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

        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        """Handle input action events."""
        action = event.action_name
        is_pressed = event.value > 0

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

        player.add_component(Transform(position=Vector2(ARENA.centerx, ARENA.centery)))
        player.add_component(Movement(speed=230.0))
        player.add_component(
            Weapon(
                fire_rate=0.15,
                bullet_speed=560.0,
                bullet_damage=1,
            )
        )
        player.add_component(Health(current=5.0, max_health=5.0))
        player.add_component(Hurtbox(team="player"))
        player.add_component(SpatialTracked())
        player.add_component(Score())
        player.add_component(
            ShooterSprite(color=render.FUR_LIGHT, size=15.0, shape="triangle")
        )

        self._player_id = player.id

        self._player_control.set_player(player)
        self._collision_system.set_player(player)
        self._weapon_system.set_player(player)
        self._score_system.set_player(player)

    def _setup_hud(self) -> None:
        """The HUD is drawn in `render()`, not built from UI widgets.

        It is an arcade bezel -- a portrait box, health pips, a wave meter
        -- and every part of it is a shape or a string in `render.py`,
        which keeps it inside the same flush discipline as the rest of the
        frame. Nothing to build here; the method stays as the place that
        explains why.
        """
        self.container.get(UIManager).clear()

    # ---- feedback --------------------------------------------------

    def _on_bullet_fired(self, event: BulletFiredEvent) -> None:
        """Flash the muzzle, nudge the screen, and kick up a little dust."""
        if self.fx is None or event.team.name != "PLAYER":
            return
        self._muzzle_flash = 1.0
        self.fx.shaker.add(1.6, duration=0.08)
        self.fx.sparks.burst(
            event.position + event.direction * 38,
            render.PLAYER_SHOT,
            count=4,
            speed=150.0,
            direction=math.atan2(event.direction.y, event.direction.x),
            spread=1.1,
            life=0.18,
            radius=2.0,
            gravity=0.0,
            drag=0.85,
            streak=True,
        )

    def _on_damage(self, event: DamageDealt) -> None:
        """Spark, flash and shake on every landed hit.

        Fires for the player's hits and the swarm's alike; `DamageDealt`
        carries no position, so the target's `Transform` is the source of
        truth for where the feedback goes.
        """
        if self.fx is None or event.amount <= 0:
            return

        target = self.entity_manager.get_entity(event.target)
        if target is None:
            return
        transform = target.get_component(Transform)
        if transform is None:
            return

        if event.target == self._player_id:
            self.fx.flash.trigger(Color(255, 70, 50, 150), duration=0.22)
            self.fx.shaker.add(12.0, duration=0.32)
            self.fx.hit_stop(PLAYER_HIT_FREEZE)
            self.fx.impact(transform.position, render.BLOOD, count=16, speed=230.0)
            self._break_combo()
            return

        # An enemy took it: whiten it for a few frames, spray, and -- when
        # the chain is running -- say so.
        self._enemy_flash[event.target] = 1.0
        self.fx.impact(transform.position, render.BLOOD, count=8, shake=1.2)
        if not event.killed:
            self.fx.popup(
                f"-{int(event.amount)}", transform.position, render.HIT_WHITE, size=15
            )

    def _on_enemy_killed(self, event: EnemyKilledEvent) -> None:
        """Blow the enemy apart, freeze the frame, and extend the chain."""
        if self.fx is None:
            return

        self._combo += 1
        self._combo_timer = COMBO_WINDOW

        big = event.points >= 50 and event.points < 100
        self.fx.explode(
            event.position,
            render.BOMBER_HOT if big else render.BLOOD,
            big=big,
        )
        self.fx.hit_stop(BOMBER_FREEZE if big else KILL_FREEZE)

        points = event.points * max(1, self._combo)
        self.fx.popup(
            f"+{points}",
            event.position,
            render.COMBO_COLOR if self._combo > 1 else render.GOLD,
            size=16 + min(10, self._combo),
        )
        if self._combo > 1:
            self.fx.popup(
                f"x{self._combo}",
                event.position + Vector2(0, -20),
                render.COMBO_COLOR,
                size=14,
            )

    def _on_wave_start(self, event: WaveStartEvent) -> None:
        """Announce the wave across the middle of the screen."""
        self._banner = f"WAVE {event.wave_number}"
        self._banner_timer = 1.8

    def _break_combo(self) -> None:
        """Drop the chain -- taking a hit ends it."""
        self._combo = 0
        self._combo_timer = 0.0

    # ---- lifecycle -------------------------------------------------

    def _on_player_death(self, event: PlayerDeathEvent) -> None:
        """Handle player death."""
        self._is_game_over = True
        if self.fx is not None:
            self.fx.flash.trigger(Color(255, 120, 60, 210), duration=0.6)
            self.fx.shaker.add(22.0, duration=0.7)
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
        self._banner = "CLEAR"
        self._banner_timer = 1.4
        if self._coroutine_manager:
            self._coroutine_manager.start_coroutine(
                self._wave_transition_sequence(event.wave_number)
            )

    def _wave_transition_sequence(self, completed_wave: int):
        """Coroutine for wave transition."""
        yield wait_for_seconds(1.5)

        self._wave_transition = False
        if self._wave_manager:
            self._wave_manager.start_wave(completed_wave + 1)
            if self._score_system:
                self._score_system.update_wave(completed_wave + 1)

    def on_exit(self) -> None:
        """Cleanup."""
        pass

    # ---- per-frame -------------------------------------------------

    def update(self, dt: float) -> None:
        """Update game logic, then everything that reacts to it.

        The simulation steps on `game_dt`, which a hit-stop can zero; the
        presentation always steps on the real `dt`, so sparks keep flying
        and the shake keeps settling through the freeze.
        """
        if self.fx is None:
            return

        self._advance_presentation(dt)

        if self._is_game_over:
            self.fx.update(dt, self.camera)
            return

        game_dt = self.fx.gameplay_dt(dt)

        if self._coroutine_manager:
            self._coroutine_manager.update(game_dt)

        if game_dt > 0.0:
            self._step_simulation(game_dt)

        self.fx.set_dynamic_lights(self._lights())
        self.fx.update(dt, self.camera)

    def _advance_presentation(self, dt: float) -> None:
        """Decay the flashes, the banner and the combo window."""
        self._muzzle_flash = max(0.0, self._muzzle_flash - dt / FLASH_DECAY)
        self._banner_timer = max(0.0, self._banner_timer - dt)

        if self._combo_timer > 0.0:
            self._combo_timer = max(0.0, self._combo_timer - dt)
            if self._combo_timer == 0.0:
                self._combo = 0

        if self._enemy_flash:
            self._enemy_flash = {
                entity_id: flash - dt * 7.0
                for entity_id, flash in self._enemy_flash.items()
                if flash - dt * 7.0 > 0.0
            }

    def _step_simulation(self, dt: float) -> None:
        """Run one tick of the game's rules."""
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

        if move_dir.magnitude > 0:
            move_dir = move_dir.normalize()
            aim_dir = move_dir  # Aim in movement direction
        elif self._player_id:
            # Standing still: keep aiming the way the player was last
            # facing (Movement.facing_angle persists across frames)
            # instead of leaving aim_dir at zero, which silently blocked
            # firing while stationary.
            player = self.entity_manager.get_entity(self._player_id)
            movement = player.get_component(Movement) if player else None
            if movement:
                aim_dir = Vector2(
                    math.cos(movement.facing_angle), math.sin(movement.facing_angle)
                )

        if self._player_control:
            self._player_control.update(dt, move_dir, aim_dir, fire)

            player_pos = self._player_control.get_position()
            if player_pos and self._enemy_ai:
                self._enemy_ai.set_player_position(player_pos)

            if fire and player_pos and aim_dir.magnitude > 0:
                if self._weapon_system:
                    self._weapon_system.fire(player_pos, aim_dir)

        if self._enemy_ai:
            self._enemy_ai.update(dt)

        # Reindex before the projectile hit-check reads it, so a bullet
        # checks this tick's enemy/player positions, not last tick's.
        if self._spatial_index_system:
            self._spatial_index_system.update(dt)

        if self._projectile_system:
            self._projectile_system.update(dt)

        if self._collision_system:
            self._collision_system.update(dt)

        if self._wave_manager and not self._wave_transition:
            player_pos = (
                self._player_control.get_position()
                if self._player_control
                else Vector2(ARENA.centerx, ARENA.centery)
            )
            self._wave_manager.update(dt, player_pos)

        if self._health_system:
            self._health_system.update(dt)

    def _lights(self) -> list[tuple[Vector2, Color, float, float]]:
        """Every moving light this frame, brightest first.

        Ordered deliberately: the pool is finite and drops the tail, so a
        crowded frame should lose a tracer's glow rather than the light
        the player is standing in.
        """
        lights: list[tuple[Vector2, Color, float, float]] = []

        player = self._player()
        if player is not None:
            transform = player.get_component(Transform)
            movement = player.get_component(Movement)
            if transform is not None:
                # Deliberately gentle, and wider than the animal. A
                # bright light centred on the player sits *on* it, and on
                # a float light map that means the player renders as a
                # white silhouette of itself rather than a grey anteater.
                lights.append((transform.position, Color(255, 214, 168), 210.0, 0.4))
                if movement is not None and self._muzzle_flash > 0.0:
                    muzzle = (
                        transform.position
                        + Vector2(
                            math.cos(movement.facing_angle),
                            math.sin(movement.facing_angle),
                        )
                        # Out at the snout tip rather than on the body,
                        # for the same reason: the flash should light the
                        # ground in front of the player, not bleach it.
                        * 52
                    )
                    lights.append(
                        (muzzle, render.PLAYER_SHOT, 230.0, 0.85 * self._muzzle_flash)
                    )

        if self._enemy_pool:
            for entity in self._enemy_pool.get_active():
                poolable = entity.get_component(Poolable)
                ai = entity.get_component(EnemyAI)
                transform = entity.get_component(Transform)
                if not poolable or not poolable.is_active or not ai or not transform:
                    continue
                if ai.enemy_type == EnemyType.BOMBER:
                    lights.append((transform.position, render.BOMBER_HOT, 120.0, 0.75))

        if self._projectile_system:
            for projectile in self._projectile_system.get_active():
                color = (
                    render.PLAYER_SHOT
                    if projectile.team == "player"
                    else render.ENEMY_SHOT
                )
                lights.append((projectile.position, color, 48.0, 0.45))

        return lights

    # ---- drawing ---------------------------------------------------

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the clearing, the fight and the bezel, then run the pipeline."""
        if not self.is_visible or self.fx is None or self.camera is None:
            return

        fx = self.fx
        offset = fx.offset

        fx.draw_ground(world_renderer)

        if self._wave_manager:
            render.draw_spawn_warnings(
                world_renderer, self._wave_manager.warnings, offset=offset
            )

        render.draw_enemies(
            world_renderer, self._enemy_views(), time=fx.time, offset=offset
        )
        render.draw_shots(world_renderer, self._shot_views(), offset=offset)
        self._draw_player(world_renderer, offset)
        fx.sparks.render(world_renderer, offset)
        world_renderer.end_frame()

        self._draw_hud_panels(world_renderer)

        # The damage flash is a full-screen rect, and rects flush before
        # circles and lines -- so it needs a batch of its own to land on
        # top of the arena rather than under it.
        world_renderer.end_frame()
        fx.flash.render(world_renderer, Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))

        # Flush again, so the HUD's text -- which draws immediately --
        # lands over every shape rather than under it.
        world_renderer.end_frame()

        self._draw_hud_text(world_renderer)
        fx.popups.render(world_renderer, self.camera)

        fx.run_pipeline(self.camera)

    def _draw_player(self, renderer: IRenderer, offset: Vector2) -> None:
        """Draw the anteater and whatever is coming out of its snout."""
        player = self._player()
        if player is None:
            return

        transform = player.get_component(Transform)
        movement = player.get_component(Movement)
        health = player.get_component(Health)
        if transform is None or movement is None:
            return

        flashing = bool(
            health
            and health.invincible_timer > 0
            and int(health.invincible_timer * 20) % 3 == 0
        )

        render.draw_anteater(
            renderer,
            transform.position,
            movement.facing_angle,
            time=self.fx.time if self.fx else 0.0,
            offset=offset,
            moving=movement.velocity.magnitude > 1.0,
            flashing=flashing,
        )
        render.draw_muzzle_flash(
            renderer,
            transform.position,
            movement.facing_angle,
            self._muzzle_flash,
            offset=offset,
        )

    def _enemy_views(self) -> list[render.EnemyView]:
        """Snapshot the swarm for the renderer, facings included.

        Enemy facing is derived here rather than stored on `Movement`:
        the AI steers by velocity and never had a reason to care which way
        a creature points, and a stale facing on a stopped enemy looks
        better than one that snaps to zero.
        """
        views: list[render.EnemyView] = []
        if not self._enemy_pool:
            return views

        for index, entity in enumerate(self._enemy_pool.get_active()):
            poolable = entity.get_component(Poolable)
            if not poolable or not poolable.is_active:
                continue

            transform = entity.get_component(Transform)
            ai = entity.get_component(EnemyAI)
            movement = entity.get_component(Movement)
            if not transform or not ai:
                continue

            if movement and movement.velocity.magnitude > 1.0:
                self._enemy_facing[entity.id] = math.atan2(
                    movement.velocity.y, movement.velocity.x
                )

            views.append(
                render.EnemyView(
                    kind=_enemy_kind(ai.enemy_type),
                    position=transform.position,
                    angle=self._enemy_facing.get(entity.id, 0.0),
                    phase=index * 0.9,
                    flash=self._enemy_flash.get(entity.id, 0.0),
                )
            )
        return views

    def _shot_views(self) -> list[tuple[Vector2, Vector2, str]]:
        """Snapshot every live projectile as `(position, velocity, team)`."""
        if not self._projectile_system:
            return []
        return [
            (projectile.position, projectile.velocity, projectile.team)
            for projectile in self._projectile_system.get_active()
        ]

    def _draw_hud_panels(self, renderer: IRenderer) -> None:
        """Draw the shaped half of the bezel."""
        player = self._player()
        health = player.get_component(Health) if player else None

        render.draw_hud_panels(
            renderer,
            arena=ARENA,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            health=health.current if health else 0.0,
            max_health=health.max_health if health else 5.0,
            combo=self._combo,
            combo_fraction=self._combo_timer / COMBO_WINDOW,
            wave_fraction=(
                self._wave_manager.wave_fraction if self._wave_manager else 0.0
            ),
        )

    def _draw_hud_text(self, renderer: IRenderer) -> None:
        """Write the bezel's text, over every shape in the frame."""
        global _high_score

        player = self._player()
        score = player.get_component(Score) if player else None
        value = score.value if score else 0
        _high_score = max(_high_score, value)

        banner_strength = min(1.0, self._banner_timer / 0.5)

        render.draw_hud_text(
            renderer,
            arena=ARENA,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            score=value,
            high_score=_high_score,
            wave=score.wave if score else 1,
            kills=score.kills if score else 0,
            combo=self._combo,
            banner=self._banner,
            banner_strength=banner_strength,
        )

    def _player(self):
        """Return the player entity, or None once it is gone."""
        if not self._player_id:
            return None
        return self.entity_manager.get_entity(self._player_id)


class GameOverScene(_ClearingScene):
    """Game over screen, over the clearing the run ended in."""

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
        global _high_score
        _high_score = max(_high_score, self._final_score)

        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        self.build_fx(seed=3)

        container = BoxContainer(
            position=Vector2(380, 380), size=Vector2(200, 150), spacing=15
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
        """Let the dust settle."""
        if not self.is_visible or self.fx is None:
            return
        self.fx.set_dynamic_lights([])
        self.fx.update(dt, self.camera)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the emptied clearing behind the results."""
        if not self.is_visible or self.fx is None or self.camera is None:
            return

        self.fx.draw_ground(world_renderer)
        self.fx.sparks.render(world_renderer, self.fx.offset)
        world_renderer.end_frame()

        # In the world buffer, for the same reason the menu's title is --
        # see `MenuScene.render`.
        world_renderer.draw_text(
            "PROTOCOLO ENCERRADO",
            Vector2(WINDOW_WIDTH / 2 - 206, 150),
            render.HEALTH_FULL,
            size=40,
        )
        world_renderer.draw_text(
            f"SCORE {self._final_score:07d}",
            Vector2(WINDOW_WIDTH / 2 - 92, 226),
            render.TEXT,
            size=24,
        )
        world_renderer.draw_text(
            f"HI {_high_score:07d}    KILLS {self._total_kills}",
            Vector2(WINDOW_WIDTH / 2 - 108, 260),
            render.DUST_PALE,
            size=18,
        )

        self.fx.run_pipeline(self.camera)
