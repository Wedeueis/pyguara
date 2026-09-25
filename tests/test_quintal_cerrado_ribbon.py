"""The top ribbon shows real state: credits, the sky, and the live score."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    GardenConditions,
    PlayerEconomy,
)
from games.quintal_cerrado.ribbon import (
    ALERT,
    SCORE_INTERVAL,
    ResilienceCard,
    ResourceCard,
    WeatherCard,
)
from games.quintal_cerrado.scoring import Score
from games.quintal_cerrado.seasons import SEASON_LENGTH
from games.quintal_cerrado.systems.weather_system import WeatherSystem
from games.quintal_cerrado.turn import SESSION_DAYS
from games.quintal_cerrado.weather import WEATHER_TABLE
from pyguara.common.random import RandomStream
from pyguara.graphics.protocols import UIRenderer


def _renderer() -> Any:
    renderer = MagicMock(spec=UIRenderer)
    renderer.get_text_size.return_value = (20, 12)
    return renderer


def _score(total: int = 600, grade: str = "B") -> Score:
    return Score(0.5, 0.5, 0.5, 0.5, total, grade)


class TestResourceCard:
    """Sementes, power, generic seed, and the pest status."""

    def test_it_shows_the_credits_power_and_generic_stock(self) -> None:
        card = ResourceCard()
        economy = PlayerEconomy(credits=137)
        economy.inventory[GENERIC_SEED_KEY] = 4

        card.refresh(economy, GardenConditions(), (2, 3))

        assert card.credits_label.text == "137"
        assert card.power == (2, 3)
        assert card.generic_seeds == 4

    def test_an_outbreak_turns_the_status_line_red(self) -> None:
        card = ResourceCard()
        conditions = GardenConditions()

        conditions.phase = "stable"
        card.refresh(PlayerEconomy(), conditions, (0, 0))
        assert not card.alarmed
        assert card.status_label.custom_color is None

        conditions.phase = "outbreak"
        card.refresh(PlayerEconomy(), conditions, (0, 0))
        assert card.alarmed
        assert "OUTBREAK" in card.status_label.text
        assert card.status_label.custom_color == ALERT

    def test_it_draws_without_a_renderer_complaining(self) -> None:
        card = ResourceCard()
        card.refresh(PlayerEconomy(credits=5), GardenConditions(), (0, 0))
        renderer = _renderer()

        card.render(renderer)

        assert renderer.draw_rect.called


class TestWeatherCard:
    """Today's condition, which day it is, and the days to come."""

    def test_it_names_the_condition_and_keeps_the_forecast(self) -> None:
        card = WeatherCard()

        card.refresh("rainy", ["cold_snap", "clear", "windy"], day=3)

        assert card.now_label.text == WEATHER_TABLE["rainy"].display_name
        assert card.forecast == ["cold_snap", "clear"], "two days fit on the card"

    def test_it_shows_the_day_and_the_season(self) -> None:
        card = WeatherCard()

        card.refresh("calm", [], day=3)

        assert card.day_label.text == f"Dia 3 / {SESSION_DAYS} · Seca"

    def test_the_season_on_the_card_turns_with_the_calendar(self) -> None:
        card = WeatherCard()

        card.refresh("calm", [], day=SEASON_LENGTH + 1)

        assert card.day_label.text.endswith("Águas")

    def test_an_unknown_condition_does_not_raise(self) -> None:
        card = WeatherCard()

        card.refresh("no_such_weather", ["also_not_real"], day=1)

        assert card.now_label.text == "?"
        assert card.forecast == []

    def test_it_draws_today_and_the_forecast(self) -> None:
        card = WeatherCard()
        card.refresh("rainy", ["clear", "windy"], day=2)
        renderer = _renderer()

        card.render(renderer)

        assert renderer.draw_rect.called
        drawn = [call.args[0] for call in renderer.draw_text.call_args_list]
        assert "a seguir" in drawn
        assert "d1" in drawn and "d2" in drawn


class TestTheWeatherTurnsOncePerDay:
    """One condition a day: nothing moves mid-day, so nothing may change."""

    def test_a_night_advances_exactly_one_condition(self) -> None:
        system = WeatherSystem(rng=RandomStream(4))
        queued = system.forecast

        system.advance_day(2)

        assert system.state.condition_id == queued[0]
        assert system.forecast[0] == queued[1]

    def test_a_saved_sky_is_restored_rather_than_rerolled(self) -> None:
        """The forecast is something the player plans around -- reloading
        must not quietly deal a different one."""
        system = WeatherSystem(rng=RandomStream(4))

        system.restore("cold_snap", ["rainy", "clear"])

        assert system.state.condition_id == "cold_snap"
        assert system.state.cold_snap
        assert system.forecast == ["rainy", "clear"]


class TestResilienceCard:
    """The live score, throttled, and never invented."""

    def test_it_fills_the_bar_from_the_score_out_of_a_thousand(self) -> None:
        card = ResilienceCard()

        card.refresh(SCORE_INTERVAL, lambda: _score(total=750, grade="A"))

        assert card.score is not None
        assert card.score.grade == "A"
        assert card.bar.value == pytest.approx(0.75)

    def test_it_scores_at_most_once_an_interval(self) -> None:
        card = ResilienceCard()
        calls = 0

        def compute() -> Score:
            nonlocal calls
            calls += 1
            return _score()

        card.refresh(SCORE_INTERVAL, compute)
        assert calls == 1

        for _ in range(29):  # 29/60s, just short of the interval
            card.refresh(1 / 60, compute)
        assert calls == 1, "a frame is not a scoring tick"

        card.refresh(SCORE_INTERVAL, compute)
        assert calls == 2

    def test_no_score_is_drawn_before_the_first_one_is_computed(self) -> None:
        """The title draws; a grade and a total do not, having no value yet."""
        card = ResilienceCard()
        renderer = _renderer()

        card.render(renderer)

        drawn = [call.args[0] for call in renderer.draw_text.call_args_list]
        assert drawn == [ResilienceCard.TITLE]

        card.refresh(SCORE_INTERVAL, lambda: _score(total=480, grade="C"))
        renderer.reset_mock()
        renderer.get_text_size.return_value = (20, 12)
        card.render(renderer)

        drawn = [call.args[0] for call in renderer.draw_text.call_args_list]
        assert "C" in drawn and "480/1000" in drawn
