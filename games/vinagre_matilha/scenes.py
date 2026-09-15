"""Vinagre: Matilha - Game Scenes.

Menu and gameplay scenes. Every rules system is registered on
`self.system_manager` alongside the engine's own Steering/AI systems (see
`pyguara.scene.base.Scene.resolve_dependencies`) rather than ticked by hand
-- `SceneManager` already calls `scene.system_manager.update(fixed_dt)`
once a tick for every active scene.

Presentation is deliberately kept out of the rules: `combat.py` dispatches
events, and everything cosmetic here (screen shake, particles, damage
numbers, hit-stop) is spawned by subscribing to them, so the fight's rules
can be tested headlessly with no renderer in sight.
"""

from __future__ import annotations

import sys

from games.vinagre_matilha import render
from games.vinagre_matilha.combat import (
    JaguarCombatSystem,
    PackCombatSystem,
    PackRecoverySystem,
)
from games.vinagre_matilha.components import DogState, JaguarPhase, JaguarState
from games.vinagre_matilha.events import (
    DogDownedEvent,
    GateOpenedEvent,
    JaguarDefeatedEvent,
    JaguarSwipedEvent,
    PackBitEvent,
    PackBrokenEvent,
)
from games.vinagre_matilha.level_builder import STAGES, StageConfig, build_stage
from games.vinagre_matilha.systems import (
    CurrentZoneSystem,
    FlankerAssignmentSystem,
    JaguarAISystem,
    PackContainmentSystem,
    PackMotionSystem,
    PressurePlateSystem,
    VanguardControlSystem,
)
from pyguara.ai.flocking_system import FlockingSystem
from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.floating_text import FloatingText
from pyguara.graphics.components.screen_flash import ScreenFlash
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import ESCAPE, NUM_1, NUM_2, NUM_3, A, D, R, S, W
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.action_combat import Health, HealthSystem
from pyguara.kits.pack import PackCommand, PackMember, issue_command
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.trigger_system import TriggerSystem
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.components.button import Button
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640
_VIEW_CENTRE = Vector2(WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2)

_UI_CREAM = Color(238, 226, 198)
_UI_DIM = Color(150, 142, 120)
_UI_PANEL = Color(18, 24, 16, 205)
_UI_ACCENT = Color(232, 150, 60)
_UI_DANGER = Color(236, 92, 66)
_UI_GOOD = Color(120, 196, 110)

# Priority band: SystemManager runs lower numbers first. The engine's own
# AISystem (200, ticks the pack's behavior trees) is registered by
# Scene.resolve_dependencies(); everything below is placed relative to it.
# (The engine's SteeringSystem (150) is also registered but unused here --
# see JaguarAISystem's docstring for why the jaguar integrates its own.)
_PRIORITY_TRIGGER_SETUP = 90
_PRIORITY_VANGUARD = 110
_PRIORITY_JAGUAR_AI = 120
_PRIORITY_FLANKER_ASSIGNMENT = 175
# [engine] AISystem = 200
_PRIORITY_FLOCKING = 220
_PRIORITY_PACK_MOTION = 225
_PRIORITY_PHYSICS = 230
_PRIORITY_CURRENT_ZONE = 240
_PRIORITY_PRESSURE_PLATE = 245
_PRIORITY_JAGUAR_COMBAT = 260
_PRIORITY_PACK_COMBAT = 265
_PRIORITY_PACK_RECOVERY = 270
# After combat, so a swipe's knockback is contained in the same tick it is
# applied rather than one frame later.
_PRIORITY_PACK_CONTAINMENT = 272
_PRIORITY_HEALTH = 275


