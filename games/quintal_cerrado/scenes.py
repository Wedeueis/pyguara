"""Quintal do Cerrado - Scenes.

`TitleScene` is a minimal reuse of the design-system pattern
`guara_falcao` already established (`BevelPanel`/`BevelButton`, a
centred column, `set_focus` on the first button) -- this demo's showcase
is the grid and persistence, not the menu, so the title screen stays
small on purpose.

`GardenScene` owns the plot: an icon dock under it (`hud_widgets.ToolDock`
-- species, tools and the base, each slot naming its hotkey and its price,
so every keyboard shortcut is also discoverable) and a `GardenGridCanvas`
that turns a grid click into the active tool's action. Where each region
sits is `layout.py`'s.
Eight simulation systems run every fixed tick -- `SoilSystem`,
`AutomationSystem`, `ShadeSystem`, `SyntropicSystem`, `PestSystem`,
`PlantGrowthSystem`, `WeedSpreadSystem`, `WeatherSystem`, in that priority
order (see the `_*_PRIORITY` constants) -- registered on
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

The garden is saved through `pyguara.persistence` -- every 60 seconds of
play (`AutosaveSystem`), and whenever the scene exits, which is also what
closing the window does. The title screen's Continue loads it. The pause
menu (`pause.py`, Esc) and the evaluation (`evaluation.py`, which offers
itself at 15:00 of play) are overlays like the store.

The store (`store.py`) is a scene pushed over this one. Buying a structure
puts it in the player's inventory and hands them a `build_<kind>` tool;
the next click on a free cell places it, and `AutomationSystem` takes over.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from games.quintal_cerrado import art, layout, treatments
from games.quintal_cerrado.bootstrap import (
    BASE_VIGNETTE_INTENSITY,
    COLD_SNAP_VIGNETTE_INTENSITY,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from games.quintal_cerrado.clock import EVALUATION_TIME, darkness
from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    GardenConditions,
    PlantComponent,
    PlayerEconomy,
    consume_seed,
    specific_seed_key,
    spend_credits,
)
from games.quintal_cerrado.economy import (
    COMPOST_COST,
    CREDITS,
    GENERIC_SEED,
    SPRAY_COST,
    harvest_cell,
)
from games.quintal_cerrado.evaluation import EvaluationScene
from games.quintal_cerrado.events import (
    AutosavedEvent,
    OutbreakResolvedEvent,
    OutbreakStartedEvent,
    PlantHarvestedEvent,
    SolarIncomeEvent,
)
from games.quintal_cerrado.garden_grid import (
    GardenGrid,
)
from games.quintal_cerrado.garden_states import build_conditions_ai
from games.quintal_cerrado.garden_widget import (
    GAIN_COLOR,
    SFX_DENIED,
    SFX_OUTBREAK_RESOLVED,
    SFX_OUTBREAK_START,
    SFX_SOLAR_INCOME,
    WARN_COLOR,
    GardenGridCanvas,
)
from games.quintal_cerrado.hud import CellInspector, Hud, WeatherPanel
from games.quintal_cerrado.hud_widgets import DockGroup, SlotSpec, ToolDock, ToolSlot
from games.quintal_cerrado.pause import PauseScene
from games.quintal_cerrado.persistence_schema import (
    SAVE_KEY,
    SCHEMA_VERSION,
    SaveFormatError,
    apply_save_payload,
    to_save_payload,
)
from games.quintal_cerrado.plant_states import build_plant_ai
from games.quintal_cerrado.scoring import compute_score, soil_health
from games.quintal_cerrado.soil_health_effect import SoilHealthEffect
from games.quintal_cerrado.species import (
    SPECIES_TABLE,
    pick_generic_species,
)
from games.quintal_cerrado.store import StoreOverlayScene
from games.quintal_cerrado.structures import STRUCTURE_TABLE, place_structure
from games.quintal_cerrado.systems.automation_system import AutomationSystem
from games.quintal_cerrado.systems.autosave_system import AutosaveSystem
from games.quintal_cerrado.systems.pest_system import PestSystem
from games.quintal_cerrado.systems.plant_growth_system import PlantGrowthSystem
from games.quintal_cerrado.systems.shade_system import ShadeSystem
from games.quintal_cerrado.systems.soil_system import SoilSystem
from games.quintal_cerrado.systems.syntropic_system import SyntropicSystem
from games.quintal_cerrado.systems.weather_system import WeatherSystem
from games.quintal_cerrado.systems.weed_spread_system import WeedSpreadSystem
from games.quintal_cerrado.weather import WEATHER_TABLE, WeatherState
from pyguara.audio.manager import AudioManager
from pyguara.common.grid import Cell
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import ESCAPE, KEY_O, B, C, G, H, M, N, P, S, T, W
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.persistence.manager import PersistenceManager
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import TextAlign, UILayer

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
_WEED_SPREAD_PRIORITY = 535
# WeatherSystem reads nothing and only ever writes WeatherState -- it runs
# last, not first, despite SoilSystem/PestSystem/PlantGrowthSystem reading
# that state: game systems cannot register below 500, where SoilSystem
# already sits, so a condition change here is read by them one tick later
# instead. See weather_system.py's own module docstring for why that lag
# is the same one plant_growth_system.py already accepts for a stage
# transition, and just as imperceptible at 60Hz.
_WEATHER_PRIORITY = 536
_AUTOSAVE_PRIORITY = 590

SOIL_HEALTH_GRADE_STRENGTH = 0.3
"""How strongly `SoilHealthEffect` blends in once anything is tilled -- kept
modest on purpose: a mood over the frame, not a filter loud enough to fight
the soil's own colour (`art.draw_soil_tile`) for legibility."""

