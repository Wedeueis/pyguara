"""The top ribbon: what you have, what the sky is doing, how the plot is.

Three `CardPanel`s, each reading real state and nothing else -- the
credits are `PlayerEconomy.credits`, the arc is the scene's own clock, the
forecast is `WeatherSystem`'s queue, and the resilience bar is exactly the
`scoring.compute_score()` the evaluation screen grades you on. No
invented rates, no "+12/min".

They draw their own chips, arc and gauge because none of that is a stock
widget: a chip is an icon and a number in a pill (`hud_widgets.draw_badge`),
and the day arc is a half-circle of line segments with the sun or the moon
riding along it. Plain text lines stay ordinary `Label` children.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from games.quintal_cerrado import layout
from games.quintal_cerrado.clock import DAY_LENGTH, format_clock
from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    GardenConditions,
    PlayerEconomy,
)
from games.quintal_cerrado.hud_widgets import MUTED_TEXT, CardPanel, draw_badge
from games.quintal_cerrado.icons import draw_icon
from games.quintal_cerrado.scoring import Score
from games.quintal_cerrado.weather import WEATHER_TABLE
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.text import Label
from pyguara.ui.design_system.tokens import Sand, Verdant, Wood

ALERT = Color(214, 96, 80)
"""The pest chip's colour while an outbreak is live."""

ARC_TRACK = Wood.C400.lerp(Color(35, 28, 38), 0.4)
ARC_SEGMENTS = 24
FORECAST_LENGTH = 2
"""How many upcoming conditions the card has room for."""

SCORE_INTERVAL = 0.5
"""Seconds between `compute_score` runs -- it walks every cell and plant,
and a bar that moves twice a second is already livelier than the garden."""

_STATUS_TEXT = {
    "stable": "Garden: calm",
    "outbreak": "PEST OUTBREAK!",
    "resolved_organic": "Organic recovery",
    "resolved_chemical": "Chemical recovery",
}


