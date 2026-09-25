"""The garden HUD: the ribbon, the tool card, the toast and the inspector.

`Hud` owns the top ribbon (`ribbon.py` -- resources, weather, resilience)
and the message toast; `CellInspector` is the card under them in the right
column. Everything shown is real state: Sementes are
`PlayerEconomy.credits`, the day is the turn's own, power is
`AutomationSystem`'s real budget, the status line is
`GardenConditions.phase`, the resilience bar is `scoring.compute_score`,
and the inspector reads the `SoilCell` and plant under the cursor.

Where each piece sits is `layout.py`'s call.
"""

from __future__ import annotations

from collections.abc import Callable

from games.quintal_cerrado import art, layout, nutrients, stress
from games.quintal_cerrado.components import (
    AutomationComponent,
    GardenConditions,
    PlantComponent,
    PlayerEconomy,
    SoilCell,
)
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.hud_widgets import (
    MUTED_TEXT,
    TEXT_COLOR,
    CardPanel,
    draw_badge,
)
from games.quintal_cerrado.icons import draw_icon
from games.quintal_cerrado.ribbon import ResilienceCard, ResourceCard, WeatherCard
from games.quintal_cerrado.scoring import Score
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.structures import STRUCTURE_TABLE
from games.quintal_cerrado.tool_info import ToolInfo, describe
from games.quintal_cerrado.turn import DayCycle
from games.quintal_cerrado.weather import WeatherState
from pyguara.common.grid import Cell
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.text import Label
from pyguara.ui.design_system.tokens import (
    Falcao,
    Guara,
    Roxo,
    Sand,
    Verdant,
    Water,
)
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer

PORTRAIT_FILL = Roxo.C900.lerp(Color(0, 0, 0), 0.25)
PORTRAIT_EDGE = Sand.C500.lerp(Roxo.C900, 0.55)
RUNG_OFF = Falcao.C400.lerp(Roxo.C900, 0.55)
DEGRADED_TEXT = Color(206, 132, 96)
SOIL_LOW = Sand.C500
SOIL_RICH = Verdant.SAGE_100

MESSAGE_SECONDS = 2.5
TOAST_HEIGHT = 30
"""The column is exactly tall enough for the inspector, the tool card and
this, between the ribbon and the dock. Anything taller runs into the
dock's BASE group."""

_SOIL_NAMES = {
    "raw_dirt": "Raw dirt",
    "tilled_dirt": "Tilled soil",
    "path": "Path",
    "water_pipe": "Water pipe",
}


