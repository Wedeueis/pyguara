# ruff: noqa: F811  - pytest fixtures are imported by name from the growth suite
"""The Cerrado's two seasons: the sky they bring and what they pay.

A twelve-day run is dry, wet, dry. The season re-weights the weather and
pays a premium on a crop harvested in its own -- nothing else. These tests
pin both, and that neither leaks into a system that should not know the
calendar exists.
"""

from __future__ import annotations

import pytest

from games.quintal_cerrado import seasons
from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.economy import sale_value
from games.quintal_cerrado.icons import ICONS
from games.quintal_cerrado.morning import report_lines
from games.quintal_cerrado.scenes import GardenScene
from games.quintal_cerrado.seasons import (
    DRY,
    IN_SEASON_PREMIUM,
    SEASON_LENGTH,
    SEASON_TABLE,
    WET,
    price_multiplier,
    season_for,
    turns_on,
)
from games.quintal_cerrado.species import SPECIES_TABLE, sellable_species
from games.quintal_cerrado.systems.day_resolver import DayReport
from games.quintal_cerrado.systems.weather_system import WeatherSystem
from games.quintal_cerrado.turn import SESSION_DAYS
from games.quintal_cerrado.weather import WEATHER_TABLE, roll_condition
from pyguara.common.random import RandomStream
from tests.test_quintal_cerrado_growth import (  # noqa: F401
    _plant_at,
    game_container,
    scene,
)


class TestTheCalendar:
    """Three spells over twelve days."""

    @pytest.mark.parametrize(
        ("day", "expected"),
        [(1, DRY), (4, DRY), (5, WET), (8, WET), (9, DRY), (12, DRY)],
    )
    def test_the_run_is_dry_wet_dry(self, day: int, expected: str) -> None:
        assert season_for(day).key == expected

    def test_every_day_of_the_session_has_a_season(self) -> None:
        assert all(season_for(day) is not None for day in range(1, SESSION_DAYS + 1))

    def test_a_day_past_the_end_stays_in_the_last_spell(self) -> None:
        """The evaluation runs on day 13; it must not fall off the calendar."""
        assert season_for(SESSION_DAYS + 1).key == season_for(SESSION_DAYS).key

    def test_a_day_before_the_start_does_not_wrap(self) -> None:
        assert season_for(0).key == DRY

    def test_the_season_turns_on_the_first_morning_of_a_spell(self) -> None:
        assert turns_on(SEASON_LENGTH + 1)
        assert turns_on(2 * SEASON_LENGTH + 1)

    def test_an_ordinary_morning_is_not_a_turn(self) -> None:
        assert not turns_on(2)
        assert not turns_on(SEASON_LENGTH)

    def test_the_first_morning_is_not_a_turn(self) -> None:
        """Day 1 is a season beginning, but there was no season before it."""
        assert not turns_on(1)

    def test_nothing_turns_after_the_session_ends(self) -> None:
        assert not turns_on(SESSION_DAYS + 1)


class TestTheSky:
    """Each season re-weights the same six conditions."""

    def _rolls(self, season: seasons.Season, count: int = 400) -> list[str]:
        rng = RandomStream(7)
        return [roll_condition(rng, season) for _ in range(count)]

    def test_the_dry_season_brings_no_rain(self) -> None:
        assert "rainy" not in self._rolls(SEASON_TABLE[DRY])

    def test_the_rains_bring_no_cold_snap(self) -> None:
        """The friagem is a dry-season front, not a wet-season one."""
        assert "cold_snap" not in self._rolls(SEASON_TABLE[WET])

    def test_the_rains_actually_rain_more_than_the_drought(self) -> None:
        wet = self._rolls(SEASON_TABLE[WET]).count("rainy")
        dry = self._rolls(SEASON_TABLE[DRY]).count("rainy")

        assert wet > dry == 0

    def test_a_season_only_ever_rolls_a_real_condition(self) -> None:
        for season in SEASON_TABLE.values():
            assert all(c in WEATHER_TABLE for c in self._rolls(season, 100))

    def test_no_season_leaves_nothing_to_roll(self) -> None:
        for season in SEASON_TABLE.values():
            assert len(set(self._rolls(season, 200))) > 1

    def test_without_a_season_the_plain_weights_still_apply(self) -> None:
        rng = RandomStream(7)
        rolls = [roll_condition(rng) for _ in range(400)]

        assert "rainy" in rolls and "cold_snap" in rolls