class ResourceCard(CardPanel):
    """Sementes, big; then power, generic seed and the pest status.

    Attributes:
        credits_label: The Sementes count, as drawn.
        status_label: `GardenConditions.phase` in words.
        power: `(devices powered, capacity)` from the solar panels.
        generic_seeds: How many generic seeds are in the inventory.
        alarmed: Whether the pest status is an outbreak.
    """

    def __init__(self) -> None:
        """Build the card at `layout.RESOURCE_CARD`."""
        card = layout.RESOURCE_CARD
        super().__init__(Vector2(card.x, card.y), Vector2(card.width, card.height))
        self.credits_label = Label(
            "0", Vector2(card.x + 48, card.y + 10), font_size=24, color=Sand.C200
        )
        self.status_label = Label("", Vector2(card.x + 12, card.y + 44), font_size=12)
        self.add_child(self.credits_label)
        self.add_child(self.status_label)
        self.power = (0, 0)
        self.generic_seeds = 0
        self.alarmed = False

    def refresh(
        self,
        economy: PlayerEconomy,
        conditions: GardenConditions,
        power: tuple[int, int],
    ) -> None:
        """Take this frame's numbers.

        Named `refresh` rather than `update`: `UIElement.update(dt)` is the
        engine's own per-frame lifecycle hook, which `UIManager` calls on
        every element, so a card overriding it with different arguments
        crashes the first frame.

        Args:
            economy: The player's economy.
            conditions: The garden's pest situation.
            power: `(devices powered, capacity)`.
        """
        self.credits_label.set_text(str(int(economy.credits)))
        self.status_label.set_text(_STATUS_TEXT.get(conditions.phase, conditions.phase))
        self.alarmed = conditions.phase == "outbreak"
        self.status_label.set_color(ALERT if self.alarmed else None)
        self.power = power
        self.generic_seeds = economy.inventory.get(GENERIC_SEED_KEY, 0)

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card, the pouch, the seed glyph and the two chips."""
        super().render(renderer)
        draw_icon(
            renderer, "seed_pouch", Rect(self.rect.x + 8, self.rect.y + 10, 34, 34)
        )

        # The seed glyph trails the number, so it moves with its width.
        number_w, _ = renderer.get_text_size(self.credits_label.text, 24)
        draw_icon(
            renderer,
            "seed",
            Rect(self.credits_label.rect.x + number_w + 6, self.rect.y + 17, 16, 16),
        )

        used, capacity = self.power
        chip_x = self.rect.x + 172
        draw_badge(
            renderer,
            f"{used}/{capacity}" if capacity else "sem sol",
            Vector2(chip_x, self.rect.y + 10),
            icon_id="sun",
            color=MUTED_TEXT if capacity else MUTED_TEXT.lerp(Color(35, 28, 38), 0.3),
        )
        draw_badge(
            renderer,
            f"x{self.generic_seeds}",
            Vector2(chip_x, self.rect.y + 34),
            icon_id="plant_generic",
        )


class WeatherCard(CardPanel):
    """Now, what is coming, how far through the day it is.

    A card of its own rather than a line on the resource card: it is
    glanced at *before* an action ("rain's coming, skip watering"), not
    read alongside the credits.

    Attributes:
        now_label: The current condition's name.
        clock_label: Day and time, from `clock.format_clock`.
        condition_id: What the sky is doing now.
        forecast: The upcoming condition ids, nearest first.
        progress: How far the current condition has run, 0.0-1.0.
        day_phase: How far through the day it is, 0.0-1.0.
    """

    def __init__(self) -> None:
        """Build the card at `layout.WEATHER_CARD`."""
        card = layout.WEATHER_CARD
        super().__init__(Vector2(card.x, card.y), Vector2(card.width, card.height))
        self.now_label = Label(
            "", Vector2(card.x + 50, card.y + 10), font_size=15, color=Sand.C200
        )
        self.clock_label = Label("", Vector2(card.x + 50, card.y + 32), font_size=12)
        self.add_child(self.now_label)
        self.add_child(self.clock_label)
        self.condition_id = ""
        self.forecast: list[str] = []
        self.progress = 0.0
        self.day_phase = 0.0

    def refresh(
        self,
        condition_id: str,
        forecast: list[str],
        progress: float,
        elapsed: float,
    ) -> None:
        """Take the sky's state and the clock.

        `refresh`, not `update` -- see `ResourceCard.refresh`.

        Args:
            condition_id: `WeatherSystem.state.condition_id`.
            forecast: `WeatherSystem.forecast`, nearest first.
            progress: `WeatherSystem.condition_progress`.
            elapsed: Seconds of play.
        """
        self.condition_id = condition_id
        condition = WEATHER_TABLE.get(condition_id)
        self.now_label.set_text(condition.display_name if condition else "?")
        self.clock_label.set_text(format_clock(elapsed))
        self.forecast = [c for c in forecast if c in WEATHER_TABLE][:FORECAST_LENGTH]
        self.progress = progress
        self.day_phase = (elapsed % DAY_LENGTH) / DAY_LENGTH

    @property
    def marker_icon(self) -> str:
        """The sun by day and the moon by night.

        The first half of a day is light and the second half dark, the
        same split `clock.darkness()` eases over.
        """
        return "sun" if self.day_phase < 0.5 else "moon"

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card, the condition, the forecast and the day arc."""
        super().render(renderer)
        draw_icon(
            renderer, self.condition_id, Rect(self.rect.x + 8, self.rect.y + 12, 36, 36)
        )

        # How much of this condition is left, under its name.
        track = Rect(self.rect.x + 50, self.rect.y + 50, 96, 4)
        renderer.draw_rect(track, ARC_TRACK, border_radius=2)
        filled = int(track.width * max(0.0, min(1.0, self.progress)))
        if filled:
            renderer.draw_rect(
                Rect(track.x, track.y, filled, track.height),
                Sand.C500,
                border_radius=2,
            )

        renderer.draw_text(
            "a seguir", Vector2(self.rect.x + 164, self.rect.y + 8), MUTED_TEXT, 10
        )
        for index, condition_id in enumerate(self.forecast):
            draw_icon(
                renderer,
                condition_id,
                Rect(self.rect.x + 164 + index * 26, self.rect.y + 24, 22, 22),
            )

        self._draw_day_arc(renderer)

    def _draw_day_arc(self, renderer: UIRenderer) -> None:
        """A half-circle of night-to-night, with the sun or moon on it."""
        center = Vector2(self.rect.right - 46, self.rect.bottom - 12)
        radius = 30.0
        points = [
            Vector2(
                center.x + math.cos(math.pi + math.pi * i / ARC_SEGMENTS) * radius,
                center.y + math.sin(math.pi + math.pi * i / ARC_SEGMENTS) * radius,
            )
            for i in range(ARC_SEGMENTS + 1)
        ]
        for start, end in zip(points, points[1:], strict=False):
            renderer.draw_line(start, end, ARC_TRACK, width=2)

        angle = math.pi + math.pi * max(0.0, min(1.0, self.day_phase))
        marker = Vector2(
            center.x + math.cos(angle) * radius, center.y + math.sin(angle) * radius
        )
        draw_icon(
            renderer,
            self.marker_icon,
            Rect(int(marker.x) - 9, int(marker.y) - 9, 18, 18),
        )