class MenuScene(Scene):
    """Stage-select title screen."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialize the menu scene."""
        super().__init__("MenuScene", event_dispatcher)

    def on_enter(self) -> None:
        """Build the stage-select UI."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        container = BoxContainer(
            position=Vector2(340, 250), size=Vector2(280, 260), spacing=14
        )
        for index, stage in enumerate(STAGES):
            button = Button(
                f"{index + 1}. {stage.name}",
                position=Vector2(0, 0),
                size=Vector2(280, 48),
            )
            button.on_click = self._make_stage_starter(stage)
            container.add_child(button)

        quit_button = Button("QUIT", position=Vector2(0, 0), size=Vector2(280, 48))
        quit_button.on_click = self._on_quit_click
        container.add_child(quit_button)
        ui_manager.add_element(container)

    def _make_stage_starter(self, stage: StageConfig):
        def _start(_element: object) -> None:
            scene_manager = self.container.get(SceneManager)
            game_scene = GameScene(self.event_dispatcher, stage)
            scene_manager.register(game_scene)
            scene_manager.switch_to("GameScene")

        return _start

    def _on_quit_click(self, _element: object) -> None:
        sys.exit(0)

    def on_exit(self) -> None:
        """Nothing to clean up."""

    def update(self, dt: float) -> None:
        """No per-frame menu logic."""

    def on_resume(self) -> None:
        """Recreate the UI when returning from a stage."""
        self.on_enter()

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the title treatment behind the UI layer's buttons."""
        world_renderer.clear(render.BACKGROUND)
        world_renderer.draw_rect(Rect(0, 150, WINDOW_WIDTH, 96), Color(38, 52, 30))
        world_renderer.draw_text(
            "VINAGRE: MATILHA", Vector2(250, 168), _UI_ACCENT, size=46
        )
        world_renderer.draw_text(
            "TACTICAL PACK ACTION", Vector2(330, 214), _UI_CREAM, size=20
        )
        world_renderer.draw_text(
            "WASD lead the alpha   .   1 Scatter   2 Pincer   3 Distract",
            Vector2(232, 540),
            _UI_DIM,
            size=16,
        )
        world_renderer.draw_text(
            "Bite the jaguar down. When it rears up to swipe, Scatter -- then punish.",
            Vector2(176, 566),
            _UI_DIM,
            size=16,
        )


