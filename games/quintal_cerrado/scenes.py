"""Quintal do Cerrado - Scenes.

`TitleScene` is a minimal reuse of the design-system pattern
`guara_falcao` already established (`BevelPanel`/`BevelButton`, a
centred column, `set_focus` on the first button) -- this demo's showcase
is the grid and persistence, not the menu, so the title screen stays
small on purpose.

`GardenScene` owns the plot: a clickable, two-row tool bar (actions on
one row, one seed per species on the other -- every tool also has a
keyboard shortcut, but the bar is what makes them discoverable) and a
`GardenGridCanvas` that turns a grid click into the active tool's action.
Six simulation systems run every fixed tick -- `SoilSystem`,
`AutomationSystem`, `ShadeSystem`, `SyntropicSystem`, `PestSystem`,
`PlantGrowthSystem`, in that priority order (see the `_*_PRIORITY` constants) -- registered on
`self.system_manager`, which `SceneManager.fixed_update()` already calls
automatically for every active scene alongside the engine's own
`AISystem`.

Two entities besides the plants live in the scene's world: `player`,
carrying `PlayerEconomy`, and `garden_conditions`, carrying
`GardenConditions` and the FSM (`garden_states.py`) that paces pest
outbreaks. Seeds and treatments cost Sementes, and a harvest pays them
back -- double for an organically grown plant, half for one that was
ever sprayed (`economy.py`). That is the PRD's dilemma: the spray fixes an
outbreak at once, and the compost is what keeps the premium.

The store (`store.py`) is a scene pushed over this one. Buying a structure
puts it in the player's inventory and hands them a `build_<kind>` tool;
the next click on a free cell places it, and `AutomationSystem` takes over.
"""

from __future__ import annotations

from collections.abc import Callable

from games.quintal_cerrado import art, treatments
from games.quintal_cerrado.bootstrap import WINDOW_HEIGHT, WINDOW_WIDTH
from games.quintal_cerrado.components import (
    GardenConditions,
    PlantComponent,
    PlayerEconomy,
    spend_credits,
)
from games.quintal_cerrado.economy import COMPOST_COST, SPRAY_COST, sell_harvest
from games.quintal_cerrado.events import (
    OutbreakResolvedEvent,
    OutbreakStartedEvent,
    PlantHarvestedEvent,
    SolarIncomeEvent,
)
from games.quintal_cerrado.garden_grid import (
    GRID_HEIGHT,
    GRID_WIDTH,
    TILE_SIZE,
    GardenGrid,
)
from games.quintal_cerrado.garden_states import build_conditions_ai
from games.quintal_cerrado.garden_widget import (
    GAIN_COLOR,
    WARN_COLOR,
    GardenGridCanvas,
)
from games.quintal_cerrado.hud import Hud
from games.quintal_cerrado.plant_states import build_plant_ai
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.store import StoreOverlayScene
from games.quintal_cerrado.structures import STRUCTURE_TABLE, place_structure
from games.quintal_cerrado.systems.automation_system import AutomationSystem
from games.quintal_cerrado.systems.pest_system import PestSystem
from games.quintal_cerrado.systems.plant_growth_system import PlantGrowthSystem
from games.quintal_cerrado.systems.shade_system import ShadeSystem
from games.quintal_cerrado.systems.soil_system import SoilSystem
from games.quintal_cerrado.systems.syntropic_system import SyntropicSystem
from pyguara.common.grid import Cell
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import KEY_O, B, C, G, H, M, P, S, T, W
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import LayoutDirection, TextAlign, UILayer

# Game systems must register at >=500 (pyguara/scene/base.py's
# GAME_SYSTEM_PRIORITY_MIN) to stay clear of the engine's own reserved band
# (100-399, e.g. AISystem at 200). Ascending order = update order: soil
# moisture before shade, before the companion bonus that reads shade,
# before growth that reads both.
_SOIL_PRIORITY = 500
_AUTOMATION_PRIORITY = 505
_SHADE_PRIORITY = 510
_SYNTROPIC_PRIORITY = 520
_PEST_PRIORITY = 525
_GROWTH_PRIORITY = 530

# The tool bar's two rows, top to bottom: seeds, then actions. Each maps a
# tool id to its button's label; the order here is the row's left-to-right
# order.
_SEED_TOOLS = {
    "plant_guandu": "Guandu (G)",
    "plant_cagaita": "Cagaita (C)",
    "plant_baru": "Baru (B)",
    "plant_pequi": "Pequi (P)",
}
_ACTION_TOOLS = {
    "till": "Till (T)",
    "water": "Water (W)",
    "harvest": "Harvest (H)",
    "compost": "Compost (M)",
    "spray": "Spray (S)",
}
_TOOL_ROWS = (_SEED_TOOLS, _ACTION_TOOLS)

