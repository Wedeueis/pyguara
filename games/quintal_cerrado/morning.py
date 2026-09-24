"""The morning report: what the garden did while the player slept.

A turn-based night resolves everything at once, so without this the player
wakes to a changed plot and no account of why: a plant gone, Sementes they
did not earn by hand, pests two cells further along. The report is the
night's receipt.

It reads a `systems/day_resolver.DayReport` and nothing else -- it cannot
disagree with what the night did, because the night is what filled it in.
Lines with nothing to say are left out rather than shown as zero, so a
quiet night is a short card and a bad one is a long one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from games.quintal_cerrado.hud_widgets import (
    MUTED_TEXT,
    TEXT_COLOR,
    CardPanel,
    draw_card,
)
from games.quintal_cerrado.icons import draw_icon
from games.quintal_cerrado.overlay import OverlayScene, Scrim
from games.quintal_cerrado.seasons import SEASON_TABLE
from games.quintal_cerrado.systems.day_resolver import DayReport
from games.quintal_cerrado.weather import WEATHER_TABLE
from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer
from pyguara.input.keys import ESCAPE, RETURN, SPACE
from pyguara.scene.manager import SceneManager
from pyguara.ui.base import UIElement
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import BevelButton, Skins
from pyguara.ui.design_system.tokens import Sand, Verdant
from pyguara.ui.manager import UIManager
from pyguara.ui.types import TextAlign, UILayer

CARD_WIDTH = 460
CARD_CHROME = 200
"""Title, the two skies and the button -- everything but the rows."""
ROW_HEIGHT = 30
ROW_ICON = 20

GOOD = Verdant.SAGE_100
BAD = Color(226, 110, 92)
COIN = Sand.C300
SEASON = Sand.C200
"""The season line: news, not good news and not bad -- a dry season is
welcome or ruinous depending entirely on what is in the ground."""


@dataclass(frozen=True)
class _Line:
    """One line of the report: an icon, some text, and its mood.

    Attributes:
        icon_id: An `icons.ICONS` key.
        text: What happened, in words.
        color: The text colour -- bad news reads red, a gain reads warm.
    """

    icon_id: str
    text: str
    color: Color = field(default_factory=lambda: TEXT_COLOR)


def report_lines(report: DayReport) -> list[_Line]:
    """Turn a night into the lines worth reading.

    Only what happened: a night with no weeds does not get a "0 weeds"
    line, because a report that always has the same shape stops being read.

    Args:
        report: What the night did.

    Returns:
        The lines, in the order the card shows them.
    """
    lines: list[_Line] = []
    season = SEASON_TABLE.get(report.season_arrived)
    if season is not None:
        # First, and never counted as a quiet night: the season is the one
        # thing in the report that changes what tomorrow is *for*. Its own
        # blurb says what changes, because "Águas" alone does not.
        lines.append(
            _Line(season.icon_id, f"{season.display_name}. {season.blurb}", SEASON)
        )
    if report.outbreak_started:
        lines.append(_Line("pests", "Pests broke out in the night", BAD))
    if report.outbreak_resolved:
        how = (
            "the slow way"
            if report.outbreak_resolved == "organic"
            else "with chemicals"
        )
        lines.append(_Line("pests", f"The outbreak is over, {how}", GOOD))
    if report.ripened:
        lines.append(
            _Line("harvest", f"Ready to harvest: {_names(report.ripened)}", GOOD)
        )
    if report.stages_grown:
        lines.append(_Line("humus", f"Grew: {_names(report.stages_grown)}"))
    if report.lost:
        lines.append(_Line("pests", f"Lost to pests: {_names(report.lost)}", BAD))
    if report.drone_harvests:
        lines.append(
            _Line("store", f"The drone collected {report.drone_harvests}", GOOD)
        )
    if report.solar_income:
        lines.append(_Line("sun", f"The panels paid {report.solar_income}", COIN))
    if report.weeds_sprouted:
        lines.append(
            _Line(
                "plant_generic", f"{report.weeds_sprouted} new weed(s) took hold", BAD
            )
        )
    if not lines:
        lines.append(_Line("moon", "A quiet night. Nothing to report."))
    return lines


def _names(entries: list[str]) -> str:
    """`"2x Guandu, Baru"` -- counted, and never longer than its line.

    Counted because a night that grew four guandu should say so once, not
    print the same word four times.

    Args:
        entries: Display names, one per plant.

    Returns:
        The line's text.
    """
    counted: dict[str, int] = {}
    for name in entries:
        counted[name] = counted.get(name, 0) + 1
    parts = [
        f"{count}x {name}" if count > 1 else name for name, count in counted.items()
    ]
    if len(parts) <= 3:
        return ", ".join(parts)
    return f"{', '.join(parts[:2])} and {len(parts) - 2} more"


class _ReportBody(UIElement):
    """Draws the weather strip and the report's icon rows.

    A widget rather than a pile of labels: every row is an icon plus text,
    and `Label` cannot draw an icon.
    """

    def __init__(self, rect: Rect, report: DayReport) -> None:
        """Initialize the body.

        Args:
            rect: Where the rows are drawn.
            report: The night to render.
        """
        super().__init__(Vector2(rect.x, rect.y), Vector2(rect.width, rect.height))
        self.report = report
        self.lines = report_lines(report)

    def render(self, renderer: UIRenderer) -> None:
        """Draw the two skies, then one row per line."""
        self._draw_weather(renderer)
        y = self.rect.y + 52
        for line in self.lines:
            draw_icon(renderer, line.icon_id, Rect(self.rect.x, y, ROW_ICON, ROW_ICON))
            renderer.draw_text(
                line.text, Vector2(self.rect.x + ROW_ICON + 10, y + 3), line.color, 13
            )
            y += ROW_HEIGHT

    def _draw_weather(self, renderer: UIRenderer) -> None:
        """Last night's sky and today's, side by side."""
        for index, (label, condition_id) in enumerate(
            (
                ("night", self.report.weather_id),
                ("today", self.report.next_weather_id),
            )
        ):
            x = self.rect.x + index * 150
            renderer.draw_text(label, Vector2(x, self.rect.y), MUTED_TEXT, 10)
            draw_icon(renderer, condition_id, Rect(x, self.rect.y + 14, 24, 24))
            condition = WEATHER_TABLE.get(condition_id)
            renderer.draw_text(
                condition.display_name if condition else "?",
                Vector2(x + 30, self.rect.y + 20),
                TEXT_COLOR,
                13,
            )


class MorningScene(OverlayScene):
    """The overlay a night ends on."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        report: DayReport,
        day: int,
        on_closed: Callable[[], None],
        width: int,
        height: int,
    ) -> None:
        """Initialize the scene.

        Args:
            event_dispatcher: The game's dispatcher.
            report: What the night did.
            day: The morning's day number, for the title.
            on_closed: Called when the player dismisses the report -- the
                garden uses it to start its sunrise.
            width: Screen width.
            height: Screen height.
        """
        super().__init__(
            "MorningScene", event_dispatcher, close_keys=(ESCAPE, SPACE, RETURN)
        )
        self.report = report
        self.day = day
        self._on_closed = on_closed
        self._width = width
        self._height = height

    def _build(self) -> None:
        """Build the card: a title, the two skies, the rows, and a button."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear(UILayer.OVERLAY)
        ui_manager.add_element(Scrim(self._width, self._height), UILayer.OVERLAY)

        # Sized to what the night has to say: a quiet night is a short
        # card, a bad one a long one.
        lines = len(report_lines(self.report))
        size = Vector2(CARD_WIDTH, CARD_CHROME + lines * ROW_HEIGHT)
        origin = Vector2((self._width - size.x) // 2, (self._height - size.y) // 2)
        card = _MorningCard(origin, size)
        ui_manager.add_element(card, UILayer.OVERLAY)

        card.add_child(
            Label(
                f"Manhã do dia {self.day}",
                Vector2(origin.x, origin.y + 24),
                font_size=22,
                color=Sand.C200,
                width=size.x,
                align=TextAlign.CENTER,
            )
        )
        card.add_child(
            _ReportBody(
                Rect(
                    int(origin.x) + 36,
                    int(origin.y) + 70,
                    int(size.x) - 72,
                    lines * ROW_HEIGHT + 52,
                ),
                self.report,
            )
        )

        button = BevelButton(
            "Bom dia",
            Vector2(origin.x + (size.x - 200) // 2, origin.y + size.y - 62),
            Vector2(200, 44),
            skin=Skins.SAGE,
        )
        button.on_click = lambda _element: self._close()
        ui_manager.add_element(button, UILayer.OVERLAY)
        ui_manager.set_focus(button)

    def _close(self) -> None:
        """Dismiss the report, and let the garden wake up."""
        was_current = self.container.get(SceneManager).current_scene is self
        super()._close()
        if was_current:
            self._on_closed()


class _MorningCard(CardPanel):
    """The report's own card -- the HUD's surface, at overlay size."""

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card, then its children."""
        draw_card(renderer, self.rect, radius=10)
        for child in self.children:
            if child.visible:
                child.render(renderer)
