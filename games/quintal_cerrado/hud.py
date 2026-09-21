"""The garden HUD: Sementes, the garden's pest status, and a transient message.

Deliberately small. It is the minimum the Phase 3 economy and pest fork
need to be playable -- a player cannot answer an outbreak they cannot see,
or spend money they cannot count -- and the same `BevelPanel` +
`create_anchored_constraints` pattern `guara_falcao/hud.py` uses, so a
later phase's fuller HUD (clock, tool inspector, score) grows out of it
rather than replacing it.

Every readout is real state: credits are `PlayerEconomy.credits`, the
status line is `GardenConditions.phase`, and the message line is whatever
the scene last told the player, shown for a few seconds and then cleared.
"""

from __future__ import annotations

from games.quintal_cerrado.components import GardenConditions, PlayerEconomy
from pyguara.common.types import Vector2
from pyguara.ui.components.text import Label
from pyguara.ui.constraints import create_anchored_constraints
from pyguara.ui.design_system import BevelPanel
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIAnchor, UILayer

PANEL_SIZE = Vector2(160, 82)
MESSAGE_SECONDS = 2.5

_STATUS_TEXT = {
    "stable": "Garden: calm",
    "outbreak": "PEST OUTBREAK!",
    "resolved_organic": "Organic recovery",
    "resolved_chemical": "Chemical recovery",
}


class Hud:
    """Builds the HUD, and keeps it showing what the game actually holds."""

    def __init__(self, ui_manager: UIManager) -> None:
        """Build the panel and add it to the HUD layer.

        Args:
            ui_manager: The manager to add the panel to.
        """
        self.credits_label = Label("", Vector2(0, 0), font_size=18)
        self.status_label = Label("", Vector2(0, 0), font_size=14)
        self.message_label = Label("", Vector2(0, 0), font_size=13)
        self._message_left = 0.0

        panel = BevelPanel(Vector2(0, 0), PANEL_SIZE, border_width=2)
        panel.constraints = create_anchored_constraints(UIAnchor.TOP_LEFT, margin=14)
        for label, offset_y in (
            (self.credits_label, 10),
            (self.status_label, 36),
            (self.message_label, 58),
        ):
            label.constraints = create_anchored_constraints(
                UIAnchor.TOP_LEFT, offset_x=10, offset_y=offset_y
            )
            panel.add_child(label)
        ui_manager.add_element(panel, UILayer.HUD)

    def show_message(self, text: str) -> None:
        """Show `text` on the message line for `MESSAGE_SECONDS`.

        Args:
            text: A short line -- the panel is not wide.
        """
        self.message_label.set_text(text)
        self._message_left = MESSAGE_SECONDS

    def update(
        self, dt: float, economy: PlayerEconomy, conditions: GardenConditions
    ) -> None:
        """Pull this frame's numbers out of the components.

        Args:
            dt: Seconds since the last frame, for the message timer.
            economy: The player's economy.
            conditions: The garden's pest situation.
        """
        self.credits_label.set_text(f"Sementes: {int(economy.credits)}")
        self.status_label.set_text(_STATUS_TEXT.get(conditions.phase, conditions.phase))
        if self._message_left > 0.0:
            self._message_left -= dt
            if self._message_left <= 0.0:
                self.message_label.set_text("")