class Hud:
    """Owns the ribbon's three cards and the message toast."""

    def __init__(self, ui_manager: UIManager, column_top: int) -> None:
        """Build the ribbon, the tool card and the toast.

        Args:
            ui_manager: The manager to add them to.
            column_top: Where the right column continues below the cell
                inspector -- the tool card goes here, the toast under it.
        """
        self.resources = ResourceCard()
        self.weather = WeatherCard()
        self.resilience = ResilienceCard()
        for card in (self.resources, self.weather, self.resilience):
            ui_manager.add_element(card, UILayer.HUD)

        self.tools = ToolCard(column_top)
        ui_manager.add_element(self.tools, UILayer.HUD)

        toast_y = column_top + layout.TOOL_CARD_HEIGHT + layout.GAP
        self.message_label = Label("", Vector2(0, 0), font_size=13)
        self.toast = CardPanel(
            Vector2(layout.COLUMN_X, toast_y),
            Vector2(layout.COLUMN_WIDTH, TOAST_HEIGHT),
        )
        self.message_label.rect.x = layout.COLUMN_X + 12
        self.message_label.rect.y = toast_y + 9
        self.toast.add_child(self.message_label)
        self.toast.visible = False
        ui_manager.add_element(self.toast, UILayer.HUD)
        self._message_left = 0.0

    @property
    def credits_label(self) -> Label:
        """The Sementes count, on the resource card."""
        return self.resources.credits_label

    @property
    def status_label(self) -> Label:
        """The pest status line, on the resource card."""
        return self.resources.status_label

    @property
    def day_label(self) -> Label:
        """Which day it is, on the weather card."""
        return self.weather.day_label

    def show_message(self, text: str) -> None:
        """Show `text` in the toast for `MESSAGE_SECONDS`.

        Args:
            text: A short line -- the toast is one line tall.
        """
        self.message_label.set_text(text)
        self.toast.visible = bool(text)
        self._message_left = MESSAGE_SECONDS

    def update(
        self,
        dt: float,
        economy: PlayerEconomy,
        conditions: GardenConditions,
        turn: DayCycle,
        power: tuple[int, int],
        compute_score: Callable[[], Score] | None = None,
    ) -> None:
        """Pull this frame's numbers out of the game.

        Args:
            dt: Seconds since the last frame, for the message and score
                timers.
            economy: The player's economy.
            conditions: The garden's pest situation.
            turn: The day and the stamina left in it.
            power: `(devices powered, capacity)` from the solar panels.
            compute_score: Returns a fresh `scoring.Score` for the
                resilience bar. Called at most every
                `ribbon.SCORE_INTERVAL` seconds, never per frame.
        """
        self.resources.refresh(economy, conditions, power, turn)
        if compute_score is not None:
            self.resilience.refresh(dt, compute_score)
        if self._message_left > 0.0:
            self._message_left -= dt
            if self._message_left <= 0.0:
                self.message_label.set_text("")
                self.toast.visible = False

    def show_tool(self, tool: str) -> None:
        """Explain `tool` on the card under the inspector.

        Args:
            tool: The hovered tool id, or the active one when the cursor is
                not over the dock.
        """
        self.tools.show(tool)

    def update_weather(self, condition_id: str, forecast: list[str], day: int) -> None:
        """Hand the weather card the sky and the calendar.

        Args:
            condition_id: `WeatherSystem.state.condition_id`.
            forecast: `WeatherSystem.forecast`, nearest first.
            day: The current day, 1-based.
        """
        self.weather.refresh(condition_id, forecast, day)


LAYER_RUNGS = (
    ("Alto", "canopy"),
    ("Médio", "understory"),
    ("Baixo", "ground_cover"),
)
"""The syntropic ladder, top down. Three rungs because `Species` has three
canopy layers -- the mockup's fourth, "Emergente", has nothing behind it."""

PEST_STEPS = (
    (0.66, Color(214, 96, 80)),
    (0.33, Sand.C500),
)
"""Pest fill by severity, worst first: crimson, then amber, then the calm
colour below them. A gauge that stays one colour makes "some pests" and
"lose the crop" look alike."""
PEST_CALM = Falcao.C400

PORTRAIT = 84
"""Side of the square the plant's portrait is drawn in."""

PORTRAIT_SCALE = 4.5
"""How much bigger the portrait draws a plant than the plot does. The plot
draws at 1.0 into a 48px tile; this fills an 84px box instead, so a
seedling still reads as a seedling and a mature tree fills the frame."""


def pest_color(pressure: float) -> Color:
    """The fill colour for `pressure`, 0.0-1.0.

    Args:
        pressure: `SoilCell.pest_pressure`.

    Returns:
        Crimson above 0.66, amber above 0.33, muted below.
    """
    for floor, color in PEST_STEPS:
        if pressure >= floor:
            return color
    return PEST_CALM


