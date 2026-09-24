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
Nothing simulates between actions. The eight simulation systems --
`SoilSystem`, `AutomationSystem`, `ShadeSystem`, `SyntropicSystem`,
`PestSystem`, `PlantGrowthSystem`, `WeedSpreadSystem`, `WeatherSystem` --
are owned by `systems/day_resolver.py` and run, in that order, only when
the player sleeps (`end_day`). They are deliberately *not* registered on
`self.system_manager`, and this scene drops the engine's own `AISystem`
too, so neither the plant nor the garden FSM can advance on real seconds.

Two entities besides the plants live in the scene's world: `player`,
carrying `PlayerEconomy`, and `garden_conditions`, carrying
`GardenConditions` and the FSM (`garden_states.py`) that paces pest
outbreaks. Seeds and treatments cost Sementes, and a harvest pays them
back -- double for an organically grown plant, half for one that was
ever sprayed (`economy.py`). That is the PRD's dilemma: the spray fixes an
outbreak at once, and the compost is what keeps the premium.

The garden is saved through `pyguara.persistence` -- every night, as part
of `end_day`, and whenever the scene exits, which is also what closing the
window does. There is no periodic autosave: between two mornings nothing
changes that a save could miss. The title screen's Continue loads it. The
pause menu (`pause.py`, Esc), the morning report (`morning.py`, after every
night) and the evaluation (`evaluation.py`, after the last one) are
overlays like the store.

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
from games.quintal_cerrado.hud import CellInspector, Hud
from games.quintal_cerrado.hud_widgets import DockGroup, SlotSpec, ToolDock, ToolSlot
from games.quintal_cerrado.pause import PauseScene
from games.quintal_cerrado.persistence_schema import (
    SAVE_KEY,
    SCHEMA_VERSION,
    SaveFormatError,
    WeatherSnapshot,
    apply_save_payload,
    to_save_payload,
)
from games.quintal_cerrado.plant_states import build_plant_ai
from games.quintal_cerrado.scoring import Score, compute_score, soil_health
from games.quintal_cerrado.soil_health_effect import SoilHealthEffect
from games.quintal_cerrado.species import (
    SPECIES_TABLE,
    pick_generic_species,
)
from games.quintal_cerrado.store import StoreOverlayScene
from games.quintal_cerrado.structures import STRUCTURE_TABLE, place_structure
from games.quintal_cerrado.systems.automation_system import AutomationSystem
from games.quintal_cerrado.systems.day_resolver import DayReport, DayResolver
from games.quintal_cerrado.systems.pest_system import PestSystem
from games.quintal_cerrado.systems.plant_growth_system import PlantGrowthSystem
from games.quintal_cerrado.systems.shade_system import ShadeSystem
from games.quintal_cerrado.systems.soil_system import SoilSystem
from games.quintal_cerrado.systems.syntropic_system import SyntropicSystem
from games.quintal_cerrado.systems.weather_system import WeatherSystem
from games.quintal_cerrado.systems.weed_spread_system import WeedSpreadSystem
from games.quintal_cerrado.turn import SESSION_DAYS, DayCycle, action_cost
from games.quintal_cerrado.weather import WEATHER_TABLE, WeatherState
from pyguara.ai.ai_system import AISystem
from pyguara.audio.manager import AudioManager
from pyguara.common.grid import Cell
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import ESCAPE, KEY_O, B, C, G, H, M, N, P, S, T, W, Z
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
SLEEP_ACTION = "sleep"
STORE_ACTION = "open_store"
"""Not a tool -- it has no active state -- so it is bound and handled apart
from `_TOOL_KEYS`, and its slot is not in `_tool_buttons`."""

STORE_SLOT = "store"
MENU_SLOT = "menu"
SLEEP_SLOT = "sleep"


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
            [
                SlotSpec(SLEEP_SLOT, "Dormir", "Z"),
                SlotSpec(STORE_SLOT, "Loja", "O"),
                SlotSpec(MENU_SLOT, "Menu", "Esc"),
            ],
        ),
    ]


