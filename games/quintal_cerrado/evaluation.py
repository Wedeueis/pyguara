"""The evaluation: the garden's Agroecological Score, shown as an overlay.

The PRD's closing beat ("Automatically triggers a save and displays victory
metrics"). The garden saves *before* opening this, so what is scored is
exactly what is on disk. Opened from the pause menu, and once on its own when
a session reaches `scenes.EVALUATION_TIME`; the player can always keep
playing afterwards.
"""

from __future__ import annotations

from collections.abc import Callable

from games.quintal_cerrado.overlay import OverlayScene, Scrim
from games.quintal_cerrado.scoring import Score
from pyguara.common.types import Color, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.keys import ESCAPE
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.design_system.tokens import Guara, Verdant, Water
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer

PANEL_SIZE = Vector2(520, 420)
BAR_SIZE = Vector2(260, 14)


class EvaluationScene(OverlayScene):
    """The score breakdown and the grade it earned."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        score: Score,
        on_quit: Callable[[], None],
        width: int,
        height: int,
    ) -> None:
        """Initialize the scene.

        Args:
            event_dispatcher: The game's dispatcher.
            score: The score to show.
            on_quit: Saves and unwinds to the title screen.
            width: Screen width.
            height: Screen height.
        """
        super().__init__("EvaluationScene", event_dispatcher, close_keys=(ESCAPE,))
        self.score = score
        self._on_quit = on_quit
        self._width = width
        self._height = height
        self.bars: dict[str, ProgressBar] = {}

    def _build(self) -> None:
        """Build the panel: grade, total, four bars, and two buttons."""
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
        x, y = panel.rect.x + 32, panel.rect.y + 22

        for label in (
            Label("EVALUATION", Vector2(x, y), 24),
            Label(self.score.grade, Vector2(x, y + 40), 20),
            Label(f"Score: {self.score.total} / 1000", Vector2(x, y + 72), 16),
        ):
            ui_manager.add_element(label, UILayer.OVERLAY)

        for index, (key, name, value, color) in enumerate(
            (
                ("soil", "Soil health", self.score.soil_health, Verdant.COLONIAL_500),
                ("biodiversity", "Biodiversity", self.score.biodiversity, Guara.C500),
                ("revenue", "Revenue", self.score.revenue, Color(226, 190, 96)),
                ("organic", "Organic sales", self.score.organic, Water.C300),
            )
        ):
            row_y = y + 116 + index * 46
            ui_manager.add_element(
                Label(f"{name}  {round(value * 100)}%", Vector2(x, row_y), 14),
                UILayer.OVERLAY,
            )
            bar = ProgressBar(
                Vector2(x, row_y + 22), BAR_SIZE, value=value, fill_color=color
            )
            self.bars[key] = bar
            ui_manager.add_element(bar, UILayer.OVERLAY)

        keep = BevelButton(
            "Keep playing",
            Vector2(panel.rect.x + 32, panel.rect.bottom - 62),
            Vector2(210, 44),
            skin=Skins.SAGE,
        )
        keep.on_click = lambda _e: self._close()
        quit_button = BevelButton(
            "Save & quit to title",
            Vector2(panel.rect.right - 242, panel.rect.bottom - 62),
            Vector2(210, 44),
            skin=Skins.WOOD,
        )
        quit_button.on_click = lambda _e: self._on_quit()
        ui_manager.add_element(keep, UILayer.OVERLAY)
        ui_manager.add_element(quit_button, UILayer.OVERLAY)
        ui_manager.set_focus(keep)
