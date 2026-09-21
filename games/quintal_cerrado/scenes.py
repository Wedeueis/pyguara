"""Quintal do Cerrado - Scenes.

`TitleScene` is a minimal reuse of the design-system pattern
`guara_falcao` already established (`BevelPanel`/`BevelButton`, a
centred column, `set_focus` on the first button) -- this demo's showcase
is the grid and persistence, not the menu, so the title screen stays
small on purpose.

`GardenScene` owns the plot: a tool selector (till, plus one plant tool per
species) and a `GardenGridCanvas` that turns a click into the active
tool's action. Three simulation systems run every fixed tick --
`ShadeSystem`, `SyntropicSystem`, `PlantGrowthSystem`, in that priority
order (`_SHADE_PRIORITY`=500, `_SYNTROPIC_PRIORITY`=510,
`_GROWTH_PRIORITY`=520) -- registered on `self.system_manager`, which
`SceneManager.fixed_update()` already calls
automatically for every active scene alongside the engine's own
`AISystem`. No persistence, no pest fork, no economy yet -- those are
later phases; this one builds on Phase 1's `GardenGrid` without touching
how a click reaches it.
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
from games.quintal_cerrado.plant_states import build_plant_ai
from games.quintal_cerrado.systems.plant_growth_system import PlantGrowthSystem
from games.quintal_cerrado.systems.shade_system import ShadeSystem
from games.quintal_cerrado.systems.syntropic_system import SyntropicSystem
from pyguara.common.grid import Cell
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import B, C, G, T
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import TextAlign, UILayer

# Game systems must register at >=500 (pyguara/scene/base.py's
# GAME_SYSTEM_PRIORITY_MIN) to stay clear of the engine's own reserved band
# (100-399, e.g. AISystem at 200). Ascending order = update order: shade
# before the companion bonus that reads it, before growth that reads that.
_SHADE_PRIORITY = 500
_SYNTROPIC_PRIORITY = 510
_GROWTH_PRIORITY = 520

TOOL_LABELS = {
    "till": "Tool: Till (T)",
    "plant_guandu": "Tool: Plant Guandu (G)",
    "plant_cagaita": "Tool: Plant Cagaita (C)",
    "plant_baru": "Tool: Plant Baru (B)",
}

_PLANT_TOOL_KEYS = {
    "plant_guandu": G,
    "plant_cagaita": C,
    "plant_baru": B,
}


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
        """Build the grid widget, wire tool-select input, register systems."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        self._setup_input()
        self._build_grid_widget(ui_manager)
        self._register_systems()

    def _register_systems(self) -> None:
        self.system_manager.register(
            ShadeSystem(self.entity_manager, self.grid),
            priority=_SHADE_PRIORITY,
            system_type=ShadeSystem,
        )
        self.system_manager.register(
            SyntropicSystem(self.entity_manager, self.grid),
            priority=_SYNTROPIC_PRIORITY,
            system_type=SyntropicSystem,
        )
        self.system_manager.register(
            PlantGrowthSystem(self.entity_manager, self.grid),
            priority=_GROWTH_PRIORITY,
            system_type=PlantGrowthSystem,
        )

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
        input_manager.bind_input(InputDevice.KEYBOARD, T, "tool_till")
        for tool, key in _PLANT_TOOL_KEYS.items():
            input_manager.register_action(tool, ActionType.PRESS)
            input_manager.bind_input(InputDevice.KEYBOARD, key, tool)
        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        if self.container.get(SceneManager).current_scene is not self:
            return
        if event.value <= 0:
            return
        if event.action_name == "tool_till":
            self._set_active_tool("till")
        elif event.action_name in _PLANT_TOOL_KEYS:
            self._set_active_tool(event.action_name)

    def _set_active_tool(self, tool: str) -> None:
        self._active_tool = tool
        if self._tool_label is not None:
            self._tool_label.set_text(TOOL_LABELS[tool])

    def _on_cell_clicked(self, cell: Cell) -> None:
        if self._active_tool == "till":
            if self.grid.till(cell) and self._canvas is not None:
                self._canvas.celebrate_till(cell)
        elif self._active_tool.startswith("plant_"):
            species_id = self._active_tool.removeprefix("plant_")
            self._plant(cell, species_id)

    def _plant(self, cell: Cell, species_id: str) -> None:
        if not self.grid.can_plant(cell):
            return
        entity = self.entity_manager.create_entity()
        entity.add_component(PlantComponent(species_id=species_id))
        entity.add_component(build_plant_ai(entity))
        self.grid.mark_planted(cell, entity.id)

    def on_exit(self) -> None:
        """Nothing to clean up yet."""

    def update(self, dt: float) -> None:
        """No scene-level animation; the grid widget drives its own juice."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Clear the world; the grid itself draws as UI (`GardenGridCanvas`)."""
        world_renderer.clear(art.WORLD_BACKDROP)
