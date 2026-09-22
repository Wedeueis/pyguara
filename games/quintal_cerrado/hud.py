"""The garden HUD: a status panel, a menu button, and a hover cell inspector.

Both use the same `BevelPanel` + stock widget pattern `guara_falcao/hud.py`
does -- `ProgressBar` and `Label`, skinned by the theme, with nothing
invented. Everything shown is real state: Sementes are `PlayerEconomy.credits`,
the clock is the scene's own, power is `AutomationSystem`'s real budget, the
status line is `GardenConditions.phase`, and the inspector reads the
`SoilCell` and plant under the cursor.

The status panel lives in the left gutter beside the grid, not the top-left
corner: the tool bar's two rows start at x~123, and a panel anchored to the
corner would sit on top of the leftmost button.
"""

from __future__ import annotations

from games.quintal_cerrado.clock import format_clock
from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    AutomationComponent,
    GardenConditions,
    PlantComponent,
    PlayerEconomy,
)
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.structures import STRUCTURE_TABLE
from pyguara.common.grid import Cell
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.text import Label
from pyguara.ui.constraints import create_anchored_constraints
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.design_system.tokens import Verdant, Water
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIAnchor, UILayer

GUTTER_X = 14
PANEL_Y = 158
PANEL_SIZE = Vector2(164, 144)
MESSAGE_SECONDS = 2.5

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
    """Builds the status panel and Menu button, and keeps them current."""

    def __init__(self, ui_manager: UIManager) -> None:
        """Build the panel and button and add them to the HUD layer.

        Args:
            ui_manager: The manager to add them to.
        """
        self.credits_label = Label("", Vector2(0, 0), font_size=18)
        self.clock_label = Label("", Vector2(0, 0), font_size=13)
        self.power_label = Label("", Vector2(0, 0), font_size=13)
        self.status_label = Label("", Vector2(0, 0), font_size=14)
        self.seeds_label = Label("", Vector2(0, 0), font_size=13)
        self.message_label = Label("", Vector2(0, 0), font_size=13)
        self._message_left = 0.0

        panel = BevelPanel(Vector2(0, 0), PANEL_SIZE, border_width=2)
        panel.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT, offset_x=GUTTER_X, offset_y=PANEL_Y
        )
        for label, offset_y in (
            (self.credits_label, 8),
            (self.clock_label, 32),
            (self.power_label, 52),
            (self.status_label, 72),
            (self.seeds_label, 92),
            (self.message_label, 116),
        ):
            label.constraints = create_anchored_constraints(
                UIAnchor.TOP_LEFT, offset_x=10, offset_y=offset_y
            )
            panel.add_child(label)
        ui_manager.add_element(panel, UILayer.HUD)

        self.menu_button = BevelButton(
            "Menu (Esc)", Vector2(0, 0), Vector2(int(PANEL_SIZE.x), 34), skin=Skins.WOOD
        )
        self.menu_button.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT,
            offset_x=GUTTER_X,
            offset_y=PANEL_Y + int(PANEL_SIZE.y) + 8,
        )
        ui_manager.add_element(self.menu_button, UILayer.HUD)

    def show_message(self, text: str) -> None:
        """Show `text` on the message line for `MESSAGE_SECONDS`.

        Args:
            text: A short line -- the panel is not wide.
        """
        self.message_label.set_text(text)
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


class CellInspector:
    """Shows the soil and plant under the cursor: a title and four meters."""

    METRICS = (
        ("Moisture", "moisture", Water.C300),
        ("Humus", "organic_matter", Verdant.COLONIAL_500),
        ("Shade", "shade_level", Color(140, 150, 190)),
        ("Pests", "pest_pressure", Color(210, 90, 200)),
    )
    HEIGHT = 64

    def __init__(self, ui_manager: UIManager, position: Vector2, width: int) -> None:
        """Build the panel and add it to the HUD layer.

        Args:
            ui_manager: The manager to add the panel to.
            position: Top-left corner, in screen space.
            width: Panel width.
        """
        panel = BevelPanel(position, Vector2(width, self.HEIGHT), border_width=2)
        self.title = Label("", Vector2(position.x + 12, position.y + 7), font_size=13)
        panel.add_child(self.title)

        column = (width - 24) // len(self.METRICS)
        self.bars: dict[str, ProgressBar] = {}
        for index, (name, key, color) in enumerate(self.METRICS):
            x = position.x + 12 + index * column
            panel.add_child(Label(name, Vector2(x, position.y + 27), font_size=11))
            bar = ProgressBar(
                Vector2(x, position.y + 44),
                Vector2(column - 14, 9),
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
        self.title.set_text("  |  ".join(parts))
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
