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

from collections.abc import Callable

from games.quintal_cerrado import layout
from games.quintal_cerrado.clock import format_day
from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    GardenConditions,
    PlayerEconomy,
)
from games.quintal_cerrado.hud_widgets import MUTED_TEXT, CardPanel, draw_badge
from games.quintal_cerrado.icons import draw_icon
from games.quintal_cerrado.scoring import Score
from games.quintal_cerrado.turn import MAX_STAMINA, DayCycle
from games.quintal_cerrado.weather import WEATHER_TABLE
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.text import Label
from pyguara.ui.design_system.tokens import Sand, Verdant, Wood

ALERT = Color(214, 96, 80)
"""The pest chip's colour while an outbreak is live."""

FORECAST_LENGTH = 2
"""How many days ahead the card has room for."""

PIP_SIZE = 7
PIP_GAP = 3
PIP_FULL = Sand.C300
PIP_SPENT = Wood.C700.lerp(Color(35, 28, 38), 0.4)

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
        stamina: Energy left today.
        max_stamina: What a night restores.
    """

    def __init__(self) -> None:
        """Build the card at `layout.RESOURCE_CARD`."""
        card = layout.RESOURCE_CARD
        super().__init__(Vector2(card.x, card.y), Vector2(card.width, card.height))
        self.credits_label = Label(
            "0", Vector2(card.x + 48, card.y + 4), font_size=23, color=Sand.C200
        )
        self.status_label = Label("", Vector2(card.x + 46, card.y + 32), font_size=11)
        self.add_child(self.credits_label)
        self.add_child(self.status_label)
        self.power = (0, 0)
        self.generic_seeds = 0
        self.alarmed = False
        self.stamina = MAX_STAMINA
        self.max_stamina = MAX_STAMINA

    def refresh(
        self,
        economy: PlayerEconomy,
        conditions: GardenConditions,
        power: tuple[int, int],
        turn: DayCycle | None = None,
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
            turn: The day's stamina, or None to leave the pips alone.
        """
        self.credits_label.set_text(str(int(economy.credits)))
        self.status_label.set_text(_STATUS_TEXT.get(conditions.phase, conditions.phase))
        self.alarmed = conditions.phase == "outbreak"
        self.status_label.set_color(ALERT if self.alarmed else None)
        self.power = power
        self.generic_seeds = economy.inventory.get(GENERIC_SEED_KEY, 0)
        if turn is not None:
            self.stamina = turn.stamina
            self.max_stamina = turn.max_stamina

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card, the pouch, the seed glyph and the two chips."""
        super().render(renderer)
        draw_icon(
            renderer, "seed_pouch", Rect(self.rect.x + 8, self.rect.y + 10, 34, 34)
        )

        # The seed glyph trails the number, so it moves with its width.
        number_w, _ = renderer.get_text_size(self.credits_label.text, 23)
        draw_icon(
            renderer,
            "seed",
            Rect(self.credits_label.rect.x + number_w + 6, self.rect.y + 10, 15, 15),
        )

        used, capacity = self.power
        chip_x = self.rect.x + 172
        draw_badge(
            renderer,
            f"{used}/{capacity}" if capacity else "sem sol",
            Vector2(chip_x, self.rect.y + 8),
            icon_id="sun",
            color=MUTED_TEXT if capacity else MUTED_TEXT.lerp(Color(35, 28, 38), 0.3),
        )
        draw_badge(
            renderer,
            f"x{self.generic_seeds}",
            Vector2(chip_x, self.rect.y + 30),
            icon_id="plant_generic",
        )
        self._draw_stamina(renderer)

    def _draw_stamina(self, renderer: UIRenderer) -> None:
        """One pip per point of energy, spent ones dimmed.

        Pips rather than a bar: stamina is discrete, and what the player
        needs to read is "how many more things can I do", not a fraction.
        """
        x = self.rect.x + 12
        y = self.rect.bottom - 12
        for index in range(self.max_stamina):
            renderer.draw_rect(
                Rect(x + index * (PIP_SIZE + PIP_GAP), y, PIP_SIZE, PIP_SIZE),
                PIP_FULL if index < self.stamina else PIP_SPENT,
                border_radius=2,
            )


class WeatherCard(CardPanel):
    """Today's sky, which day it is, and what the next days bring.

    A card of its own rather than a line on the resource card: the
    forecast is glanced at *before* an action ("rain tomorrow, skip the
    watering can"), not read alongside the credits.

    Attributes:
        now_label: The current condition's name.
        day_label: `"Dia 3 / 12"`.
        condition_id: What the sky is doing today.
        forecast: The conditions of the next days, nearest first.
    """

    def __init__(self) -> None:
        """Build the card at `layout.WEATHER_CARD`."""
        card = layout.WEATHER_CARD
        super().__init__(Vector2(card.x, card.y), Vector2(card.width, card.height))
        self.now_label = Label(
            "", Vector2(card.x + 50, card.y + 10), font_size=15, color=Sand.C200
        )
        self.day_label = Label("", Vector2(card.x + 50, card.y + 32), font_size=12)
        self.add_child(self.now_label)
        self.add_child(self.day_label)
        self.condition_id = ""
        self.forecast: list[str] = []

    def refresh(self, condition_id: str, forecast: list[str], day: int) -> None:
        """Take the sky and the calendar.

        `refresh`, not `update` -- see `ResourceCard.refresh`.

        Args:
            condition_id: `WeatherSystem.state.condition_id`.
            forecast: `WeatherSystem.forecast`, nearest first.
            day: The current day, 1-based.
        """
        self.condition_id = condition_id
        condition = WEATHER_TABLE.get(condition_id)
        self.now_label.set_text(condition.display_name if condition else "?")
        self.day_label.set_text(format_day(day))
        self.forecast = [c for c in forecast if c in WEATHER_TABLE][:FORECAST_LENGTH]

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card, today's condition, and the days to come."""
        super().render(renderer)
        draw_icon(
            renderer, self.condition_id, Rect(self.rect.x + 8, self.rect.y + 12, 36, 36)
        )
        renderer.draw_text(
            "a seguir", Vector2(self.rect.x + 164, self.rect.y + 8), MUTED_TEXT, 10
        )
        for index, condition_id in enumerate(self.forecast):
            x = self.rect.x + 164 + index * 46
            draw_icon(renderer, condition_id, Rect(x, self.rect.y + 22, 22, 22))
            renderer.draw_text(
                f"d{index + 1}", Vector2(x + 26, self.rect.y + 28), MUTED_TEXT, 10
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