logger = logging.getLogger(__name__)

# The dock's three groups, left to right. Each tool id maps to its slot's
# Portuguese name, its key and that key's name; the icon is keyed by the
# tool id itself (`icons.ICONS`).
_SPECIES_TOOLS: dict[str, tuple[str, int, str]] = {
    "plant_guandu": ("Guandu", G, "G"),
    "plant_cagaita": ("Cagaita", C, "C"),
    "plant_baru": ("Baru", B, "B"),
    "plant_pequi": ("Pequi", P, "P"),
    "plant_generic": ("Genérica", N, "N"),
}
_ACTION_TOOLS: dict[str, tuple[str, int, str]] = {
    "till": ("Enxada", T, "T"),
    "water": ("Regador", W, "W"),
    "harvest": ("Colher", H, "H"),
    "compost": ("Adubo", M, "M"),
    "spray": ("Calda", S, "S"),
}

_TOOL_KEYS = {
    tool: key
    for table in (_SPECIES_TOOLS, _ACTION_TOOLS)
    for tool, (_label, key, _key_label) in table.items()
}

PAUSE_ACTION = "open_pause"
STORE_ACTION = "open_store"
"""Not a tool -- it has no active state -- so it is bound and handled apart
from `_TOOL_KEYS`, and its slot is not in `_tool_buttons`."""

STORE_SLOT = "store"
MENU_SLOT = "menu"


def _dock_groups() -> list[DockGroup]:
    def specs(table: dict[str, tuple[str, int, str]]) -> list[SlotSpec]:
        return [
            SlotSpec(tool, label, key_label)
            for tool, (label, _key, key_label) in table.items()
        ]

    return [
        DockGroup("ESPÉCIES", "plant_generic", specs(_SPECIES_TOOLS)),
        DockGroup("FERRAMENTAS", "till", specs(_ACTION_TOOLS)),
        DockGroup(
            "BASE",
            "store",
            [SlotSpec(STORE_SLOT, "Loja", "O"), SlotSpec(MENU_SLOT, "Menu", "Esc")],
        ),
    ]