class ResilienceCard(CardPanel):
    """The live Agroecological Score, as a bar and a grade.

    The same `scoring.compute_score` the evaluation screen runs, so the
    ribbon cannot flatter a garden the score sheet then marks down.

    Attributes:
        score: The last score computed, or None before the first one.
    """

    TITLE = "Resiliência do quintal"

    def __init__(self) -> None:
        """Build the card at `layout.RESILIENCE_CARD`."""
        card = layout.RESILIENCE_CARD
        super().__init__(Vector2(card.x, card.y), Vector2(card.width, card.height))
        self.add_child(
            Label(
                self.TITLE,
                Vector2(card.x + 40, card.y + 10),
                font_size=12,
                color=Sand.C200,
            )
        )
        self.bar = ProgressBar(
            Vector2(card.x + 40, card.y + 30),
            Vector2(card.width - 52, 10),
            value=0.0,
            fill_color=Verdant.COLONIAL_500,
        )
        self.add_child(self.bar)
        self.score: Score | None = None
        self._since_score = SCORE_INTERVAL

    def refresh(self, dt: float, compute: Callable[[], Score]) -> None:
        """Re-score the plot every `SCORE_INTERVAL` seconds.

        `refresh`, not `update` -- see `ResourceCard.refresh`.

        Args:
            dt: Seconds since the last frame.
            compute: Returns a fresh `Score`. Called on the tick only, so
                a caller can hand over `scoring.compute_score` directly
                without it running every frame.
        """
        self._since_score += dt
        if self._since_score < SCORE_INTERVAL:
            return
        self._since_score = 0.0
        self.score = compute()
        self.bar.set_value(self.score.total / 1000)

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card, the leaf, and the score with its grade."""
        super().render(renderer)
        draw_icon(renderer, "leaf", Rect(self.rect.x + 10, self.rect.y + 8, 24, 24))
        if self.score is None:
            return
        # The grade shares the bottom line with the total, right-aligned:
        # the longest one ("Guardian of the Cerrado") would otherwise run
        # into the title above it.
        grade = self.score.grade
        grade_w, _ = renderer.get_text_size(grade, 12)
        renderer.draw_text(
            grade,
            Vector2(self.rect.right - grade_w - 12, self.rect.y + 44),
            Sand.C200,
            12,
        )
        renderer.draw_text(
            f"{self.score.total}/1000",
            Vector2(self.rect.x + 40, self.rect.y + 44),
            MUTED_TEXT,
            10,
        )