class TestTheForecastKnowsTheCalendar:
    """A roll is made for the day it lands on, not for today."""

    def test_the_forecast_crossing_into_the_rains_can_rain(self) -> None:
        """Rolled on day 4, the two-day forecast covers days 5 and 6 --
        both wet. A queue filled under today's dry season could not rain."""
        seen = set()
        for seed in range(40):
            system = WeatherSystem(rng=RandomStream(seed), start_day=SEASON_LENGTH - 1)
            system.advance_day(SEASON_LENGTH)
            seen.update(system.forecast)

        assert "rainy" in seen

    def test_the_dry_season_forecast_never_rains(self) -> None:
        seen = set()
        for seed in range(40):
            seen.update(WeatherSystem(rng=RandomStream(seed), start_day=1).forecast)

        assert "rainy" not in seen

    def test_a_night_still_advances_exactly_one_condition(self) -> None:
        system = WeatherSystem(rng=RandomStream(4))
        queued = system.forecast

        system.advance_day(2)

        assert system.state.condition_id == queued[0]
        assert system.forecast[0] == queued[1]


class TestTheMarket:
    """A crop harvested in its own season is worth more."""

    def test_in_season_pays_the_premium(self) -> None:
        assert price_multiplier(SEASON_TABLE[DRY], DRY) == IN_SEASON_PREMIUM

    def test_out_of_season_pays_the_ordinary_rate(self) -> None:
        assert price_multiplier(SEASON_TABLE[DRY], WET) == 1.0

    def test_a_crop_with_no_season_is_never_penalised(self) -> None:
        for season in SEASON_TABLE.values():
            assert price_multiplier(season, None) == 1.0

    def test_both_seasons_have_a_crop_of_their_own(self) -> None:
        """Otherwise one spell is dead time for the market."""
        grown = {s.season for s in sellable_species()}

        assert DRY in grown and WET in grown

    def test_a_baru_sells_higher_in_the_drought_than_in_the_rains(self) -> None:
        plant = PlantComponent(species_id="baru")

        dry = sale_value(plant, None, SEASON_TABLE[DRY])
        wet = sale_value(plant, None, SEASON_TABLE[WET])

        assert SPECIES_TABLE["baru"].season == DRY
        assert dry > wet

    def test_pricing_without_a_season_ignores_the_calendar(self) -> None:
        plant = PlantComponent(species_id="baru")

        assert sale_value(plant) == sale_value(plant, None, SEASON_TABLE[WET])

    def test_the_premium_is_worth_planning_for_but_not_decisive(self) -> None:
        """An out-of-season crop should still be worth growing: the
        calendar is a lever, not a lockout."""
        assert 1.1 < IN_SEASON_PREMIUM < 1.5


class TestTheGardenSeesIt:
    """End to end, through the scene."""

    def test_a_hand_harvest_is_paid_the_season_it_happens_in(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (2, 2), "baru", stage="harvestable")
        scene.turn.day = SEASON_LENGTH + 1  # the rains: baru is out of season
        before = scene.economy.credits

        scene._harvest((2, 2))
        out_of_season = scene.economy.credits - before

        _plant_at(scene, (2, 2), "baru", stage="harvestable")
        scene.turn.day = 1  # the drought: baru's own season
        before = scene.economy.credits

        scene._harvest((2, 2))

        assert scene.economy.credits - before > out_of_season

    def test_the_morning_names_a_season_that_turned(self, scene: GardenScene) -> None:
        scene.turn.day = SEASON_LENGTH

        report = scene.end_day()

        assert report.season_arrived == WET
        assert not report.quiet, "a season turning is always worth a line"

    def test_an_ordinary_morning_names_no_season(self, scene: GardenScene) -> None:
        report = scene.end_day()

        assert report.season_arrived == ""


class TestTheMorningLine:
    """What the report says the morning a season turns."""

    def test_the_line_names_the_season_and_what_it_brings(self) -> None:
        lines = report_lines(DayReport(day=SEASON_LENGTH, season_arrived=WET))

        assert lines[0].text.startswith(SEASON_TABLE[WET].display_name)
        assert SEASON_TABLE[WET].blurb in lines[0].text

    def test_it_leads_the_report(self) -> None:
        """Before the pests and the harvest: it is what tomorrow is for."""
        report = DayReport(day=SEASON_LENGTH, season_arrived=DRY, outbreak_started=True)

        assert report_lines(report)[0].icon_id == SEASON_TABLE[DRY].icon_id

    def test_an_ordinary_morning_gets_no_season_line(self) -> None:
        lines = report_lines(DayReport(day=2))

        assert all("Seca" not in line.text for line in lines)

    def test_every_blurb_fits_the_card_on_one_row(self) -> None:
        """The body draws a line as one row of text, and does not wrap."""
        for season in SEASON_TABLE.values():
            row = f"{season.display_name}. {season.blurb}"
            assert len(row) <= 60, row

    def test_every_season_icon_is_one_the_hud_can_draw(self) -> None:
        for season in SEASON_TABLE.values():
            assert season.icon_id in ICONS