def slot_status(tool: str, economy: PlayerEconomy) -> tuple[str, bool]:
    """What a tool's slot badge says, and whether the player can use it now.

    Mirrors what `GardenScene` actually charges, so the dock can never
    promise a price the click then disagrees with: a species spends its
    own stocked seed before Sementes (`_plant`), Generic spends only
    stocked generic seed (`_sow_generic`), and compost and spray cost
    their flat price (`treatments`). Every other tool is free.

    Args:
        tool: A tool id.
        economy: The player's economy.

    Returns:
        `(badge, affordable)` -- the badge is "" for a free tool.
    """
    if tool == "plant_generic":
        stock = economy.inventory.get(GENERIC_SEED_KEY, 0)
        return f"x{stock}", stock > 0
    if tool.startswith("plant_"):
        species_id = tool.removeprefix("plant_")
        stock = economy.inventory.get(specific_seed_key(species_id), 0)
        if stock > 0:
            return f"x{stock}", True
        species = SPECIES_TABLE.get(species_id)
        cost = species.seed_cost if species is not None else 0
        return str(cost), economy.credits >= cost
    if tool == "compost":
        return str(COMPOST_COST), economy.credits >= COMPOST_COST
    if tool == "spray":
        return str(SPRAY_COST), economy.credits >= SPRAY_COST
    return "", True


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

        has_save = (
            SAVE_KEY in self.container.get(PersistenceManager).storage.list_keys()
        )
        column = BoxContainer(
            Vector2((WINDOW_WIDTH - 240) // 2, 280), Vector2(240, 118), spacing=14
        )
        continue_button = BevelButton(
            "Continue",
            Vector2(0, 0),
            Vector2(240, 52),
            skin=Skins.SAGE if has_save else Skins.GHOST,
        )
        continue_button.set_enabled(has_save)
        continue_button.on_click = self._on_continue
        new_button = BevelButton(
            "New Garden",
            Vector2(0, 0),
            Vector2(240, 52),
            skin=Skins.WOOD if has_save else Skins.SAGE,
        )
        new_button.on_click = self._on_new
        column.add_child(continue_button)
        column.add_child(new_button)
        ui_manager.add_element(column, UILayer.CONTENT)

        ui_manager.set_focus(continue_button if has_save else new_button)

    def _on_continue(self, _element: object) -> None:
        self._start(load=True)

    def _on_new(self, _element: object) -> None:
        self._start(load=False)

    def _start(self, *, load: bool) -> None:
        scene_manager = self.container.get(SceneManager)
        scene_manager.register(GardenScene(self.event_dispatcher, load=load))
        scene_manager.push_scene("GardenScene")

    def on_exit(self) -> None:
        """Nothing to clean up."""

    def update(self, dt: float) -> None:
        """Nothing animates yet."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Clear to the world backdrop; the menu is UI on top of it.

        The post-process pass that grades this is not run from here:
        `Application` executes every render-graph pass itself, after all
        scenes have drawn.
        """
        world_renderer.clear(art.WORLD_BACKDROP)


class GardenScene(Scene):
    """The garden: the grid, the tool dock, and the whole farming loop."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        rng: RandomStream | None = None,
        *,
        load: bool = False,
    ) -> None:
        """Initialize the garden scene.

        Args:
            event_dispatcher: The game's dispatcher.
            rng: Randomness for picking where an outbreak starts. Pass a
                seeded stream for a reproducible one.
            load: Resume the saved garden instead of starting a new one.
        """
        super().__init__("GardenScene", event_dispatcher)
        self.grid = GardenGrid()
        self.economy = PlayerEconomy()
        self.conditions = GardenConditions()
        self.weather = WeatherState()
        self._rng = rng
        self._audio: AudioManager | None = None
        self._storm: StormEffect | None = None
        self._vignette: VignetteEffect | None = None
        self._soil_health_effect: SoilHealthEffect | None = None
        self._canvas: GardenGridCanvas | None = None
        self._hud: Hud | None = None
        self._weather_panel: WeatherPanel | None = None
        self._inspector: CellInspector | None = None
        self._tool_buttons: dict[str, ToolSlot] = {}
        self._store_button: ToolSlot | None = None
        self._menu_button: ToolSlot | None = None
        self._active_tool = "till"
        self._load_requested = load
        self.elapsed = 0.0
        """Seconds of play: advanced by `fixed_update`, so it stops while an
        overlay is up, and saved so Continue resumes the same day."""
        self._evaluation_offered = False

    def on_enter(self) -> None:
        """Build the widgets and entities, wire input, register systems."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()
        self._audio = self.container.get(AudioManager)
        self._storm = self.container.get(StormEffect)
        self._vignette = self.container.get(VignetteEffect)
        self._soil_health_effect = self.container.get(SoilHealthEffect)

        self._setup_input()
        self._build_grid_widget(ui_manager)
        self._build_dock(ui_manager)
        self._build_inspector(ui_manager)
        self._hud = Hud(
            ui_manager, layout.GRID_RECT.y + CellInspector.HEIGHT + layout.GAP
        )
        self._weather_panel = WeatherPanel(ui_manager)
        self._create_entities()
        self._register_systems()
        if self._load_requested:
            self._load()

        self.event_dispatcher.subscribe(OutbreakStartedEvent, self._on_outbreak_started)
        self.event_dispatcher.subscribe(
            OutbreakResolvedEvent, self._on_outbreak_resolved
        )
        self.event_dispatcher.subscribe(PlantHarvestedEvent, self._on_drone_harvest)
        self.event_dispatcher.subscribe(SolarIncomeEvent, self._on_solar_income)
        self.event_dispatcher.subscribe(AutosavedEvent, self._on_autosaved)

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
            SoilSystem(self.grid, self.weather),
            priority=_SOIL_PRIORITY,
            system_type=SoilSystem,
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
            PestSystem(self.entity_manager, self.grid, self.weather),
            priority=_PEST_PRIORITY,
            system_type=PestSystem,
        )
        self.system_manager.register(
            PlantGrowthSystem(self.entity_manager, self.grid, self.weather),
            priority=_GROWTH_PRIORITY,
            system_type=PlantGrowthSystem,
        )
        self.system_manager.register(
            WeedSpreadSystem(self.entity_manager, self.grid),
            priority=_WEED_SPREAD_PRIORITY,
            system_type=WeedSpreadSystem,
        )
        self.system_manager.register(
            WeatherSystem(self.weather),
            priority=_WEATHER_PRIORITY,
            system_type=WeatherSystem,
        )
        self.system_manager.register(
            AutosaveSystem(self.save_now, self.event_dispatcher),
            priority=_AUTOSAVE_PRIORITY,
            system_type=AutosaveSystem,
        )

    def _build_grid_widget(self, ui_manager: UIManager) -> None:
        """The plot, left of the right-hand column (`layout.GRID_ORIGIN`)."""
        self._canvas = GardenGridCanvas(
            layout.GRID_ORIGIN, self.grid, self.entity_manager, self._audio
        )
        self._canvas.on_cell_clicked = self._on_cell_clicked
        ui_manager.add_element(self._canvas, UILayer.CONTENT)

    def _build_dock(self, ui_manager: UIManager) -> None:
        """The icon dock under the grid: species, tools, and the base.

        Every tool also has a keyboard shortcut (`_TOOL_KEYS`), but a
        shortcut nothing on screen names is not discoverable -- the dock is
        what a player actually finds "water" and "harvest" through, and
        each slot's corner badge names its key. Costs sit on the slots
        themselves (`slot_status`), next to the thing they buy.
        """
        dock = ToolDock(_dock_groups(), WINDOW_WIDTH)
        for tool, slot in dock.slots.items():
            if tool == STORE_SLOT:
                slot.on_click = lambda _element: self._open_store()
                self._store_button = slot
            elif tool == MENU_SLOT:
                slot.on_click = lambda _element: self._open_pause()
                self._menu_button = slot
            else:
                slot.on_click = self._tool_button_handler(tool)
                slot.active = tool == self._active_tool
                self._tool_buttons[tool] = slot
        for group in dock.groups:
            ui_manager.add_element(group, UILayer.CONTENT)

    def _build_inspector(self, ui_manager: UIManager) -> None:
        """The hover inspector, at the top of the right-hand column."""
        self._inspector = CellInspector(
            ui_manager,
            Vector2(layout.COLUMN_X, layout.GRID_RECT.y),
            layout.COLUMN_WIDTH,
        )

    def _refresh_tool_slots(self) -> None:
        """Re-read every slot's badge and affordability from the economy."""
        for tool, slot in self._tool_buttons.items():
            slot.badge, slot.affordable = slot_status(tool, self.economy)

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
        input_manager.register_action(PAUSE_ACTION, ActionType.PRESS)
        input_manager.bind_input(InputDevice.KEYBOARD, ESCAPE, PAUSE_ACTION)
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
        elif event.action_name == PAUSE_ACTION:
            self._open_pause()

    def _set_active_tool(self, tool: str) -> None:
        self._active_tool = tool
        for tool_name, slot in self._tool_buttons.items():
            slot.active = tool_name == tool

    def _say(self, text: str) -> None:
        if self._hud is not None:
            self._hud.show_message(text)

    def save_now(self) -> bool:
        """Write the garden to disk.

        The payload is plain dicts and lists (see `persistence_schema.py`
        for why it must be), saved with the schema version so the engine's
        `MigrationManager` can tell one build's saves from another's.

        Returns:
            Whether the save was written.
        """
        payload = to_save_payload(
            self.grid, self.entity_manager, self.economy, self.conditions, self.elapsed
        )
        return self.container.get(PersistenceManager).save_data(
            SAVE_KEY, payload, save_version=SCHEMA_VERSION
        )

    def _load(self) -> None:
        """Resume the saved garden, or say why a new one started instead."""
        payload = self.container.get(PersistenceManager).load_data(SAVE_KEY)
        if payload is None:
            self._say("No usable save")
            return
        try:
            self.elapsed = apply_save_payload(
                payload, self.grid, self.entity_manager, self.economy, self.conditions
            )
        except SaveFormatError as error:
            logger.warning("Ignoring an unreadable save: %s", error)
            self._say("Save unreadable")
            return
        # Loading a session already past the evaluation must not re-offer it.
        self._evaluation_offered = self.elapsed >= EVALUATION_TIME
        self._say("Garden loaded")

    def _on_autosaved(self, event: AutosavedEvent) -> None:
        self._say("Garden saved" if event.success else "Autosave failed!")

    def _open_pause(self) -> None:
        """Push the pause menu over the garden."""
        scene_manager = self.container.get(SceneManager)
        if scene_manager.current_scene is not self:
            return
        scene_manager.register(
            PauseScene(
                self.event_dispatcher,
                self.save_now,
                self.open_evaluation,
                self._quit_to_title,
                WINDOW_WIDTH,
                WINDOW_HEIGHT,
            )
        )
        scene_manager.push_scene("PauseScene", pause_below=True)

    def open_evaluation(self) -> None:
        """Save, then show the Agroecological Score over the garden.

        Saved first, so what is scored is exactly what is on disk.
        """
        scene_manager = self.container.get(SceneManager)
        if scene_manager.current_scene is not self:
            return
        self.save_now()
        score = compute_score(self.grid, self.entity_manager, self.economy)
        scene_manager.register(
            EvaluationScene(
                self.event_dispatcher,
                score,
                self._quit_to_title,
                WINDOW_WIDTH,
                WINDOW_HEIGHT,
            )
        )
        scene_manager.push_scene("EvaluationScene", pause_below=True)

    def _quit_to_title(self) -> None:
        """Unwind to the title screen. Leaving this scene saves it."""
        self.container.get(SceneManager).switch_to("TitleScene")

    def _on_outbreak_started(self, event: OutbreakStartedEvent) -> None:
        if self._canvas is not None:
            self._canvas.flash_alert()
        if self._audio is not None:
            self._audio.play_sfx(SFX_OUTBREAK_START)
        self._say("Pests! Treat them")

    def _on_outbreak_resolved(self, event: OutbreakResolvedEvent) -> None:
        if self._audio is not None:
            self._audio.play_sfx(SFX_OUTBREAK_RESOLVED)
        self._say(f"Pests gone ({event.method})")

    def _on_drone_harvest(self, event: PlantHarvestedEvent) -> None:
        if self._canvas is None:
            return
        if event.kind == CREDITS:
            self._canvas.celebrate_harvest(event.cell, event.species_id)
            self._canvas.spawn_label(event.cell, f"+{event.value}", GAIN_COLOR)
        else:
            self._canvas.celebrate_seed(event.cell, event.species_id)
            label = "Generic seed" if event.kind == GENERIC_SEED else "Seed"
            self._canvas.spawn_label(event.cell, f"+{event.value} {label}", GAIN_COLOR)

    def _on_solar_income(self, event: SolarIncomeEvent) -> None:
        if self._canvas is not None:
            self._canvas.spawn_label(event.cell, f"+{event.amount}", GAIN_COLOR)
        if self._audio is not None:
            self._audio.play_sfx(SFX_SOLAR_INCOME)

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
        elif tool == "plant_generic":
            self._sow_generic(cell)
        elif tool.startswith("plant_"):
            self._plant(cell, tool.removeprefix("plant_"))
        elif tool.startswith("build_"):
            self._build(cell, tool.removeprefix("build_"))

    def _cant_afford(self, cell: Cell, cost: int) -> None:
        """Tell the player, at the cell they clicked, what they were short of."""
        if self._canvas is not None:
            self._canvas.spawn_label(cell, f"Need {cost}", WARN_COLOR)
        if self._audio is not None:
            self._audio.play_sfx(SFX_DENIED)
        self._say("Not enough Sementes")

    def _plant(self, cell: Cell, species_id: str) -> None:
        """Plant a specific species, spending stocked seed before Sementes.

        An overripe harvest stocks a free seed of its own species
        (`economy.harvest_cell`) -- `consume_seed` spends one of those
        first, and only charges `seed_cost` once that stock is empty, so
        a stocked seed is never wasted paying for one you didn't need to.
        """
        species = SPECIES_TABLE.get(species_id)
        if species is None or not self.grid.can_plant(cell):
            return
        if not consume_seed(self.economy, specific_seed_key(species_id)) and (
            not spend_credits(self.economy, species.seed_cost)
        ):
            self._cant_afford(cell, species.seed_cost)
            return
        entity = self.entity_manager.create_entity()
        entity.add_component(PlantComponent(species_id=species_id))
        entity.add_component(build_plant_ai(entity))
        self.grid.mark_planted(cell, entity.id)

    def _sow_generic(self, cell: Cell) -> None:
        """Sow one generic seed, if there is one, as a random common species.

        `pick_generic_species` weights towards cheap species -- a free
        seed pulled off a weed is a worse bet at a valuable canopy tree
        than paying for one outright, on purpose.
        """
        if not self.grid.can_plant(cell):
            return
        if not consume_seed(self.economy, GENERIC_SEED_KEY):
            if self._canvas is not None:
                self._canvas.spawn_label(cell, "No generic seed", WARN_COLOR)
            self._say("Pull a weed for a generic seed")
            return
        species_id = pick_generic_species(self._rng or RandomStream())
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
        """Collect a harvestable or overripe plant, or clear a dead one.

        The cell stays tilled either way, ready to replant. An infested
        plant is refused -- treating the pests first is the point of the
        outbreak -- and a plant still growing is left alone. What a
        collectable plant is worth (Sementes, or a seed) is entirely
        `economy.harvest_cell`'s call; this only reports the result.
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
        result = harvest_cell(self.grid, self.entity_manager, self.economy, cell)
        if result is None or self._canvas is None:
            return
        if result.kind == CREDITS:
            self._canvas.celebrate_harvest(cell, result.species_id)
            self._canvas.spawn_label(cell, f"+{result.amount}", GAIN_COLOR)
        else:
            self._canvas.celebrate_seed(cell, result.species_id)
            label = "Generic seed" if result.kind == GENERIC_SEED else "Seed"
            self._canvas.spawn_label(cell, f"+{result.amount} {label}", GAIN_COLOR)

    def on_exit(self) -> None:
        """Save the garden.

        Every way out of this scene runs through here -- quitting to the
        title, and the window being closed, which `Application` turns into a
        `SceneManager.cleanup()` -- so this is the one "save on exit".
        """
        self.save_now()

    def fixed_update(self, fixed_dt: float) -> None:
        """Advance the play clock. The engine pauses this while an overlay is up."""
        self.elapsed += fixed_dt

    def update(self, dt: float) -> None:
        """Refresh the HUD and inspector, and offer the evaluation at 15:00."""
        automation = self.system_manager.get_system(AutomationSystem)
        power = (
            (automation.power_used, automation.power_capacity)
            if automation is not None
            else (0, 0)
        )
        if self._hud is not None:
            self._hud.update(dt, self.economy, self.conditions, self.elapsed, power)
        self._refresh_tool_slots()
        weather_system = self.system_manager.get_system(WeatherSystem)
        if self._weather_panel is not None and weather_system is not None:
            self._weather_panel.update(
                weather_system.state.condition_id, weather_system.forecast
            )
        if self._canvas is not None:
            self._canvas.darkness = darkness(self.elapsed)
            if self._inspector is not None:
                self._inspector.update(
                    self.grid, self.entity_manager, self._canvas.hover_cell
                )
        self._update_weather_effects(dt)
        if self.elapsed >= EVALUATION_TIME and not self._evaluation_offered:
            self._evaluation_offered = True
            self.open_evaluation()

    def _update_weather_effects(self, dt: float) -> None:
        """Drive the post-process shaders from real state, every frame.

        Nothing here decides what the weather or the soil *is* --
        `WeatherSystem` and `scoring.soil_health` already did that. This
        only ever translates their numbers into a shader's own uniforms,
        so the visual can never disagree with what the HUD or the
        evaluation screen says about the same plot.
        """
        if self._storm is not None:
            rain_reference = WEATHER_TABLE["rainy"].moisture_gain_per_second
            self._storm.rain = (
                min(1.0, self.weather.moisture_gain_per_second / rain_reference)
                if rain_reference > 0.0
                else 0.0
            )
            self._storm.update(dt)
        if self._vignette is not None:
            self._vignette.intensity = (
                COLD_SNAP_VIGNETTE_INTENSITY
                if self.weather.cold_snap
                else BASE_VIGNETTE_INTENSITY
            )
        if self._soil_health_effect is not None:
            any_tilled = any(
                soil.soil_type == "tilled_dirt"
                for row in self.grid.soil
                for soil in row
            )
            self._soil_health_effect.health = soil_health(self.grid)
            self._soil_health_effect.strength = (
                SOIL_HEALTH_GRADE_STRENGTH if any_tilled else 0.0
            )

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Clear the world and draw the plot into it; `Application` grades it.

        The tool dock, the HUD and every overlay still draw through the UI
        pass as always; only the grid moved (Phase 5) -- see
        `garden_widget.py`'s module docstring for why.
        """
        world_renderer.clear(art.WORLD_BACKDROP)
        if self._canvas is not None:
            self._canvas.render_world(world_renderer)