class ToolCard(CardPanel):
    """What the hovered tool or seed is for.

    The dock says what something costs; it cannot say what it does, and the
    PRD's dilemma only works if the player knows what a spray trades away.
    Falls back to the *active* tool when the cursor is not over the dock,
    so the card is never blank and always describes what a click would do.

    Attributes:
        tool: The tool id currently explained.
    """

    LINE_HEIGHT = 14
    BODY_SIZE = 11

    def __init__(self, top: int) -> None:
        """Build the card at the top of its slice of the right column.

        Args:
            top: The card's top edge, below the cell inspector.
        """
        super().__init__(
            Vector2(layout.COLUMN_X, top),
            Vector2(layout.COLUMN_WIDTH, layout.TOOL_CARD_HEIGHT),
        )
        self.tool = ""
        self._info: ToolInfo | None = None

    def show(self, tool: str) -> None:
        """Point the card at `tool`.

        Args:
            tool: The tool id to explain.
        """
        if tool == self.tool:
            return
        self.tool = tool
        self._info = describe(tool)

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card: icon, name, the costs, then the wrapped body."""
        super().render(renderer)
        info = self._info
        if info is None:
            return
        draw_icon(
            renderer, info.icon_id, Rect(self.rect.x + 12, self.rect.y + 10, 22, 22)
        )
        renderer.draw_text(
            info.name, Vector2(self.rect.x + 42, self.rect.y + 13), TEXT_COLOR, 14
        )
        self._draw_costs(renderer, info)

        y = self.rect.y + 36
        limit = self.rect.bottom - 4
        for line in info.lines:
            for part in _wrap(renderer, line, self.rect.width - 24, self.BODY_SIZE):
                if y + self.LINE_HEIGHT > limit:
                    return
                renderer.draw_text(
                    part, Vector2(self.rect.x + 12, y), MUTED_TEXT, self.BODY_SIZE
                )
                y += self.LINE_HEIGHT

    def _draw_costs(self, renderer: UIRenderer, info: ToolInfo) -> None:
        """Stamina and Sementes, right-aligned against the name."""
        x = self.rect.right - 12
        if info.price:
            badge = draw_badge(renderer, info.price, Vector2(0, 0), icon_id="seed")
            x -= badge.width
            draw_badge(
                renderer, info.price, Vector2(x, self.rect.y + 12), icon_id="seed"
            )
            x -= 6
        if info.stamina:
            text = f"{info.stamina}"
            badge = draw_badge(renderer, text, Vector2(0, 0), icon_id="stamina")
            draw_badge(
                renderer,
                text,
                Vector2(x - badge.width, self.rect.y + 12),
                icon_id="stamina",
            )


def _wrap(renderer: UIRenderer, text: str, width: int, size: int) -> list[str]:
    """Break `text` into lines that fit `width`.

    Args:
        renderer: Measures the text.
        text: One sentence.
        width: Pixels available.
        size: Font size.

    Returns:
        The lines, in order.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and renderer.get_text_size(candidate, size)[0] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


