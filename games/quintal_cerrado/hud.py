"""The garden HUD: a status card, a weather card, a toast and an inspector.

Each is a `hud_widgets.CardPanel` holding stock widgets -- `ProgressBar`
and `Label`, skinned by the theme -- plus `icons.py` glyphs, with nothing
invented. Everything shown is real state: Sementes are `PlayerEconomy.credits`,
the clock is the scene's own, power is `AutomationSystem`'s real budget, the
status line is `GardenConditions.phase`, and the inspector reads the
`SoilCell` and plant under the cursor.

Where each piece sits is `layout.py`'s call: the status card and the
weather card open the top ribbon, and the inspector and the message toast
share the column right of the grid.
"""

from __future__ import annotations

from games.quintal_cerrado import layout
from games.quintal_cerrado.clock import format_clock
from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    AutomationComponent,
    GardenConditions,
    PlantComponent,
    PlayerEconomy,
)
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.hud_widgets import CardPanel
from games.quintal_cerrado.icons import draw_icon
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.structures import STRUCTURE_TABLE
from games.quintal_cerrado.weather import WEATHER_TABLE
from pyguara.common.grid import Cell
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.text import Label
from pyguara.ui.design_system.tokens import Guara, Sand, Verdant, Water
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer

MESSAGE_SECONDS = 2.5
TOAST_HEIGHT = 34

_STATUS_TEXT = {
    "stable": "Garden: calm",
    "outbreak": "PEST OUTBREAK!",
    "resolved_organic": "Organic recovery",
    "resolved_chemical": "Chemical recovery",
}
_SOIL_NAMES = {
    "raw_dirt": "Raw dirt",
    "tilled_dirt": "Tilled soil",
    "path": "Path",
    "water_pipe": "Water pipe",
}


class Hud:
    """Builds the status card and the message toast, and keeps them current."""

    def __init__(self, ui_manager: UIManager, toast_y: int) -> None:
        """Build the status card and the message toast.

        Args:
            ui_manager: The manager to add them to.
            toast_y: Where the toast's top edge sits in the right column.
        """
        self.credits_label = Label("", Vector2(0, 0), font_size=20, color=Sand.C200)
        self.clock_label = Label("", Vector2(0, 0), font_size=12)
        self.power_label = Label("", Vector2(0, 0), font_size=12)
        self.status_label = Label("", Vector2(0, 0), font_size=12)
        self.seeds_label = Label("", Vector2(0, 0), font_size=12)
        self.message_label = Label("", Vector2(0, 0), font_size=13)
        self._message_left = 0.0

        card = layout.RESOURCE_CARD
        panel = CardPanel(Vector2(card.x, card.y), Vector2(card.width, card.height))
        for label, x, y in (
            (self.credits_label, 12, 10),
            (self.status_label, 12, 40),
            (self.clock_label, 150, 10),
            (self.power_label, 150, 27),
            (self.seeds_label, 150, 44),
        ):
            label.rect.x, label.rect.y = card.x + x, card.y + y
            panel.add_child(label)
        ui_manager.add_element(panel, UILayer.HUD)

        self.toast = CardPanel(
            Vector2(layout.COLUMN_X, toast_y),
            Vector2(layout.COLUMN_WIDTH, TOAST_HEIGHT),
        )
        self.message_label.rect.x = layout.COLUMN_X + 12
        self.message_label.rect.y = toast_y + 9
        self.toast.add_child(self.message_label)
        self.toast.visible = False
        ui_manager.add_element(self.toast, UILayer.HUD)

    def show_message(self, text: str) -> None:
        """Show `text` on the message line for `MESSAGE_SECONDS`.

        Args:
            text: A short line -- the panel is not wide.
        """
        self.message_label.set_text(text)
        self.toast.visible = bool(text)
        self._message_left = MESSAGE_SECONDS

    def update(
        self,
        dt: float,
        economy: PlayerEconomy,
        conditions: GardenConditions,
        elapsed: float,
        power: tuple[int, int],
    ) -> None:
        """Pull this frame's numbers out of the game.

        Args:
            dt: Seconds since the last frame, for the message timer.
            economy: The player's economy.
            conditions: The garden's pest situation.
            elapsed: Seconds of play, for the clock.
            power: `(devices powered, capacity)` from the solar panels.
        """
        self.credits_label.set_text(f"Sementes: {int(economy.credits)}")
        self.clock_label.set_text(format_clock(elapsed))
        used, capacity = power
        self.power_label.set_text(
            f"Power: {used}/{capacity}" if capacity else "Power: no solar"
        )
        self.status_label.set_text(_STATUS_TEXT.get(conditions.phase, conditions.phase))
        generic_seeds = economy.inventory.get(GENERIC_SEED_KEY, 0)
        self.seeds_label.set_text(f"Generic seed: {generic_seeds}")
        if self._message_left > 0.0:
            self._message_left -= dt
            if self._message_left <= 0.0:
                self.message_label.set_text("")
                self.toast.visible = False