class GameScene(Scene):
    """One stage of pack-tactics gameplay."""

    def __init__(self, event_dispatcher: EventDispatcher, stage: StageConfig) -> None:
        """Initialize the game scene for `stage`."""
        super().__init__("GameScene", event_dispatcher)
        self._stage = stage
        self._art = render.StageArtwork(stage)
        self._input_manager: InputManager | None = None
        self._vanguard_control: VanguardControlSystem | None = None
        self._move_up = False
        self._move_down = False
        self._move_left = False
        self._move_right = False

        self._elapsed = 0.0
        self._outcome: str | None = None
        self._command = PackCommand.NONE
        self._command_flash = 0.0
        self._hit_stop = 0.0
        self._floating = FloatingText(capacity=48)
        self._flash = ScreenFlash()
        # Used purely as a shake generator, not to move the view: every
        # stage is exactly window-sized, and a squad-tactics read wants the
        # whole corridor on screen at once rather than a following camera.
        #
        # Its position is re-pinned to `_VIEW_CENTRE` every frame before
        # `update()` because `Camera2D.update()` *adds* the shake offset
        # straight onto `position` and never takes it back off -- despite
        # the comment there claiming the shake "doesn't modify the base
        # position". Left as-is, a few shakes walk the camera off the level
        # permanently. Re-pinning makes each frame's offset come from a
        # known base, so the accumulation cannot happen.
        self._shake_camera = Camera2D(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._shake_camera.position = _VIEW_CENTRE

    # ---- lifecycle ----------------------------------------------------

    def on_enter(self) -> None:
        """Build the level, register systems, and wire input/events."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        self._input_manager = self.container.get(InputManager)
        self._setup_input()

        self._level = build_stage(self.entity_manager, self._stage)
        physics_engine = self.container.get(IPhysicsEngine)  # type: ignore[type-abstract]

        self._vanguard_control = VanguardControlSystem(
            self.entity_manager, self._level.graph, self._level.vanguard_id
        )

        register = self.system_manager.register
        register(
            TriggerSystem(self.entity_manager, self.event_dispatcher),
            priority=_PRIORITY_TRIGGER_SETUP,
        )
        register(self._vanguard_control, priority=_PRIORITY_VANGUARD)
        register(
            JaguarAISystem(
                self.entity_manager,
                self._level.graph,
                self._level.jaguar_id,
                self._level.corner_zone,
                self._level.required_capture_dogs,
                self.event_dispatcher,
            ),
            priority=_PRIORITY_JAGUAR_AI,
        )
        register(
            FlankerAssignmentSystem(
                self.entity_manager,
                self._level.blackboard,
                self._level.flow_field,
                self._level.jaguar_id,
            ),
            priority=_PRIORITY_FLANKER_ASSIGNMENT,
        )
        register(FlockingSystem(self.entity_manager), priority=_PRIORITY_FLOCKING)
        register(PackMotionSystem(self.entity_manager), priority=_PRIORITY_PACK_MOTION)
        register(
            PhysicsSystem(
                engine=physics_engine,
                entity_manager=self.entity_manager,
                event_dispatcher=self.event_dispatcher,
                gravity=Vector2(0, 0),
            ),
            priority=_PRIORITY_PHYSICS,
        )
        register(
            CurrentZoneSystem(self.entity_manager), priority=_PRIORITY_CURRENT_ZONE
        )
        register(
            PressurePlateSystem(
                self.entity_manager, self._level.graph, self.event_dispatcher
            ),
            priority=_PRIORITY_PRESSURE_PLATE,
        )
        register(
            JaguarCombatSystem(
                self.entity_manager,
                self._level.jaguar_id,
                self.event_dispatcher,
                self._stage.pack_break_threshold,
            ),
            priority=_PRIORITY_JAGUAR_COMBAT,
        )
        register(
            PackCombatSystem(
                self.entity_manager, self._level.jaguar_id, self.event_dispatcher
            ),
            priority=_PRIORITY_PACK_COMBAT,
        )
        register(
            PackRecoverySystem(self.entity_manager), priority=_PRIORITY_PACK_RECOVERY
        )
        register(
            PackContainmentSystem(self.entity_manager, self._level.graph),
            priority=_PRIORITY_PACK_CONTAINMENT,
        )
        register(HealthSystem(self.entity_manager), priority=_PRIORITY_HEALTH)

        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)
        self.event_dispatcher.subscribe(PackBitEvent, self._on_pack_bit)
        self.event_dispatcher.subscribe(JaguarSwipedEvent, self._on_jaguar_swiped)
        self.event_dispatcher.subscribe(DogDownedEvent, self._on_dog_downed)
        self.event_dispatcher.subscribe(PackBrokenEvent, self._on_pack_broken)
        self.event_dispatcher.subscribe(GateOpenedEvent, self._on_gate_opened)

    def on_exit(self) -> None:
        """Unsubscribe this stage's event handlers."""
        self.event_dispatcher.unsubscribe(OnActionEvent, self._on_action)
        self.event_dispatcher.unsubscribe(PackBitEvent, self._on_pack_bit)
        self.event_dispatcher.unsubscribe(JaguarSwipedEvent, self._on_jaguar_swiped)
        self.event_dispatcher.unsubscribe(DogDownedEvent, self._on_dog_downed)
        self.event_dispatcher.unsubscribe(PackBrokenEvent, self._on_pack_broken)
        self.event_dispatcher.unsubscribe(GateOpenedEvent, self._on_gate_opened)

    # ---- input --------------------------------------------------------

    def _setup_input(self) -> None:
        assert self._input_manager is not None
        im = self._input_manager
        for action in ("move_up", "move_down", "move_left", "move_right"):
            im.register_action(action, ActionType.HOLD)
        for action in (
            "command_scatter",
            "command_pincer",
            "command_distract",
            "restart",
            "back",
        ):
            im.register_action(action, ActionType.PRESS)

        im.bind_input(InputDevice.KEYBOARD, W, "move_up")
        im.bind_input(InputDevice.KEYBOARD, S, "move_down")
        im.bind_input(InputDevice.KEYBOARD, A, "move_left")
        im.bind_input(InputDevice.KEYBOARD, D, "move_right")
        im.bind_input(InputDevice.KEYBOARD, NUM_1, "command_scatter")
        im.bind_input(InputDevice.KEYBOARD, NUM_2, "command_pincer")
        im.bind_input(InputDevice.KEYBOARD, NUM_3, "command_distract")
        im.bind_input(InputDevice.KEYBOARD, R, "restart")
        im.bind_input(InputDevice.KEYBOARD, ESCAPE, "back")

    def _on_action(self, event: OnActionEvent) -> None:
        pressed = event.value > 0
        action = event.action_name
        if action == "move_up":
            self._move_up = pressed
        elif action == "move_down":
            self._move_down = pressed
        elif action == "move_left":
            self._move_left = pressed
        elif action == "move_right":
            self._move_right = pressed
        elif action == "command_scatter" and pressed:
            self._issue(PackCommand.SCATTER)
        elif action == "command_pincer" and pressed:
            self._issue(PackCommand.PINCER)
        elif action == "command_distract" and pressed:
            self._issue(PackCommand.DISTRACT)
        elif action == "restart" and pressed:
            self._restart()
        elif action == "back" and pressed:
            self.container.get(SceneManager).switch_to("MenuScene")

    def _issue(self, command: PackCommand) -> None:
        self._command = command
        self._command_flash = 0.45
        issue_command(self._level.blackboard, command)

    def _restart(self) -> None:
        scene_manager = self.container.get(SceneManager)
        scene_manager.register(GameScene(self.event_dispatcher, self._stage))
        scene_manager.switch_to("GameScene")

    # ---- juice (event-driven; rules code knows none of this) ----------

    def _on_pack_bit(self, event: PackBitEvent) -> None:
        self._floating.spawn(
            f"{int(event.damage)}",
            event.position,
            color=_UI_ACCENT if not event.was_punish else Color(255, 236, 140),
            size=18 if event.was_punish else 14,
            life=0.6,
        )
        if event.was_punish:
            self._shake_camera.shake(magnitude=5.0, duration=0.16)
            self._hit_stop = max(self._hit_stop, 0.045)

    def _on_jaguar_swiped(self, event: JaguarSwipedEvent) -> None:
        self._shake_camera.shake(magnitude=11.0 if event.hit else 5.0, duration=0.3)
        if event.hit:
            self._flash.trigger(Color(220, 70, 50, 110), duration=0.22)
            self._hit_stop = max(self._hit_stop, 0.09)
        else:
            self._floating.spawn(
                "WHIFF!", event.position, color=_UI_GOOD, size=20, life=0.8
            )

    def _on_dog_downed(self, event: DogDownedEvent) -> None:
        self._floating.spawn(
            "DOWN", event.position, color=_UI_DANGER, size=16, life=0.9
        )

    def _on_pack_broken(self, _event: PackBrokenEvent) -> None:
        if self._outcome is None:
            self._outcome = "lost"
            self._flash.trigger(Color(180, 40, 30, 150), duration=0.5)
            self.system_manager.set_enabled(False)

    def _on_gate_opened(self, _event: GateOpenedEvent) -> None:
        if self._stage.plate_rect is not None:
            self._floating.spawn(
                "LOG DOWN!",
                self._stage.plate_rect.center_vec,
                color=_UI_GOOD,
                size=20,
                life=1.4,
            )
        self._shake_camera.shake(magnitude=8.0, duration=0.4)

    # ---- frame --------------------------------------------------------

    def update(self, dt: float) -> None:
        """Drive the vanguard from held keys and advance presentation state."""
        self._elapsed += dt
        self._command_flash = max(0.0, self._command_flash - dt)
        self._floating.update(dt)
        self._flash.update(dt)
        self._shake_camera.position = _VIEW_CENTRE  # see __init__ for why
        self._shake_camera.update(dt)

        # Hit-stop: freeze the rules briefly on a heavy hit so it lands.
        # Presentation above still advances, which is what makes the pause
        # read as impact rather than as a dropped frame.
        if self._hit_stop > 0.0:
            self._hit_stop = max(0.0, self._hit_stop - dt)
            self.system_manager.set_enabled(False)
        elif self._outcome is None:
            self.system_manager.set_enabled(True)

        if self._outcome is None:
            self._check_win()
        if self._vanguard_control is None:
            return
        x = (1.0 if self._move_right else 0.0) - (1.0 if self._move_left else 0.0)
        y = (1.0 if self._move_down else 0.0) - (1.0 if self._move_up else 0.0)
        self._vanguard_control.move_direction = Vector2(x, y)

    def _check_win(self) -> None:
        jaguar = self.entity_manager.get_entity(self._level.jaguar_id)
        if jaguar is None or not jaguar.has_component(Health):
            return
        if jaguar.get_component(Health).is_alive:
            return
        self._outcome = "won"
        self.event_dispatcher.dispatch(JaguarDefeatedEvent())
        self._flash.trigger(Color(255, 236, 180, 120), duration=0.5)
        self._shake_camera.shake(magnitude=10.0, duration=0.5)
        self.system_manager.set_enabled(False)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the world, then the HUD."""
        offset = self._shake_camera.position - _VIEW_CENTRE

        render.draw_terrain(
            world_renderer, self._stage, self._art, offset, self._elapsed
        )
        render.draw_objectives(
            world_renderer, self._stage, self.entity_manager, offset, self._elapsed
        )
        render.draw_pack_bonds(world_renderer, self.entity_manager, offset)
        render.draw_pack(world_renderer, self.entity_manager, offset, self._elapsed)
        render.draw_jaguar(
            world_renderer,
            self.entity_manager,
            self._level.jaguar_id,
            offset,
            self._elapsed,
        )
        render.draw_health_bar(
            world_renderer, self.entity_manager, self._level.jaguar_id, offset
        )
        self._floating.render(world_renderer, self._shake_camera)
        self._flash.render(world_renderer, Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))
        self._draw_hud(world_renderer)

    # ---- HUD ----------------------------------------------------------

    def _draw_hud(self, renderer: IRenderer) -> None:
        renderer.draw_rect(Rect(0, 0, WINDOW_WIDTH, 46), _UI_PANEL)
        renderer.draw_text(self._stage.name.upper(), Vector2(16, 8), _UI_CREAM, size=20)
        renderer.draw_text(self._stage.briefing, Vector2(16, 28), _UI_DIM, size=13)

        self._draw_jaguar_meter(renderer)
        self._draw_pack_meter(renderer)
        self._draw_commands(renderer)

        if self._outcome is not None:
            self._draw_outcome(renderer)

    def _draw_jaguar_meter(self, renderer: IRenderer) -> None:
        jaguar = self.entity_manager.get_entity(self._level.jaguar_id)
        if jaguar is None or not jaguar.has_component(Health):
            return
        health = jaguar.get_component(Health)
        state = jaguar.get_component(JaguarState)
        fraction = max(0.0, health.current / health.max_health)

        x, y, width = 330, 54, 300
        renderer.draw_rect(Rect(x - 2, y - 2, width + 4, 18), _UI_PANEL)
        renderer.draw_rect(
            Rect(x, y, int(width * fraction), 14),
            Color(206, 74, 52).lerp(Color(226, 186, 74), fraction),
        )
        label = "ONÇA"
        if state.phase is JaguarPhase.WINDUP:
            label = "ONÇA -- REARING UP!  [1] SCATTER"
        elif state.phase is JaguarPhase.RECOVER:
            label = "ONÇA -- STAGGERED!  PUNISH"
        elif state.cornered:
            label = "ONÇA -- CORNERED"
        color = (
            _UI_DANGER
            if state.phase is JaguarPhase.WINDUP
            else (_UI_GOOD if state.phase is JaguarPhase.RECOVER else _UI_CREAM)
        )
        renderer.draw_text(label, Vector2(x, y + 18), color, size=14)

    def _draw_pack_meter(self, renderer: IRenderer) -> None:
        dogs = list(self.entity_manager.get_entities_with(PackMember, DogState))
        ready = sum(1 for dog in dogs if not dog.get_component(DogState).is_downed)
        renderer.draw_text(
            f"PACK {ready}/{len(dogs)}", Vector2(16, 54), _UI_CREAM, size=16
        )
        for i, dog in enumerate(dogs):
            down = dog.get_component(DogState).is_downed
            renderer.draw_circle(
                Vector2(22 + i * 15, 82),
                5.0,
                render.DOG_DOWNED if down else render.DOG_BODY_VANGUARD,
            )
        broken_at = self._stage.pack_break_threshold
        renderer.draw_text(
            f"pack breaks at {broken_at} down", Vector2(16, 94), _UI_DIM, size=12
        )

    def _draw_commands(self, renderer: IRenderer) -> None:
        commands = (
            ("1 SCATTER", PackCommand.SCATTER),
            ("2 PINCER", PackCommand.PINCER),
            ("3 DISTRACT", PackCommand.DISTRACT),
        )
        for i, (label, command) in enumerate(commands):
            active = self._command is command
            x = WINDOW_WIDTH - 300 + i * 100
            box = Rect(x, 54, 92, 26)
            renderer.draw_rect(box, _UI_PANEL)
            if active:
                glow = _UI_ACCENT if self._command_flash <= 0 else Color(255, 236, 180)
                renderer.draw_rect(box, glow, width=2)
            renderer.draw_text(
                label,
                Vector2(x + 8, 60),
                _UI_CREAM if active else _UI_DIM,
                size=14,
            )

    def _draw_outcome(self, renderer: IRenderer) -> None:
        won = self._outcome == "won"
        # A banner, not a curtain: the final positions of the pack and the
        # jaguar are the most interesting thing on screen at this moment,
        # so the panel is kept narrow and off-centre rather than covering
        # the fight that produced it.
        renderer.draw_rect(Rect(250, 244, 460, 108), _UI_PANEL)
        renderer.draw_rect(
            Rect(250, 244, 460, 108), _UI_GOOD if won else _UI_DANGER, width=2
        )
        renderer.draw_text(
            "PREY DRIVEN OFF" if won else "THE PACK IS BROKEN",
            Vector2(292 if won else 276, 258),
            _UI_GOOD if won else _UI_DANGER,
            size=32,
        )
        renderer.draw_text(
            "The pack holds the bend." if won else "Too many down. Regroup.",
            Vector2(330, 298),
            _UI_CREAM,
            size=17,
        )
        renderer.draw_text(
            "[R] run it again     [ESC] menu",
            Vector2(340, 324),
            _UI_DIM,
            size=15,
        )