class CellInspector:
    """The soil and plant under the cursor: a portrait, a ladder, four gauges.

    The portrait is `art.draw_plant` -- the very function the plot draws
    with (through `ShapeRenderer`, which both renderers satisfy), so the
    card cannot show a different plant from the one in the ground.
    """

    METRICS = (
        ("Umidade", "moisture", "moisture", Water.C300),
        ("Húmus", "organic_matter", "humus", Verdant.COLONIAL_500),
        ("Sombra", "shade_level", "shade", Sand.C500),
        ("Pragas", "pest_pressure", "pests", Guara.C400),
    )
    ROW_HEIGHT = 26
    TOP = PORTRAIT + 62
    """Where the gauges start: below the portrait box *and* the detail line
    under it, which is what pushed this past the portrait's own height."""
    HEIGHT = TOP + ROW_HEIGHT * len(METRICS) + 10

    def __init__(self, ui_manager: UIManager, position: Vector2, width: int) -> None:
        """Build the card and add it to the HUD layer.

        Args:
            ui_manager: The manager to add the card to.
            position: Top-left corner, in screen space.
            width: Card width.
        """
        self.panel = _InspectorCard(position, Vector2(width, self.HEIGHT))
        self.title = Label("", Vector2(position.x + 12, position.y + 10), font_size=13)
        self.panel.add_child(self.title)

        bar_x = position.x + 100
        self.bars: dict[str, ProgressBar] = {}
        for index, (name, key, icon_id, color) in enumerate(self.METRICS):
            y = position.y + self.TOP + index * self.ROW_HEIGHT
            self.panel.add_child(
                _IconMark(icon_id, Rect(int(position.x) + 12, int(y), 18, 18))
            )
            self.panel.add_child(
                Label(name, Vector2(position.x + 36, y + 3), font_size=12)
            )
            bar = ProgressBar(
                Vector2(bar_x, y + 5),
                Vector2(width - (bar_x - position.x) - 14, 9),
                value=0.0,
                fill_color=color,
            )
            self.bars[key] = bar
            self.panel.add_child(bar)
        ui_manager.add_element(self.panel, UILayer.HUD)

    def update(
        self,
        grid: GardenGrid,
        entity_manager: EntityManager,
        cell: Cell | None,
        weather: WeatherState | None = None,
    ) -> None:
        """Describe `cell`, or prompt for one.

        Args:
            grid: The plot.
            entity_manager: Where the plant and structure live.
            cell: The hovered cell, or None if the cursor has not been over
                the plot yet.
            weather: The sky, since a cold snap is one of the things that
                can be wrong with the plant standing there.
        """
        if cell is None or not grid.in_bounds(cell):
            self.title.set_text("Hover a tile to inspect it")
            self.panel.show_plant(None, 0.0)
            self.panel.detail = ""
            self.panel.degraded = False
            self.panel.soil = None
            for bar in self.bars.values():
                bar.set_value(0.0)
            return

        soil = grid.soil_at(cell)
        self.title.set_text(
            f"({cell[0]},{cell[1]}) {_SOIL_NAMES.get(soil.soil_type, '?')}"
        )
        self.panel.degraded = soil.is_chemically_degraded
        self.panel.soil = soil
        self.panel.weather = weather
        plant = self._plant_at(grid, entity_manager, cell)
        if plant is not None:
            species = SPECIES_TABLE.get(plant.species_id)
            name = species.display_name if species else plant.species_id
            self.panel.show_plant(plant, 0.0)
            detail = f"{name} - {plant.growth_stage} {round(plant.health * 100)}%"
            self.panel.detail = detail + (
                " - pulverizado" if plant.is_chemical_boosted else ""
            )
        else:
            self.panel.show_plant(None, 0.0)
            self.panel.detail = self._structure_name(grid, entity_manager, cell)
        for key, bar in self.bars.items():
            value = float(getattr(soil, key))
            bar.set_value(value)
            if key == "pest_pressure":
                bar.fill_color = pest_color(value)

    @staticmethod
    def _plant_at(
        grid: GardenGrid, entity_manager: EntityManager, cell: Cell
    ) -> PlantComponent | None:
        entity_id = grid.plant_at.get(cell)
        if entity_id is None:
            return None
        entity = entity_manager.get_entity(entity_id)
        if entity is None or not entity.has_component(PlantComponent):
            return None
        return entity.get_component(PlantComponent)

    @staticmethod
    def _structure_name(
        grid: GardenGrid, entity_manager: EntityManager, cell: Cell
    ) -> str:
        if cell in grid.automation_at:
            entity = entity_manager.get_entity(grid.automation_at[cell])
            if entity is not None and entity.has_component(AutomationComponent):
                kind = entity.get_component(AutomationComponent).kind
                return STRUCTURE_TABLE[kind].display_name
        return ""