class WeatherPanel:
    """Now, and what's coming -- a short weather forecast in the corner.

    A separate card rather than a line on the status card (`Hud`, beside
    it): that one is already packed, and this is meant to be glanced at ahead of an action ("rain's coming, skip
    watering"), not read alongside credits and the clock.
    """

    def __init__(self, ui_manager: UIManager) -> None:
        """Build the panel and add it to the HUD layer.

        Args:
            ui_manager: The manager to add it to.
        """
        self.now_label = Label("", Vector2(0, 0), font_size=14)
        self.forecast_label = Label("", Vector2(0, 0), font_size=12)

        card = layout.WEATHER_CARD
        panel = CardPanel(Vector2(card.x, card.y), Vector2(card.width, card.height))
        for label, offset_y in ((self.now_label, 12), (self.forecast_label, 38)):
            label.rect.x, label.rect.y = card.x + 12, card.y + offset_y
            panel.add_child(label)
        ui_manager.add_element(panel, UILayer.HUD)

    def update(self, condition_id: str, forecast: list[str]) -> None:
        """Show the current condition and what is coming after it.

        Args:
            condition_id: `WeatherSystem.state.condition_id`.
            forecast: `WeatherSystem.forecast`, nearest first.
        """
        current = WEATHER_TABLE.get(condition_id)
        self.now_label.set_text(f"Weather: {current.display_name if current else '?'}")
        names = [WEATHER_TABLE[c].display_name for c in forecast if c in WEATHER_TABLE]
        self.forecast_label.set_text(f"Next: {' then '.join(names)}" if names else "")


class CellInspector:
    """Shows the soil and plant under the cursor: a title and four meters."""

    METRICS = (
        ("Umidade", "moisture", "moisture", Water.C300),
        ("Húmus", "organic_matter", "humus", Verdant.COLONIAL_500),
        ("Sombra", "shade_level", "shade", Sand.C500),
        ("Pragas", "pest_pressure", "pests", Guara.C400),
    )
    ROW_HEIGHT = 30
    TOP = 34
    HEIGHT = TOP + ROW_HEIGHT * len(METRICS) + 8

    def __init__(self, ui_manager: UIManager, position: Vector2, width: int) -> None:
        """Build the card and add it to the HUD layer.

        Args:
            ui_manager: The manager to add the card to.
            position: Top-left corner, in screen space.
            width: Card width.
        """
        panel = CardPanel(position, Vector2(width, self.HEIGHT))
        self.title = Label("", Vector2(position.x + 12, position.y + 10), font_size=13)
        panel.add_child(self.title)

        self.bars: dict[str, ProgressBar] = {}
        for index, (name, key, icon_id, color) in enumerate(self.METRICS):
            y = position.y + self.TOP + index * self.ROW_HEIGHT
            panel.add_child(
                _IconMark(icon_id, Rect(int(position.x) + 12, int(y), 20, 20))
            )
            panel.add_child(Label(name, Vector2(position.x + 40, y + 3), font_size=12))
            bar = ProgressBar(
                Vector2(position.x + 110, y + 6),
                Vector2(width - 126, 9),
                value=0.0,
                fill_color=color,
            )
            self.bars[key] = bar
            panel.add_child(bar)
        ui_manager.add_element(panel, UILayer.HUD)

    def update(
        self, grid: GardenGrid, entity_manager: EntityManager, cell: Cell | None
    ) -> None:
        """Describe `cell`, or prompt for one.

        Args:
            grid: The plot.
            entity_manager: Where the plant and structure live.
            cell: The hovered cell, or None if the cursor has not been over
                the plot yet.
        """
        if cell is None or not grid.in_bounds(cell):
            self.title.set_text("Hover a tile to inspect it")
            for bar in self.bars.values():
                bar.set_value(0.0)
            return

        soil = grid.soil_at(cell)
        parts = [f"({cell[0]},{cell[1]}) {_SOIL_NAMES.get(soil.soil_type, '?')}"]
        if soil.is_chemically_degraded:
            parts.append("degraded")
        plant_text = self._plant_text(grid, entity_manager, cell)
        if plant_text:
            parts.append(plant_text)
        self.title.set_text(" | ".join(parts))
        for key, bar in self.bars.items():
            bar.set_value(float(getattr(soil, key)))

    @staticmethod
    def _plant_text(grid: GardenGrid, entity_manager: EntityManager, cell: Cell) -> str:
        entity_id = grid.plant_at.get(cell)
        if entity_id is not None:
            entity = entity_manager.get_entity(entity_id)
            if entity is not None and entity.has_component(PlantComponent):
                plant = entity.get_component(PlantComponent)
                species = SPECIES_TABLE.get(plant.species_id)
                name = species.display_name if species else plant.species_id
                text = f"{name}: {plant.growth_stage} ({round(plant.health * 100)}%)"
                return text + (" - sprayed" if plant.is_chemical_boosted else "")
        if cell in grid.automation_at:
            entity = entity_manager.get_entity(grid.automation_at[cell])
            if entity is not None and entity.has_component(AutomationComponent):
                kind = entity.get_component(AutomationComponent).kind
                return STRUCTURE_TABLE[kind].display_name
        return ""


class _IconMark(UIElement):
    """A static icon as a UI child, so a card can hold one like a label."""

    def __init__(self, icon_id: str, rect: Rect) -> None:
        super().__init__(Vector2(rect.x, rect.y), Vector2(rect.width, rect.height))
        self.icon_id = icon_id

    def render(self, renderer: UIRenderer) -> None:
        draw_icon(renderer, self.icon_id, self.rect)