def slot_status(
    tool: str, economy: PlayerEconomy, turn: DayCycle | None = None
) -> tuple[str, bool]:
    """What a tool's slot badge says, and whether the player can use it now.

    Mirrors what `GardenScene` actually charges, so the dock can never
    promise a price the click then disagrees with: a species spends its
    own stocked seed before Sementes (`_plant`), Generic spends only
    stocked generic seed (`_sow_generic`), and compost and spray cost
    their flat price (`treatments`). Every other tool is free.

    Stamina is the second gate. A tool you have the Sementes for but not
    the energy dims the same way, because from the player's side it is the
    same answer: not today.

    Args:
        tool: A tool id.
        economy: The player's economy.
        turn: The day's stamina, or None to ignore energy entirely.

    Returns:
        `(badge, affordable)` -- the badge is "" for a free tool.
    """
    badge, affordable = _price_status(tool, economy)
    if turn is not None and not turn.can_afford(action_cost(tool)):
        return badge, False
    return badge, affordable


def _price_status(tool: str, economy: PlayerEconomy) -> tuple[str, bool]:
    """What a tool costs in Sementes or stocked seed, ignoring stamina."""
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
        """Draw the backdrop; the menu is UI on top of it.

        The post-process pass that grades this is not run from here:
        `Application` executes every render-graph pass itself, after all
        scenes have drawn.
        """
        world_renderer.clear(art.WORLD_BACKDROP)
        art.draw_backdrop(world_renderer, WINDOW_WIDTH, WINDOW_HEIGHT)


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
        self._inspector: CellInspector | None = None
        self._tool_buttons: dict[str, ToolSlot] = {}
        self._store_button: ToolSlot | None = None
        self._menu_button: ToolSlot | None = None
        self._sleep_button: ToolSlot | None = None
        self._active_tool = "till"
        self._load_requested = load
        self.turn = DayCycle()
        """Which day it is and what energy is left in it (`turn.py`)."""
        self._resolver: DayResolver | None = None
        self._last_report: DayReport | None = None
        self._evaluation_offered = False

    def on_enter(self) -> None:
        """Build the widgets and entities, wire input, own the systems."""
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
        self._create_entities()
        self._resolver = self._build_resolver()
        if self._load_requested:
            self._load()

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

    def _build_resolver(self) -> DayResolver:
        """Own the simulation systems instead of registering them.

        None of them tick any more: the garden is turn-based, and a night is
        the only thing that moves the plot (`systems/day_resolver.py`). The
        engine's own `AISystem` is dropped for the same reason -- it would
        drive the plant and garden FSMs on real seconds between actions --
        and the resolver drives those FSMs itself.
        """
        self.system_manager.unregister(AISystem)
        return DayResolver(
            self.entity_manager,
            self.grid,
            self.conditions,
            self.event_dispatcher,
            soil=SoilSystem(self.grid, self.weather),
            automation=AutomationSystem(
                self.entity_manager, self.grid, self.economy, self.event_dispatcher
            ),
            shade=ShadeSystem(self.entity_manager, self.grid),
            syntropic=SyntropicSystem(self.entity_manager, self.grid),
            pest=PestSystem(self.entity_manager, self.grid, self.weather),
            growth=PlantGrowthSystem(self.entity_manager, self.grid, self.weather),
            weeds=WeedSpreadSystem(self.entity_manager, self.grid, self._rng),
            weather=WeatherSystem(self.weather, self._rng),
        )

    def _build_grid_widget(self, ui_manager: UIManager) -> None:
        """The plot, left of the right-hand column (`layout.GRID_ORIGIN`)."""
        self._canvas = GardenGridCanvas(
            layout.GRID_ORIGIN, self.grid, self.entity_manager, self._audio
        )
        self._canvas.on_cell_clicked = self._on_cell_clicked
        self._canvas.tool_allows = self._tool_allows
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
            if tool == SLEEP_SLOT:
                slot.on_click = lambda _element: self.end_day()
                self._sleep_button = slot
            elif tool == STORE_SLOT:
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
            slot.badge, slot.affordable = slot_status(tool, self.economy, self.turn)

    def _tool_allows(self, cell: Cell) -> bool:
        """Whether the active tool would actually do something on `cell`.

        What the cursor colours itself from. Every branch mirrors the
        check the click itself makes -- `grid.till`/`water` on the soil,
        `can_plant`, `can_build`, and `treatments`' own tilled/saturated
        rules -- plus whether it can be paid for (`slot_status`), so the
        ring cannot promise an action the click then refuses.

        Args:
            cell: The cell under the cursor.

        Returns:
            Whether a click there would land.
        """
        tool = self._active_tool
        if not self.grid.in_bounds(cell):
            return False
        if not slot_status(tool, self.economy, self.turn)[1]:
            return False
        soil = self.grid.soil_at(cell)
        if tool == "till":
            return soil.soil_type == "raw_dirt"
        if tool == "water":
            return soil.moisture < 1.0
        if tool == "harvest":
            return cell in self.grid.plant_at
        if tool == "compost":
            return soil.soil_type == "tilled_dirt" and soil.organic_matter < 1.0
        if tool == "spray":
            return True
        if tool.startswith("plant_"):
            return self.grid.can_plant(cell)
        if tool.startswith("build_"):
            return self.grid.can_build(cell)
        return True

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
        input_manager.register_action(SLEEP_ACTION, ActionType.PRESS)
        input_manager.bind_input(InputDevice.KEYBOARD, Z, SLEEP_ACTION)
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
        elif event.action_name == SLEEP_ACTION:
            self.end_day()
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
        weather = self._resolver.weather if self._resolver is not None else None
        payload = to_save_payload(
            self.grid,
            self.entity_manager,
            self.economy,
            self.conditions,
            self.turn,
            WeatherSnapshot(weather.state.condition_id, weather.forecast)
            if weather is not None
            else None,
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
            self.turn, weather = apply_save_payload(
                payload, self.grid, self.entity_manager, self.economy, self.conditions
            )
        except SaveFormatError as error:
            logger.warning("Ignoring an unreadable save: %s", error)
            self._say("Save unreadable -- it is from an older build")
            return
        if self._resolver is not None:
            self._resolver.weather.restore(weather.condition_id, weather.forecast)
        # A session already past its last day must not re-offer the evaluation.
        self._evaluation_offered = self.turn.day > SESSION_DAYS
        self._say(f"Garden loaded -- day {self.turn.day}")

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

    def _score(self) -> Score:
        """Score the plot as it stands, for the resilience bar.

        The same call `open_evaluation` grades with, so the ribbon and the
        evaluation screen can never disagree about the same garden.
        """
        return compute_score(self.grid, self.entity_manager, self.economy)

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

    def _build(self, cell: Cell, kind: str) -> bool:
        """Place a structure from the inventory, and drop the tool when it runs out.

        Returns:
            Whether the structure was placed.
        """
        if (
            place_structure(self.grid, self.entity_manager, self.economy, kind, cell)
            != "ok"
        ):
            return False
        if self._canvas is not None:
            self._canvas.celebrate_build(cell, kind)
        if self.economy.inventory.get(kind, 0) <= 0:
            self._set_active_tool("till")
        return True

    def _on_cell_clicked(self, cell: Cell) -> None:
        """Act on `cell` with the active tool, if the day has the energy.

        Stamina is spent only once the action has actually happened: a
        click refused for any other reason -- untilled ground, no Sementes,
        nothing to harvest -- must cost nothing, or a day drains on clicks
        that did nothing.
        """
        tool = self._active_tool
        cost = action_cost(tool)
        if not self.turn.can_afford(cost):
            self._no_energy(cell)
            return
        if self._perform(tool, cell):
            self.turn.spend(cost)

    def _perform(self, tool: str, cell: Cell) -> bool:
        """Run `tool` on `cell`.

        Args:
            tool: The active tool id.
            cell: The clicked cell.

        Returns:
            Whether anything actually happened -- which is what decides if
            the day is charged for it.
        """
        if tool == "till":
            if not self.grid.till(cell):
                return False
            if self._canvas is not None:
                self._canvas.celebrate_till(cell)
            return True
        if tool == "water":
            if not self.grid.water(cell):
                return False
            if self._canvas is not None:
                self._canvas.celebrate_water(cell)
            return True
        if tool == "harvest":
            return self._harvest(cell)
        if tool == "compost":
            return self._compost(cell)
        if tool == "spray":
            return self._spray(cell)
        if tool == "plant_generic":
            return self._sow_generic(cell)
        if tool.startswith("plant_"):
            return self._plant(cell, tool.removeprefix("plant_"))
        if tool.startswith("build_"):
            return self._build(cell, tool.removeprefix("build_"))
        return False

    def _no_energy(self, cell: Cell) -> None:
        """Say why the click did nothing, where it was clicked."""
        if self._canvas is not None:
            self._canvas.spawn_label(cell, "Sem energia", WARN_COLOR)
        if self._audio is not None:
            self._audio.play_sfx(SFX_DENIED)
        self._say("No energy left -- sleep to start a new day")

    def _cant_afford(self, cell: Cell, cost: int) -> None:
        """Tell the player, at the cell they clicked, what they were short of."""
        if self._canvas is not None:
            self._canvas.spawn_label(cell, f"Need {cost}", WARN_COLOR)
        if self._audio is not None:
            self._audio.play_sfx(SFX_DENIED)
        self._say("Not enough Sementes")

    def _plant(self, cell: Cell, species_id: str) -> bool:
        """Plant a specific species, spending stocked seed before Sementes.

        An overripe harvest stocks a free seed of its own species
        (`economy.harvest_cell`) -- `consume_seed` spends one of those
        first, and only charges `seed_cost` once that stock is empty, so
        a stocked seed is never wasted paying for one you didn't need to.
        """
        species = SPECIES_TABLE.get(species_id)
        if species is None or not self.grid.can_plant(cell):
            return False
        if not consume_seed(self.economy, specific_seed_key(species_id)) and (
            not spend_credits(self.economy, species.seed_cost)
        ):
            self._cant_afford(cell, species.seed_cost)
            return False
        entity = self.entity_manager.create_entity()
        entity.add_component(PlantComponent(species_id=species_id))
        entity.add_component(build_plant_ai(entity))
        self.grid.mark_planted(cell, entity.id)
        return True

    def _sow_generic(self, cell: Cell) -> bool:
        """Sow one generic seed, if there is one, as a random common species.

        `pick_generic_species` weights towards cheap species -- a free
        seed pulled off a weed is a worse bet at a valuable canopy tree
        than paying for one outright, on purpose.
        """
        if not self.grid.can_plant(cell):
            return False
        if not consume_seed(self.economy, GENERIC_SEED_KEY):
            if self._canvas is not None:
                self._canvas.spawn_label(cell, "No generic seed", WARN_COLOR)
            self._say("Pull a weed for a generic seed")
            return False
        species_id = pick_generic_species(self._rng or RandomStream())
        entity = self.entity_manager.create_entity()
        entity.add_component(PlantComponent(species_id=species_id))
        entity.add_component(build_plant_ai(entity))
        self.grid.mark_planted(cell, entity.id)
        return True

    def _compost(self, cell: Cell) -> bool:
        """Compost `cell`, and report whether it took."""
        result = treatments.apply_compost(
            self.grid, self.economy, self.conditions, cell
        )
        if result == treatments.OK:
            if self._canvas is not None:
                self._canvas.celebrate_compost(cell)
            return True
        if result == treatments.BROKE:
            self._cant_afford(cell, COMPOST_COST)
        return False

    def _spray(self, cell: Cell) -> bool:
        """Spray `cell` and its neighbours, and report whether it took."""
        result = treatments.apply_spray(
            self.grid, self.entity_manager, self.economy, self.conditions, cell
        )
        if result == treatments.OK:
            if self._canvas is not None:
                self._canvas.celebrate_spray(cell)
            return True
        if result == treatments.BROKE:
            self._cant_afford(cell, SPRAY_COST)
        return False

    def _harvest(self, cell: Cell) -> bool:
        """Collect a harvestable or overripe plant, or clear a dead one.

        The cell stays tilled either way, ready to replant. An infested
        plant is refused -- treating the pests first is the point of the
        outbreak -- and a plant still growing is left alone. What a
        collectable plant is worth (Sementes, or a seed) is entirely
        `economy.harvest_cell`'s call; this only reports the result.
        """
        entity_id = self.grid.plant_at.get(cell)
        if entity_id is None:
            return False
        entity = self.entity_manager.get_entity(entity_id)
        if entity is None or not entity.has_component(PlantComponent):
            return False
        plant = entity.get_component(PlantComponent)

        if plant.growth_stage == "infested":
            self._say("Treat the pests first")
            return False
        if plant.growth_stage == "dying":
            self.entity_manager.remove_entity(entity_id)
            self.grid.unmark_planted(cell)
            if self._canvas is not None:
                self._canvas.spawn_label(cell, "Cleared", Color(190, 180, 168))
            return True
        result = harvest_cell(self.grid, self.entity_manager, self.economy, cell)
        if result is None:
            return False
        if self._canvas is None:
            return True
        if result.kind == CREDITS:
            self._canvas.celebrate_harvest(cell, result.species_id)
            self._canvas.spawn_label(cell, f"+{result.amount}", GAIN_COLOR)
        else:
            self._canvas.celebrate_seed(cell, result.species_id)
            label = "Generic seed" if result.kind == GENERIC_SEED else "Seed"
            self._canvas.spawn_label(cell, f"+{result.amount} {label}", GAIN_COLOR)
        return True

    def end_day(self) -> DayReport:
        """Sleep: resolve the night, wake on the next morning, save.

        The one place the simulation moves. Saving here replaces the old
        60-second autosave -- between two mornings nothing can have changed
        that a save would capture.

        Returns:
            What happened overnight.
        """
        report = DayReport(day=self.turn.day)
        if self._resolver is not None:
            report = self._resolver.resolve(self.turn.day)
        self._last_report = report
        final = self.turn.is_final_day
        self.turn.sleep()
        self.save_now()
        if final and not self._evaluation_offered:
            self._evaluation_offered = True
            self.open_evaluation()
        else:
            self._say(self._night_summary(report))
        return report

    @staticmethod
    def _night_summary(report: DayReport) -> str:
        """One line for the toast until the morning report lands (PR3)."""
        if report.outbreak_started:
            return "Pests broke out overnight"
        parts = []
        if report.ripened:
            parts.append(f"{len(report.ripened)} ready to harvest")
        if report.stages_grown:
            parts.append(f"{len(report.stages_grown)} grew")
        if report.solar_income:
            parts.append(f"+{report.solar_income} solar")
        return "  ".join(parts) if parts else "A quiet night"

    def on_exit(self) -> None:
        """Save the garden.

        Every way out of this scene runs through here -- quitting to the
        title, and the window being closed, which `Application` turns into a
        `SceneManager.cleanup()` -- so this is the one "save on exit".
        """
        self.save_now()

    def update(self, dt: float) -> None:
        """Refresh the HUD and the inspector. Nothing simulates here.

        The plot only changes when the player sleeps (`end_day`), so this
        is presentation only: the cards, the dock's affordability, the
        hovered cell, and the post-process shaders.
        """
        automation = self._resolver.automation if self._resolver is not None else None
        power = (
            (automation.power_used, automation.power_capacity)
            if automation is not None
            else (0, 0)
        )
        if self._hud is not None:
            self._hud.update(
                dt,
                self.economy,
                self.conditions,
                self.turn,
                power,
                self._score,
            )
        self._refresh_tool_slots()
        weather = self._resolver.weather if self._resolver is not None else None
        if self._hud is not None and weather is not None:
            self._hud.update_weather(
                weather.state.condition_id, weather.forecast, self.turn.day
            )
        if self._canvas is not None and self._inspector is not None:
            self._inspector.update(
                self.grid, self.entity_manager, self._canvas.hover_cell
            )
        self._update_weather_effects(dt)

    def _update_weather_effects(self, dt: float) -> None:
        """Drive the post-process shaders from real state, every frame.

        Nothing here decides what the weather or the soil *is* --
        `WeatherSystem` and `scoring.soil_health` already did that. This
        only ever translates their numbers into a shader's own uniforms,
        so the visual can never disagree with what the HUD or the
        evaluation screen says about the same plot.
        """
        if self._storm is not None:
            rain_reference = WEATHER_TABLE["rainy"].moisture_gain_per_day
            self._storm.rain = (
                min(1.0, self.weather.moisture_gain_per_day / rain_reference)
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
        art.draw_backdrop(world_renderer, WINDOW_WIDTH, WINDOW_HEIGHT)
        if self._canvas is not None:
            self._canvas.render_world(world_renderer)
