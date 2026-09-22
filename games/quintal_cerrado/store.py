"""The store: a scene pushed over the garden, where structures are bought.

Follows `guara_falcao/menus.py`'s pattern for a pushed overlay -- a scrim
and a panel on `UILayer.OVERLAY`, pushed with `pause_below=True` so the
garden freezes but keeps rendering behind it. Freezing is deliberate: a
store you can browse while your plants die of pests is a store you rush.

The store is a catalogue and a till, not a shop floor. Buying a structure
puts it in `PlayerEconomy.inventory` and closes the store; the garden then
hands the player a placement tool for it (see `scenes.py`). A structure
whose tech-tree requirement has not been *placed* yet shows as locked --
`structures.is_unlocked` is the one place that is decided.
"""

from __future__ import annotations

from collections.abc import Callable

from games.quintal_cerrado import structures
from games.quintal_cerrado.components import PlayerEconomy
from games.quintal_cerrado.overlay import OverlayScene, Scrim
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.keys import ESCAPE, KEY_O
from pyguara.ui.base import UIElement
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer

PANEL_WIDTH = 620
CARD_WIDTH = 588
CARD_HEIGHT = 66
CARD_GAP = 8


class StoreOverlayScene(OverlayScene):
    """Lists every structure, and sells the ones the player has unlocked."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        economy: PlayerEconomy,
        on_bought: Callable[[str], None],
        width: int,
        height: int,
    ) -> None:
        """Initialize the scene.

        Args:
            event_dispatcher: The game's dispatcher.
            economy: Who pays, and whose inventory and unlocks are read.
            on_bought: Called with the structure kind once a purchase goes
                through and the store has closed.
            width: Screen width.
            height: Screen height.
        """
        super().__init__(
            "StoreOverlayScene", event_dispatcher, close_keys=(ESCAPE, KEY_O)
        )
        self._economy = economy
        self._on_bought = on_bought
        self._width = width
        self._height = height
        self.buy_buttons: dict[str, BevelButton] = {}
        self._message: Label | None = None

    def _build(self) -> None:
        """Build the store's panel, one card per structure, and Close."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear(UILayer.OVERLAY)
        ui_manager.add_element(Scrim(self._width, self._height), UILayer.OVERLAY)

        table = structures.STRUCTURE_TABLE
        panel_height = 66 + len(table) * (CARD_HEIGHT + CARD_GAP) + 56
        panel = BevelPanel(
            Vector2(
                (self._width - PANEL_WIDTH) // 2, (self._height - panel_height) // 2
            ),
            Vector2(PANEL_WIDTH, panel_height),
            border_width=3,
            shadow=True,
        )
        panel.add_child(
            Label("STORE", Vector2(panel.rect.x + 18, panel.rect.y + 16), 24)
        )
        panel.add_child(
            Label(
                f"Sementes: {int(self._economy.credits)}",
                Vector2(panel.rect.right - 190, panel.rect.y + 22),
                font_size=16,
            )
        )

        for index, structure in enumerate(table.values()):
            card_y = panel.rect.y + 60 + index * (CARD_HEIGHT + CARD_GAP)
            panel.add_child(self._card(structure, panel.rect.x + 16, card_y))

        self._message = Label(
            "", Vector2(panel.rect.x + 18, panel.rect.bottom - 40), font_size=14
        )
        panel.add_child(self._message)
        close = BevelButton(
            "Close (Esc)",
            Vector2(panel.rect.right - 158, panel.rect.bottom - 48),
            Vector2(140, 34),
            skin=Skins.WOOD,
        )
        close.on_click = lambda _element: self._close()
        panel.add_child(close)

        ui_manager.add_element(panel, UILayer.OVERLAY)
        first_open = next((b for b in self.buy_buttons.values() if b.enabled), close)
        ui_manager.set_focus(first_open)

    def _card(self, structure: structures.Structure, x: int, y: int) -> BevelPanel:
        """One structure's row: name, blurb, price, stock, and a Buy button."""
        card = BevelPanel(
            Vector2(x, y), Vector2(CARD_WIDTH, CARD_HEIGHT), border_width=1, bevel=False
        )
        unlocked = structures.is_unlocked(self._economy, structure.kind)
        owned = self._economy.inventory.get(structure.kind, 0)

        card.add_child(Label(structure.display_name, Vector2(x + 12, y + 8), 16))
        blurb = structure.description
        if not unlocked and structure.requires is not None:
            required = structures.STRUCTURE_TABLE[structure.requires].display_name
            blurb = f"Locked: place a {required} first."
        card.add_child(Label(blurb, Vector2(x + 12, y + 36), 12))
        card.add_child(
            Label(f"{structure.cost} Sementes", Vector2(x + 340, y + 10), 14)
        )
        card.add_child(Label(f"Owned: {owned}", Vector2(x + 340, y + 36), 12))

        button = BevelButton(
            "Buy" if unlocked else "Locked",
            Vector2(x + CARD_WIDTH - 116, y + 14),
            Vector2(104, 38),
            skin=Skins.SAGE if unlocked else Skins.GHOST,
        )
        button.set_enabled(unlocked)
        button.on_click = self._buy_handler(structure.kind)
        self.buy_buttons[structure.kind] = button
        card.add_child(button)
        return card

    def _buy_handler(self, kind: str) -> Callable[[UIElement], None]:
        def _handler(_element: UIElement) -> None:
            self._buy(kind)

        return _handler

    def _buy(self, kind: str) -> None:
        result = structures.buy_structure(self._economy, kind)
        if result == structures.BROKE:
            if self._message is not None:
                self._message.set_text("Not enough Sementes")
            return
        if result != structures.OK:
            return
        self._close()
        self._on_bought(kind)
