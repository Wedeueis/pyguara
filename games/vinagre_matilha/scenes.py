"""Vinagre: Matilha - Game Scenes.

Menu (stage select) and gameplay scenes. Every game-specific system is
registered on `self.system_manager` alongside the engine's own Steering/AI
systems (see `pyguara.scene.base.Scene.resolve_dependencies`) rather than
ticked by hand -- `SceneManager` already calls `scene.system_manager.
update(fixed_dt)` once a tick for every active scene, so registering here is
enough; `fixed_update()`/`update()` below only handle input and rendering.
"""

from __future__ import annotations

import sys

from games.vinagre_matilha.components import JaguarState, LogGate, PressurePlate
from games.vinagre_matilha.events import JaguarCorneredEvent
from games.vinagre_matilha.level_builder import (
    CELL_SIZE,
    STAGES,
    StageConfig,
    build_stage,
)
from games.vinagre_matilha.systems import (
    CurrentZoneSystem,
    FlankerAssignmentSystem,
    JaguarAISystem,
    PressurePlateSystem,
    VanguardControlSystem,
)
from pyguara.ai.flocking_system import FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import ESCAPE, NUM_1, NUM_2, NUM_3, A, D, S, W
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.pack import PackCommand, PackMember, PackRole, issue_command
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.trigger_system import TriggerSystem
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.components.button import Button
from pyguara.ui.components.text import Label
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640

_COLOR_BACKGROUND = Color(46, 58, 35)
_COLOR_WALL = Color(30, 38, 22)
_COLOR_WATER = Color(60, 110, 140, 160)
_COLOR_LOG = Color(90, 60, 30)
_COLOR_PLATE_CLOSED = Color(120, 100, 60)
_COLOR_PLATE_OPEN = Color(90, 160, 90)
_COLOR_CORNER_ZONE = Color(200, 180, 60)
_COLOR_VANGUARD = Color(230, 130, 40)
_COLOR_FLANKER = Color(160, 100, 60)
_COLOR_JAGUAR = Color(210, 60, 40)
_COLOR_JAGUAR_CORNERED = Color(255, 220, 40)

# Priority band: SystemManager runs lower numbers first. The engine's own
# AISystem (200, ticks the pack's behavior trees) is registered by
# Scene.resolve_dependencies(); everything below is placed relative to it.
# (The engine's SteeringSystem (150) is also registered, but unused here --
# see JaguarAISystem's docstring for why the jaguar integrates its own flee.)
_PRIORITY_TRIGGER_SETUP = 90
_PRIORITY_VANGUARD = 110
_PRIORITY_JAGUAR_AI = 120
_PRIORITY_FLANKER_ASSIGNMENT = 175
# [engine] AISystem = 200
_PRIORITY_FLOCKING = 220
_PRIORITY_PHYSICS = 230
_PRIORITY_CURRENT_ZONE = 240
_PRIORITY_PRESSURE_PLATE = 245
# [engine] AudioSourceSystem = 250, AnimationSystem = 300


class MenuScene(Scene):
    """Stage-select title screen."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialize the menu scene."""
        super().__init__("MenuScene", event_dispatcher)

    def on_enter(self) -> None:
        """Build the stage-select UI."""
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        ui_manager.add_element(Label("VINAGRE: MATILHA", position=Vector2(300, 80)))
        ui_manager.add_element(
            Label("Tactical Pack Action!", position=Vector2(340, 120))
        )

        container = BoxContainer(
            position=Vector2(340, 220), size=Vector2(280, 260), spacing=15
        )
        for index, stage in enumerate(STAGES):
            button = Button(
                f"{index + 1}. {stage.name}",
                position=Vector2(0, 0),
                size=Vector2(280, 50),
            )
            button.on_click = self._make_stage_starter(stage)
            container.add_child(button)

        quit_button = Button("QUIT", position=Vector2(0, 0), size=Vector2(280, 50))
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

    def on_resume(self) -> None:
        """Recreate the UI when returning from a stage."""
        self.on_enter()

    def update(self, dt: float) -> None:
        """No per-frame menu logic."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Clear to the background color; the UI layer draws the buttons."""
        world_renderer.clear(_COLOR_BACKGROUND)