class _InspectorCard(CardPanel):
    """The inspector's own drawing: the portrait box and the layer ladder.

    Attributes:
        plant: What to draw a portrait of, or None for an empty plot.
        detail: The line under the portrait -- a species and stage, or a
            structure's name.
        degraded: Whether to say the soil is chemically degraded.
        soil: The hovered cell, for the soil chip. None hides it.
        weather: The sky, since a cold snap is one of the things that can
            be wrong with a plant.
    """

    def __init__(self, position: Vector2, size: Vector2) -> None:
        """Initialize the card.

        Args:
            position: Top-left corner.
            size: Width and height.
        """
        super().__init__(position, size)
        self.plant: PlantComponent | None = None
        self.detail = ""
        self.degraded = False
        self.soil: SoilCell | None = None
        self.weather: WeatherState | None = None
        self._elapsed = 0.0

    def show_plant(self, plant: PlantComponent | None, elapsed: float) -> None:
        """Set the plant the portrait draws.

        Args:
            plant: The hovered cell's plant, or None.
            elapsed: Seconds of play, for the harvestable pulse.
        """
        self.plant = plant
        self._elapsed = elapsed

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card, the portrait box, the ladder, then the children."""
        super().render(renderer)
        box = Rect(self.rect.x + 12, self.rect.y + 32, PORTRAIT, PORTRAIT)
        renderer.draw_rect(box, PORTRAIT_FILL, border_radius=6)
        renderer.draw_rect(box, PORTRAIT_EDGE, width=1, border_radius=6)
        self._draw_portrait(renderer, box)
        self._draw_ladder(renderer, box)
        self._draw_soil(renderer)
        if self.detail:
            renderer.draw_text(
                self.detail,
                Vector2(self.rect.x + 12, box.bottom + 8),
                TEXT_COLOR,
                12,
            )
        if self.degraded:
            renderer.draw_text(
                "solo degradado",
                Vector2(self.rect.x + 12, self.rect.y + 12),
                DEGRADED_TEXT,
                11,
            )

    def _draw_soil(self, renderer: UIRenderer) -> None:
        """One chip for the ground's condition -- never four numbers.

        What a player can act on is "this bed is short of nitrogen", not a
        reading of each element. `nutrients.scarcest` picks the one worth
        naming, and a well-fed cell says so in a word.
        """
        if self.soil is None:
            return
        if self.plant is not None:
            # A planted cell reports the *plant*: what is wrong with its
            # conditions is more use than what the dirt holds.
            text = stress.describe(
                self.soil, SPECIES_TABLE.get(self.plant.species_id), self.weather
            )
            color = SOIL_RICH if text == stress.THRIVING else SOIL_LOW
        else:
            short = nutrients.scarcest(self.soil)
            text = f"low {short.short}" if short is not None else "soil in good heart"
            color = SOIL_LOW if short is not None else SOIL_RICH
        width, _ = renderer.get_text_size(text, 10)
        draw_badge(
            renderer,
            text,
            Vector2(self.rect.right - width - 30, self.rect.y + 8),
            icon_id="humus",
            color=color,
        )

    def _draw_portrait(self, renderer: UIRenderer, box: Rect) -> None:
        if self.plant is None:
            return
        species = SPECIES_TABLE.get(self.plant.species_id)
        # Scaled up from the 1.0 the plot draws at, so the same silhouette
        # fills a portrait box instead of a 48px tile.
        art.draw_plant(
            renderer,
            Vector2(box.centerx, box.centery + PORTRAIT * 0.16),
            species.color if species else Verdant.COLONIAL_500,
            self.plant.growth_stage,
            pop_scale=PORTRAIT_SCALE,
            elapsed=self._elapsed,
        )

    def _draw_ladder(self, renderer: UIRenderer, box: Rect) -> None:
        """Three rungs, the plant's own lit -- where it sits in the canopy."""
        species = (
            SPECIES_TABLE.get(self.plant.species_id) if self.plant is not None else None
        )
        x = box.right + 14
        renderer.draw_text("Camada", Vector2(x, box.y + 2), MUTED_TEXT, 10)
        for index, (name, layer) in enumerate(LAYER_RUNGS):
            y = box.y + 20 + index * 22
            lit = species is not None and species.canopy_layer == layer
            rung = Rect(x, y, 10, 10)
            renderer.draw_rect(
                rung, Verdant.COLONIAL_500 if lit else RUNG_OFF, border_radius=2
            )
            renderer.draw_text(
                name,
                Vector2(x + 16, y - 2),
                TEXT_COLOR if lit else MUTED_TEXT,
                11,
            )


class _IconMark(UIElement):
    """A static icon as a UI child, so a card can hold one like a label."""

    def __init__(self, icon_id: str, rect: Rect) -> None:
        super().__init__(Vector2(rect.x, rect.y), Vector2(rect.width, rect.height))
        self.icon_id = icon_id

    def render(self, renderer: UIRenderer) -> None:
        draw_icon(renderer, self.icon_id, self.rect)
