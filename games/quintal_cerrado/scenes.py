"""Quintal do Cerrado - Scenes.

`TitleScene` is a minimal reuse of the design-system pattern
`guara_falcao` already established (`BevelPanel`/`BevelButton`, a
centred column, `set_focus` on the first button) -- this demo's showcase
is the grid and persistence, not the menu, so the title screen stays
small on purpose.

`GardenScene` owns the plot: a `T`/`P` tool selector (till/plant), and a
`GardenGridCanvas` that turns a click into the active tool's action. No
growth, no companion bonuses, no persistence yet -- Phase 1 proves the
grid and the click-to-cell input path; later phases build on `GardenGrid`
without touching how a click reaches it.
"""

from __future__ import annotations

from games.quintal_cerrado import art
from games.quintal_cerrado.bootstrap import WINDOW_HEIGHT, WINDOW_WIDTH
from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import (
    GRID_HEIGHT,
    GRID_WIDTH,
    TILE_SIZE,
    GardenGrid,
)
from games.quintal_cerrado.garden_widget import GardenGridCanvas
from pyguara.common.grid import Cell
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import P, T
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import TextAlign, UILayer

TOOL_LABELS = {"till": "Tool: Till (T)", "plant": "Tool: Plant Guandu (P)"}


class TitleScene(Scene):
    """The title screen: a plate and a Play button, over the world backdrop."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialize the title scene."""
        super().__init__("TitleScene", event_dispatcher)

    def on_enter(self) -> None:
        """Build the menu."""
        self._build_menu()

    def on_resume(self) -> None:
        """Rebuild the menu after returning from the game."""
        super().on_resume()
        self._build_menu()

    def _build_menu(self) -> None:
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        plate_width, plate_height = 440, 120
        plate_x = (WINDOW_WIDTH - plate_width) // 2
        plate = BevelPanel(
            Vector2(plate_x, 96), Vector2(plate_width, plate_height), border_width=3
        )
        plate.add_child(
            Label(
                "QUINTAL DO CERRADO",
                Vector2(plate_x, 130),
                font_size=32,
                width=plate_width,
                align=TextAlign.CENTER,
            )
        )
        plate.add_child(
            Label(
                "PYGUARA SOLAR ENGINE",
                Vector2(plate_x, 176),
                font_size=14,
                width=plate_width,
                align=TextAlign.CENTER,
            )
        )
        ui_manager.add_element(plate, UILayer.CONTENT)

        column = BoxContainer(
            Vector2((WINDOW_WIDTH - 240) // 2, 280), Vector2(240, 56), spacing=14
        )
        button = BevelButton("Play", Vector2(0, 0), Vector2(240, 52), skin=Skins.SAGE)
        button.on_click = self._on_play
        column.add_child(button)
        ui_manager.add_element(column, UILayer.CONTENT)

        ui_manager.set_focus(button)

    def _on_play(self, _element: object) -> None:
        scene_manager = self.container.get(SceneManager)
        scene_manager.register(GardenScene(self.event_dispatcher))
        scene_manager.push_scene("GardenScene")

    def on_exit(self) -> None:
        """Nothing to clean up."""

    def update(self, dt: float) -> None:
        """Nothing animates yet."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Clear to the world backdrop; the menu is UI on top of it."""
        world_renderer.clear(art.WORLD_BACKDROP)


class GardenScene(Scene):
    """The garden: the grid, the tool selector, and click-to-till/plant."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialize the garden scene."""
        super().__init__("GardenScene", event_dispatcher)
        self.grid = GardenGrid()
        self._canvas: GardenGridCanvas | None = None
        self._tool_label: Label | None = None
        self._active_tool = "till"

    def on_enter(self) -> None:
        """Build the grid widget and wire tool-select input."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        self._setup_input()
        self._build_grid_widget(ui_manager)

    def _build_grid_widget(self, ui_manager: UIManager) -> None:
        grid_width_px = GRID_WIDTH * TILE_SIZE
        grid_height_px = GRID_HEIGHT * TILE_SIZE
        origin = Vector2(
            (WINDOW_WIDTH - grid_width_px) // 2, (WINDOW_HEIGHT - grid_height_px) // 2
        )
        self._canvas = GardenGridCanvas(origin, self.grid, self.entity_manager)
        self._canvas.on_cell_clicked = self._on_cell_clicked
        ui_manager.add_element(self._canvas, UILayer.CONTENT)

        self._tool_label = Label(
            TOOL_LABELS[self._active_tool],
            Vector2(origin.x, origin.y - 28),
            font_size=16,
        )
        ui_manager.add_element(self._tool_label, UILayer.CONTENT)

    def _setup_input(self) -> None:
        input_manager = self.container.get(InputManager)
        input_manager.register_action("tool_till", ActionType.PRESS)
        input_manager.register_action("tool_plant", ActionType.PRESS)
        input_manager.bind_input(InputDevice.KEYBOARD, T, "tool_till")
        input_manager.bind_input(InputDevice.KEYBOARD, P, "tool_plant")
        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        if self.container.get(SceneManager).current_scene is not self:
            return
        if event.value <= 0:
            return
        if event.action_name == "tool_till":
            self._set_active_tool("till")
        elif event.action_name == "tool_plant":
            self._set_active_tool("plant")

    def _set_active_tool(self, tool: str) -> None:
        self._active_tool = tool
        if self._tool_label is not None:
            self._tool_label.set_text(TOOL_LABELS[tool])

    def _on_cell_clicked(self, cell: Cell) -> None:
        if self._active_tool == "till":
            self.grid.till(cell)
        elif self._active_tool == "plant":
            self._plant_guandu(cell)

    def _plant_guandu(self, cell: Cell) -> None:
        if not self.grid.can_plant(cell):
            return
        entity = self.entity_manager.create_entity()
        entity.add_component(PlantComponent(species_id="guandu"))
        self.grid.mark_planted(cell, entity.id)

    def on_exit(self) -> None:
        """Nothing to clean up yet."""

    def update(self, dt: float) -> None:
        """No simulation systems yet."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Clear the world; the grid itself draws as UI (`GardenGridCanvas`)."""
        world_renderer.clear(art.WORLD_BACKDROP)
