# ruff: noqa: F811  - pytest fixtures are imported by name from the growth suite
"""A comfortable plant resists pests; a stressed one does not.

Pests used to land on whatever was nearest, which made an outbreak
something done *to* the player. Here the garden can be arranged to resist
one -- and calcium is worth most to a plant already doing well.
"""

from __future__ import annotations

import pytest

from games.quintal_cerrado import stress
from games.quintal_cerrado.components import SoilCell
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.weather import WEATHER_TABLE, WeatherState

GUANDU = SPECIES_TABLE["guandu"]
CAGAITA = SPECIES_TABLE["cagaita"]
BARU = SPECIES_TABLE["baru"]

COLD = WeatherState(cold_snap=True)


def _ideal(**overrides: float) -> SoilCell:
    """A cell a plant is perfectly happy in."""
    soil = SoilCell(
        soil_type="tilled_dirt",
        moisture=0.6,
        nitrogen=0.6,
        phosphorus=0.6,
        potassium=0.6,
        calcium=0.6,
        shade_level=0.2,
    )
    for key, value in overrides.items():
        setattr(soil, key, value)
    return soil


class TestTheBand:
    """Too much is as bad as too little."""

    @pytest.mark.parametrize("value", [0.4, 0.6, 0.85])
    def test_inside_the_band_is_perfectly_comfortable(self, value: float) -> None:
        assert stress.MOISTURE.comfort(value) == 1.0

    def test_comfort_falls_off_on_both_sides(self) -> None:
        assert stress.MOISTURE.comfort(0.2) < 1.0
        assert stress.MOISTURE.comfort(1.0) < 1.0

    def test_it_never_goes_negative(self) -> None:
        assert stress.MOISTURE.comfort(-5.0) == 0.0
        assert stress.MOISTURE.comfort(5.0) == 0.0


class TestWhatStressesAPlant:
    """Every factor, and the worst one winning."""

    def test_ideal_conditions_are_comfortable(self) -> None:
        assert stress.comfort(_ideal(), GUANDU).overall == 1.0

    @pytest.mark.parametrize(
        ("field", "value", "worst"),
        [
            ("moisture", 0.1, "water"),
            ("moisture", 1.0, "water"),
            ("nitrogen", 0.05, "food"),
            ("nitrogen", 1.0, "food"),
        ],
    )
    def test_any_factor_out_of_band_shows_up(
        self, field: str, value: float, worst: str
    ) -> None:
        result = stress.comfort(_ideal(**{field: value}), GUANDU)

        assert result.overall < 1.0
        assert result.worst == worst

    def test_a_plant_is_only_as_comfortable_as_its_worst_condition(self) -> None:
        """Liebig's law: feeding a drowning plant does not help it."""
        drowning = stress.comfort(_ideal(moisture=1.0, nitrogen=0.6), GUANDU)

        assert drowning.overall == drowning.moisture
        assert drowning.nutrition == 1.0, "well fed, and it does not matter"

    def test_each_layer_wants_its_own_light(self) -> None:
        open_ground = _ideal(shade_level=0.0)
        deep_shade = _ideal(shade_level=0.9)

        assert stress.comfort(open_ground, BARU).light == 1.0
        assert stress.comfort(deep_shade, BARU).light < 1.0
        assert (
            stress.comfort(deep_shade, CAGAITA).light
            > stress.comfort(deep_shade, BARU).light
        )

    def test_an_understory_plant_in_the_open_copes(self) -> None:
        """Everything starts in full sun; a band that bottomed out there
        would make the opening of every session a pest magnet."""
        assert stress.comfort(_ideal(shade_level=0.0), CAGAITA).light > 0.5

    def test_a_cold_snap_is_stressful_unless_sheltered(self) -> None:
        exposed = stress.comfort(_ideal(shade_level=0.0, potassium=0.2), GUANDU, COLD)
        covered = stress.comfort(_ideal(shade_level=0.9, potassium=0.2), GUANDU, COLD)
        fed = stress.comfort(_ideal(shade_level=0.0, potassium=1.0), GUANDU, COLD)

        assert exposed.warmth < 1.0
        assert covered.warmth > exposed.warmth
        assert fed.warmth > exposed.warmth, "potassium answers the cold too"
        assert covered.warmth > fed.warmth, "but a canopy answers it better"

    def test_calm_weather_is_never_cold(self) -> None:
        calm = WeatherState(**{"condition_id": WEATHER_TABLE["calm"].condition_id})

        assert stress.comfort(_ideal(), GUANDU, calm).warmth == 1.0


class TestResistingPests:
    """What comfort buys, and what calcium multiplies."""

    def test_a_comfortable_plant_turns_most_of_it_away(self) -> None:
        thriving = stress.pest_susceptibility(_ideal(), GUANDU)
        parched = stress.pest_susceptibility(_ideal(moisture=0.1), GUANDU)

        assert thriving < parched

    def test_calcium_is_worth_more_to_a_healthy_plant(self) -> None:
        """The multiplier, not a shield: it cannot rescue neglect."""
        healthy_gain = stress.pest_resistance(
            _ideal(calcium=1.0), GUANDU
        ) - stress.pest_resistance(_ideal(calcium=0.0), GUANDU)
        stressed_gain = stress.pest_resistance(
            _ideal(calcium=1.0, moisture=0.12), GUANDU
        ) - stress.pest_resistance(_ideal(calcium=0.0, moisture=0.12), GUANDU)

        assert healthy_gain > stressed_gain > 0.0

    def test_forcing_nitrogen_past_the_band_invites_pests(self) -> None:
        """The cost of the obvious lever: soft, lush growth."""
        fed = stress.pest_susceptibility(_ideal(nitrogen=0.6), GUANDU)
        forced = stress.pest_susceptibility(_ideal(nitrogen=1.0), GUANDU)

        assert forced > fed

    def test_some_pressure_always_lands(self) -> None:
        """A garden is defensible, not immune."""
        best = stress.pest_susceptibility(_ideal(calcium=1.0), GUANDU)

        assert best >= stress.MIN_SUSCEPTIBILITY

    def test_a_bare_cell_reads_as_middling_rather_than_raising(self) -> None:
        assert 0.0 < stress.pest_susceptibility(SoilCell()) <= 1.0


class TestWhatThePlayerIsTold:
    """One word for what is wrong -- the thing most worth acting on."""

    def test_a_happy_plant_says_so(self) -> None:
        assert stress.describe(_ideal(), GUANDU) == stress.THRIVING

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({"moisture": 0.1}, "thirsty"),
            ({"moisture": 1.0}, "waterlogged"),
            ({"nitrogen": 0.08, "phosphorus": 0.08}, "hungry"),
            ({"nitrogen": 1.0, "phosphorus": 1.0}, "forced"),
        ],
    )
    def test_it_names_both_sides_of_a_band(
        self, overrides: dict[str, float], expected: str
    ) -> None:
        """Too much has its own word: a forced plant is not a hungry one."""
        assert stress.describe(_ideal(**overrides), GUANDU) == expected

    def test_light_is_named_for_the_plant_that_wants_it(self) -> None:
        assert stress.describe(_ideal(shade_level=1.0), BARU) == "wants sun"

    def test_a_cold_snap_is_named(self) -> None:
        exposed = _ideal(shade_level=0.0, potassium=0.2)

        assert stress.describe(exposed, GUANDU, COLD) == "cold"