_TOOL_KEYS = {
    "till": T,
    "water": W,
    "harvest": H,
    "compost": M,
    "spray": S,
    "plant_guandu": G,
    "plant_cagaita": C,
    "plant_baru": B,
    "plant_pequi": P,
}

STORE_ACTION = "open_store"
"""Not a tool -- it has no active state -- so it is bound and handled apart
from `_TOOL_KEYS`, and its button is not in `_tool_buttons`."""

_TOOL_BAR_BUTTON_SIZE = Vector2(114, 34)
_TOOL_BAR_SPACING = 6
_TOOL_BAR_ROW_GAP = 6


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
    """The garden: the grid, the tool bar, and the whole farming loop."""

    def __init__(
        self, event_dispatcher: EventDispatcher, rng: RandomStream | None = None
    ) -> None:
        """Initialize the garden scene.

        Args:
            event_dispatcher: The game's dispatcher.
            rng: Randomness for picking where an outbreak starts. Pass a
                seeded stream for a reproducible one.
        """
        super().__init__("GardenScene", event_dispatcher)
        self.grid = GardenGrid()
        self.economy = PlayerEconomy()
        self.conditions = GardenConditions()
        self._rng = rng
        self._canvas: GardenGridCanvas | None = None
        self._hud: Hud | None = None
        self._tool_buttons: dict[str, BevelButton] = {}
        self._active_tool = "till"

    def on_enter(self) -> None:
        """Build the widgets and entities, wire input, register systems."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()

        self._setup_input()
        origin = self._build_grid_widget(ui_manager)
        self._build_tool_bar(ui_manager, origin)
        self._build_price_hint(ui_manager, origin)
        self._hud = Hud(ui_manager)
        self._create_entities()
        self._register_systems()

        self.event_dispatcher.subscribe(OutbreakStartedEvent, self._on_outbreak_started)
        self.event_dispatcher.subscribe(
            OutbreakResolvedEvent, self._on_outbreak_resolved
        )
        self.event_dispatcher.subscribe(PlantHarvestedEvent, self._on_drone_harvest)
        self.event_dispatcher.subscribe(SolarIncomeEvent, self._on_solar_income)

    def _create_entities(self) -> None:
        """The two non-plant entities: the player, and the garden's conditions."""
        player = self.entity_manager.create_entity("player")
        player.add_component(self.economy)

        garden = self.entity_manager.create_entity("garden_conditions")
        garden.add_component(self.conditions)
        garden.add_component(
            build_conditions_ai(
                garden,
                self.grid,
                self.entity_manager,
                self.event_dispatcher,
                self._rng,
            )
        )

    def _register_systems(self) -> None:
        self.system_manager.register(
            SoilSystem(self.grid), priority=_SOIL_PRIORITY, system_type=SoilSystem
        )
        self.system_manager.register(
            AutomationSystem(
                self.entity_manager, self.grid, self.economy, self.event_dispatcher
            ),
            priority=_AUTOMATION_PRIORITY,
            system_type=AutomationSystem,
        )
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
            PestSystem(self.entity_manager, self.grid),
            priority=_PEST_PRIORITY,
            system_type=PestSystem,
        )
        self.system_manager.register(
            PlantGrowthSystem(self.entity_manager, self.grid),
            priority=_GROWTH_PRIORITY,
            system_type=PlantGrowthSystem,
        )

    def _build_grid_widget(self, ui_manager: UIManager) -> Vector2:
        grid_width_px = GRID_WIDTH * TILE_SIZE
        grid_height_px = GRID_HEIGHT * TILE_SIZE
        # 16px below centre: the tool bar's two rows sit above the grid, and
        # the HUD panel in the top-left corner would otherwise clip the
        # leftmost button of the lower row.
        origin = Vector2(
            (WINDOW_WIDTH - grid_width_px) // 2,
            (WINDOW_HEIGHT - grid_height_px) // 2 + 16,
        )
        self._canvas = GardenGridCanvas(origin, self.grid, self.entity_manager)
        self._canvas.on_cell_clicked = self._on_cell_clicked
        ui_manager.add_element(self._canvas, UILayer.CONTENT)
        return origin

    def _build_tool_bar(self, ui_manager: UIManager, origin: Vector2) -> None:
        """Two rows of clickable tool buttons above the grid.

        Every tool also has a keyboard shortcut (`_TOOL_KEYS`), but a
        shortcut nothing on screen names is not discoverable -- this bar
        is what a player actually finds "water" and "harvest" through. The
        actions sit on the row nearest the grid, and the seeds above them.
        """
        row_height = int(_TOOL_BAR_BUTTON_SIZE.y)
        for row_index, tools in enumerate(reversed(_TOOL_ROWS)):
            has_store = tools is _ACTION_TOOLS
            count = len(tools) + (1 if has_store else 0)
            width = count * _TOOL_BAR_BUTTON_SIZE.x + (count - 1) * _TOOL_BAR_SPACING
            position = Vector2(
                origin.x + (GRID_WIDTH * TILE_SIZE - width) / 2,
                origin.y
                - 12
                - (row_index + 1) * row_height
                - row_index * _TOOL_BAR_ROW_GAP,
            )
            row = BoxContainer(
                position,
                Vector2(width, row_height),
                direction=LayoutDirection.HORIZONTAL,
                spacing=_TOOL_BAR_SPACING,
            )
            for tool, label in tools.items():
                button = BevelButton(
                    label,
                    Vector2(0, 0),
                    _TOOL_BAR_BUTTON_SIZE,
                    skin=Skins.SAGE if tool == self._active_tool else Skins.GHOST,
                )
                button.on_click = self._tool_button_handler(tool)
                self._tool_buttons[tool] = button
                row.add_child(button)
            if has_store:
                store = BevelButton(
                    "Store (O)",
                    Vector2(0, 0),
                    _TOOL_BAR_BUTTON_SIZE,
                    skin=Skins.WOOD,
                )
                store.on_click = lambda _element: self._open_store()
                row.add_child(store)
            ui_manager.add_element(row, UILayer.CONTENT)

    def _build_price_hint(self, ui_manager: UIManager, origin: Vector2) -> None:
        """One line under the grid naming what everything costs.

        Built from `SPECIES_TABLE` and `economy.py` rather than typed out, so
        it cannot drift from what `_plant`/`_apply_*` actually charge.
        """
        seeds = "  ".join(
            f"{species.display_name} {species.seed_cost}"
            for species in SPECIES_TABLE.values()
        )
        hint = Label(
            f"Seeds: {seeds}   |   Compost {COMPOST_COST}   Spray {SPRAY_COST}",
            Vector2(origin.x, origin.y + GRID_HEIGHT * TILE_SIZE + 12),
            font_size=13,
        )
        ui_manager.add_element(hint, UILayer.CONTENT)

    def _tool_button_handler(self, tool: str) -> Callable[[object], None]:
        def _handler(_element: object) -> None:
            self._set_active_tool(tool)

        return _handler

    def _setup_input(self) -> None:
        input_manager = self.container.get(InputManager)
        for tool, key in _TOOL_KEYS.items():
            input_manager.register_action(tool, ActionType.PRESS)
            input_manager.bind_input(InputDevice.KEYBOARD, key, tool)
        input_manager.register_action(STORE_ACTION, ActionType.PRESS)
        input_manager.bind_input(InputDevice.KEYBOARD, KEY_O, STORE_ACTION)
        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        if self.container.get(SceneManager).current_scene is not self:
            return
        if event.value <= 0:
            return
        if event.action_name in _TOOL_KEYS:
            self._set_active_tool(event.action_name)
        elif event.action_name == STORE_ACTION:
            self._open_store()

    def _set_active_tool(self, tool: str) -> None:
        self._active_tool = tool
        for tool_name, button in self._tool_buttons.items():
            button.skin = Skins.SAGE if tool_name == tool else Skins.GHOST

    def _say(self, text: str) -> None:
        if self._hud is not None:
            self._hud.show_message(text)

    def _on_outbreak_started(self, event: OutbreakStartedEvent) -> None:
        if self._canvas is not None:
            self._canvas.flash_alert()
        self._say("Pests! Treat them")

    def _on_outbreak_resolved(self, event: OutbreakResolvedEvent) -> None:
        self._say(f"Pests gone ({event.method})")

    def _on_drone_harvest(self, event: PlantHarvestedEvent) -> None:
        if self._canvas is not None:
            self._canvas.celebrate_harvest(event.cell, event.species_id)
            self._canvas.spawn_label(event.cell, f"+{event.value}", GAIN_COLOR)

    def _on_solar_income(self, event: SolarIncomeEvent) -> None:
        if self._canvas is not None:
            self._canvas.spawn_label(event.cell, f"+{event.amount}", GAIN_COLOR)

    def _open_store(self) -> None:
        """Push the store over the garden, freezing it while the player shops."""
        scene_manager = self.container.get(SceneManager)
        if scene_manager.current_scene is not self:
            return
        scene_manager.register(
            StoreOverlayScene(
                self.event_dispatcher,
                self.economy,
                self._on_structure_bought,
                WINDOW_WIDTH,
                WINDOW_HEIGHT,
            )
        )
        scene_manager.push_scene("StoreOverlayScene", pause_below=True)

    def _on_structure_bought(self, kind: str) -> None:
        """The store has closed on a purchase: hand over the placement tool."""
        self._set_active_tool(f"build_{kind}")
        self._say(f"Place your {STRUCTURE_TABLE[kind].display_name}")

    def _build(self, cell: Cell, kind: str) -> None:
        """Place a structure from the inventory, and drop the tool when it runs out."""
        if (
            place_structure(self.grid, self.entity_manager, self.economy, kind, cell)
            != "ok"
        ):
            return
        if self._canvas is not None:
            self._canvas.celebrate_build(cell, kind)
        if self.economy.inventory.get(kind, 0) <= 0:
            self._set_active_tool("till")

    def _on_cell_clicked(self, cell: Cell) -> None:
        tool = self._active_tool
        if tool == "till":
            if self.grid.till(cell) and self._canvas is not None:
                self._canvas.celebrate_till(cell)
        elif tool == "water":
            if self.grid.water(cell) and self._canvas is not None:
                self._canvas.celebrate_water(cell)
        elif tool == "harvest":
            self._harvest(cell)
        elif tool == "compost":
            self._compost(cell)
        elif tool == "spray":
            self._spray(cell)
        elif tool.startswith("plant_"):
            self._plant(cell, tool.removeprefix("plant_"))
        elif tool.startswith("build_"):
            self._build(cell, tool.removeprefix("build_"))

    def _cant_afford(self, cell: Cell, cost: int) -> None:
        """Tell the player, at the cell they clicked, what they were short of."""
        if self._canvas is not None:
            self._canvas.spawn_label(cell, f"Need {cost}", WARN_COLOR)
        self._say("Not enough Sementes")

    def _plant(self, cell: Cell, species_id: str) -> None:
        species = SPECIES_TABLE.get(species_id)
        if species is None or not self.grid.can_plant(cell):
            return
        if not spend_credits(self.economy, species.seed_cost):
            self._cant_afford(cell, species.seed_cost)
            return
        entity = self.entity_manager.create_entity()
        entity.add_component(PlantComponent(species_id=species_id))
        entity.add_component(build_plant_ai(entity))
        self.grid.mark_planted(cell, entity.id)

    def _compost(self, cell: Cell) -> None:
        result = treatments.apply_compost(
            self.grid, self.economy, self.conditions, cell
        )
        if result == treatments.OK and self._canvas is not None:
            self._canvas.celebrate_compost(cell)
        elif result == treatments.BROKE:
            self._cant_afford(cell, COMPOST_COST)

    def _spray(self, cell: Cell) -> None:
        result = treatments.apply_spray(
            self.grid, self.entity_manager, self.economy, self.conditions, cell
        )
        if result == treatments.OK and self._canvas is not None:
            self._canvas.celebrate_spray(cell)
        elif result == treatments.BROKE:
            self._cant_afford(cell, SPRAY_COST)

    def _harvest(self, cell: Cell) -> None:
        """Sell a harvestable plant, or clear a dead one, freeing its cell.

        The cell stays tilled either way, ready to replant. An infested
        plant is refused -- treating the pests first is the point of the
        outbreak -- and a plant still growing is left alone.
        """
        entity_id = self.grid.plant_at.get(cell)
        if entity_id is None:
            return
        entity = self.entity_manager.get_entity(entity_id)
        if entity is None or not entity.has_component(PlantComponent):
            return
        plant = entity.get_component(PlantComponent)

        if plant.growth_stage == "infested":
            self._say("Treat the pests first")
            return
        if plant.growth_stage == "dying":
            self.entity_manager.remove_entity(entity_id)
            self.grid.unmark_planted(cell)
            if self._canvas is not None:
                self._canvas.spawn_label(cell, "Cleared", Color(190, 180, 168))
            return
        sold = sell_harvest(self.grid, self.entity_manager, self.economy, cell)
        if sold is None or self._canvas is None:
            return
        species_id, value = sold
        self._canvas.celebrate_harvest(cell, species_id)
        self._canvas.spawn_label(cell, f"+{value}", GAIN_COLOR)

    def on_exit(self) -> None:
        """Nothing to clean up yet."""

    def update(self, dt: float) -> None:
        """Refresh the HUD; the grid widget drives its own juice."""
        if self._hud is not None:
            self._hud.update(dt, self.economy, self.conditions)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Clear the world; the grid itself draws as UI (`GardenGridCanvas`)."""
        world_renderer.clear(art.WORLD_BACKDROP)