class GameScene(Scene):
    """One stage of pack-tactics gameplay."""

    def __init__(self, event_dispatcher: EventDispatcher, stage: StageConfig) -> None:
        """Initialize the game scene for `stage`."""
        super().__init__("GameScene", event_dispatcher)
        self._stage = stage
        self._input_manager: InputManager | None = None
        self._vanguard_control: VanguardControlSystem | None = None
        self._move_up = False
        self._move_down = False
        self._move_left = False
        self._move_right = False
        self._stage_cleared = False

    def on_enter(self) -> None:
        """Build the level, construct systems, and wire input/events."""
        ui_manager = self.container.get(UIManager)
        ui_manager._root_elements.clear()

        self._input_manager = self.container.get(InputManager)
        self._setup_input()

        self._level = build_stage(self.entity_manager, self._stage)

        physics_engine = self.container.get(IPhysicsEngine)  # type: ignore[type-abstract]

        self._vanguard_control = VanguardControlSystem(
            self.entity_manager, self._level.graph, self._level.vanguard_id
        )

        self.system_manager.register(
            TriggerSystem(self.entity_manager, self.event_dispatcher),
            priority=_PRIORITY_TRIGGER_SETUP,
        )
        self.system_manager.register(
            self._vanguard_control, priority=_PRIORITY_VANGUARD
        )
        self.system_manager.register(
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
        self.system_manager.register(
            FlankerAssignmentSystem(
                self.entity_manager,
                self._level.blackboard,
                self._level.flow_field,
                self._level.jaguar_id,
            ),
            priority=_PRIORITY_FLANKER_ASSIGNMENT,
        )
        self.system_manager.register(
            FlockingSystem(self.entity_manager), priority=_PRIORITY_FLOCKING
        )
        self.system_manager.register(
            PhysicsSystem(
                engine=physics_engine,
                entity_manager=self.entity_manager,
                event_dispatcher=self.event_dispatcher,
                gravity=Vector2(0, 0),
            ),
            priority=_PRIORITY_PHYSICS,
        )
        self.system_manager.register(
            CurrentZoneSystem(self.entity_manager), priority=_PRIORITY_CURRENT_ZONE
        )
        self.system_manager.register(
            PressurePlateSystem(
                self.entity_manager, self._level.graph, self.event_dispatcher
            ),
            priority=_PRIORITY_PRESSURE_PLATE,
        )

        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)
        self.event_dispatcher.subscribe(JaguarCorneredEvent, self._on_jaguar_cornered)

        self._setup_hud()

    def on_exit(self) -> None:
        """Unsubscribe this stage's event handlers."""
        self.event_dispatcher.unsubscribe(OnActionEvent, self._on_action)
        self.event_dispatcher.unsubscribe(JaguarCorneredEvent, self._on_jaguar_cornered)

    def _setup_input(self) -> None:
        assert self._input_manager is not None
        im = self._input_manager
        im.register_action("move_up", ActionType.HOLD)
        im.register_action("move_down", ActionType.HOLD)
        im.register_action("move_left", ActionType.HOLD)
        im.register_action("move_right", ActionType.HOLD)
        im.register_action("command_scatter", ActionType.PRESS)
        im.register_action("command_pincer", ActionType.PRESS)
        im.register_action("command_distract", ActionType.PRESS)
        im.register_action("back", ActionType.PRESS)

        im.bind_input(InputDevice.KEYBOARD, W, "move_up")
        im.bind_input(InputDevice.KEYBOARD, S, "move_down")
        im.bind_input(InputDevice.KEYBOARD, A, "move_left")
        im.bind_input(InputDevice.KEYBOARD, D, "move_right")
        im.bind_input(InputDevice.KEYBOARD, NUM_1, "command_scatter")
        im.bind_input(InputDevice.KEYBOARD, NUM_2, "command_pincer")
        im.bind_input(InputDevice.KEYBOARD, NUM_3, "command_distract")
        im.bind_input(InputDevice.KEYBOARD, ESCAPE, "back")

    def _on_action(self, event: OnActionEvent) -> None:
        is_pressed = event.value > 0
        if event.action_name == "move_up":
            self._move_up = is_pressed
        elif event.action_name == "move_down":
            self._move_down = is_pressed
        elif event.action_name == "move_left":
            self._move_left = is_pressed
        elif event.action_name == "move_right":
            self._move_right = is_pressed
        elif event.action_name == "command_scatter" and is_pressed:
            issue_command(self._level.blackboard, PackCommand.SCATTER)
        elif event.action_name == "command_pincer" and is_pressed:
            issue_command(self._level.blackboard, PackCommand.PINCER)
        elif event.action_name == "command_distract" and is_pressed:
            issue_command(self._level.blackboard, PackCommand.DISTRACT)
        elif event.action_name == "back" and is_pressed:
            self.container.get(SceneManager).switch_to("MenuScene")

    def _on_jaguar_cornered(self, _event: JaguarCorneredEvent) -> None:
        self._stage_cleared = True
        self.system_manager.set_enabled(False)

    def _setup_hud(self) -> None:
        ui_manager = self.container.get(UIManager)
        ui_manager.add_element(
            Label(
                f"{self._stage.name} -- 1:Scatter 2:Pincer 3:Distract  ESC:Menu",
                position=Vector2(16, 8),
            )
        )

    def update(self, dt: float) -> None:
        """Compute the Vanguard's move direction from held keys."""
        if self._vanguard_control is None:
            return
        x = (1.0 if self._move_right else 0.0) - (1.0 if self._move_left else 0.0)
        y = (1.0 if self._move_down else 0.0) - (1.0 if self._move_up else 0.0)
        self._vanguard_control.move_direction = Vector2(x, y)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the stage as tinted primitives -- placeholder art, real subsystems."""
        world_renderer.clear(_COLOR_BACKGROUND)

        for rect in self._stage.wall_rects:
            world_renderer.draw_rect(rect, _COLOR_WALL)

        for rect in self._stage.water_zones:
            world_renderer.draw_rect(rect, _COLOR_WATER)
            center = rect.center_vec
            direction = self._level.flow_field.vector_at(center, CELL_SIZE)
            if direction.length > 0.001:
                world_renderer.draw_line(
                    center, center + direction * 24.0, Color(230, 230, 255), width=2
                )

        if any(self.entity_manager.get_entities_with(LogGate)):
            if self._stage.log_rect is not None:
                world_renderer.draw_rect(self._stage.log_rect, _COLOR_LOG)

        for plate_entity in self.entity_manager.get_entities_with(PressurePlate):
            plate = plate_entity.get_component(PressurePlate)
            if self._stage.plate_rect is not None:
                color = _COLOR_PLATE_OPEN if plate.opened else _COLOR_PLATE_CLOSED
                world_renderer.draw_rect(self._stage.plate_rect, color)

        world_renderer.draw_rect(self._stage.corner_zone, _COLOR_CORNER_ZONE, width=2)

        for dog in self.entity_manager.get_entities_with(PackMember, Transform):
            member = dog.get_component(PackMember)
            position = dog.get_component(Transform).position
            color = (
                _COLOR_VANGUARD if member.role is PackRole.VANGUARD else _COLOR_FLANKER
            )
            world_renderer.draw_circle(position, 9.0, color)

        jaguar = self.entity_manager.get_entity(self._level.jaguar_id)
        if jaguar is not None:
            state = jaguar.get_component(JaguarState)
            color = _COLOR_JAGUAR_CORNERED if state.cornered else _COLOR_JAGUAR
            world_renderer.draw_circle(
                jaguar.get_component(Transform).position, 15.0, color
            )

        if self._stage_cleared:
            world_renderer.draw_text(
                "STAGE CLEARED -- press ESC for the menu",
                Vector2(280, WINDOW_HEIGHT // 2),
                Color(255, 255, 255),
                size=24,
            )
