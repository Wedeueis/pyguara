"""The pause menu: resume, save, evaluate, or save and quit to the title.

An overlay pushed over the frozen garden (see `overlay.py`). It owns no game
logic -- each button calls back into the garden, which is the one place that
knows how to save, score and unwind to the title screen.
"""

from __future__ import annotations

from collections.abc import Callable

from games.quintal_cerrado.overlay import OverlayScene, Scrim
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.keys import ESCAPE
from pyguara.ui.base import UIElement
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer

PANEL_SIZE = Vector2(360, 340)
BUTTON_SIZE = Vector2(280, 46)


class PauseScene(OverlayScene):
    """Pause menu over a frozen garden."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        on_save: Callable[[], bool],
        on_evaluate: Callable[[], None],
        on_quit: Callable[[], None],
        width: int,
        height: int,
    ) -> None:
        """Initialize the scene.

        Args:
            event_dispatcher: The game's dispatcher.
            on_save: Writes a save; returns whether it worked.
            on_evaluate: Opens the evaluation, once this menu has closed.
            on_quit: Saves and unwinds to the title screen.
            width: Screen width.
            height: Screen height.
        """
        super().__init__("PauseScene", event_dispatcher, close_keys=(ESCAPE,))
        self._on_save = on_save
        self._on_evaluate = on_evaluate
        self._on_quit = on_quit
        self._width = width
        self._height = height
        self.message: Label | None = None

    def _build(self) -> None:
        """Build the scrim, panel, title, message line and four buttons."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear(UILayer.OVERLAY)
        ui_manager.add_element(Scrim(self._width, self._height), UILayer.OVERLAY)

        panel = BevelPanel(
            Vector2(
                (self._width - PANEL_SIZE.x) // 2, (self._height - PANEL_SIZE.y) // 2
            ),
            PANEL_SIZE,
            border_width=3,
            shadow=True,
        )
        ui_manager.add_element(panel, UILayer.OVERLAY)
        ui_manager.add_element(
            Label("PAUSED", Vector2(panel.rect.x + 40, panel.rect.y + 22), 24),
            UILayer.OVERLAY,
        )
        self.message = Label(
            "", Vector2(panel.rect.x + 40, panel.rect.bottom - 34), font_size=14
        )
        ui_manager.add_element(self.message, UILayer.OVERLAY)

        column = BoxContainer(
            Vector2(panel.rect.x + 40, panel.rect.y + 70),
            Vector2(BUTTON_SIZE.x, 220),
            spacing=10,
        )
        for text, skin, handler in (
            ("Resume", Skins.SAGE, lambda _e: self._close()),
            ("Save game", Skins.WOOD, self._save),
            ("Evaluate garden", Skins.WOOD, self._evaluate),
            ("Save & quit to title", Skins.WOOD, lambda _e: self._on_quit()),
        ):
            button = BevelButton(text, Vector2(0, 0), BUTTON_SIZE, skin=skin)
            button.on_click = handler
            column.add_child(button)
        ui_manager.add_element(column, UILayer.OVERLAY)
        ui_manager.set_focus(column.children[0])

    def _save(self, _element: UIElement) -> None:
        if self.message is not None:
            self.message.set_text("Garden saved" if self._on_save() else "Save failed!")

    def _evaluate(self, _element: UIElement) -> None:
        self._close()
        self._on_evaluate()
