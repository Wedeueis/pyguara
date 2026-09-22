"""The garden HUD: the ribbon's three cards, a toast, and the inspector.

`Hud` owns the top ribbon (`ribbon.py` -- resources, weather, resilience)
and the message toast; `CellInspector` is the card under them in the right
column. Everything shown is real state: Sementes are
`PlayerEconomy.credits`, the clock is the scene's own, power is
`AutomationSystem`'s real budget, the status line is
`GardenConditions.phase`, the resilience bar is `scoring.compute_score`,
and the inspector reads the `SoilCell` and plant under the cursor.

Where each piece sits is `layout.py`'s call.
"""

from __future__ import annotations

from collections.abc import Callable

from games.quintal_cerrado import layout
from games.quintal_cerrado.components import (
    AutomationComponent,
    GardenConditions,
    PlantComponent,
    PlayerEconomy,
)
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.hud_widgets import CardPanel
from games.quintal_cerrado.icons import draw_icon
from games.quintal_cerrado.ribbon import ResilienceCard, ResourceCard, WeatherCard
from games.quintal_cerrado.scoring import Score
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.structures import STRUCTURE_TABLE
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

_SOIL_NAMES = {
    "raw_dirt": "Raw dirt",
    "tilled_dirt": "Tilled soil",
    "path": "Path",
    "water_pipe": "Water pipe",
}


class Hud:
    """Owns the ribbon's three cards and the message toast."""

    def __init__(self, ui_manager: UIManager, toast_y: int) -> None:
        """Build the ribbon and the toast.

        Args:
            ui_manager: The manager to add them to.
            toast_y: Where the toast's top edge sits in the right column.
        """
        self.resources = ResourceCard()
        self.weather = WeatherCard()
        self.resilience = ResilienceCard()
        for card in (self.resources, self.weather, self.resilience):
            ui_manager.add_element(card, UILayer.HUD)

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
    def clock_label(self) -> Label:
        """Day and time, on the weather card."""
        return self.weather.clock_label

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
        elapsed: float,
        power: tuple[int, int],
        compute_score: Callable[[], Score] | None = None,
    ) -> None:
        """Pull this frame's numbers out of the game.

        Args:
            dt: Seconds since the last frame, for the message and score
                timers.
            economy: The player's economy.
            conditions: The garden's pest situation.
            elapsed: Seconds of play, for the clock and the day arc.
            power: `(devices powered, capacity)` from the solar panels.
            compute_score: Returns a fresh `scoring.Score` for the
                resilience bar. Called at most every
                `ribbon.SCORE_INTERVAL` seconds, never per frame.
        """
        self.resources.refresh(economy, conditions, power)
        if compute_score is not None:
            self.resilience.refresh(dt, compute_score)
        if self._message_left > 0.0:
            self._message_left -= dt
            if self._message_left <= 0.0:
                self.message_label.set_text("")
                self.toast.visible = False

    def update_weather(
        self, condition_id: str, forecast: list[str], progress: float, elapsed: float
    ) -> None:
        """Hand the weather card the sky's state and the clock.

        Args:
            condition_id: `WeatherSystem.state.condition_id`.
            forecast: `WeatherSystem.forecast`, nearest first.
            progress: `WeatherSystem.condition_progress`.
            elapsed: Seconds of play.
        """
        self.weather.refresh(condition_id, forecast, progress, elapsed)


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
