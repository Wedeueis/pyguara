# ruff: noqa: F811  (fixtures imported from the growth tests are used by name)
"""Weather: the forecasted cycle, and its effect on soil, pests and growth.

Reuses `tests/test_quintal_cerrado_growth.py`'s container and scene
fixtures.
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.scenes import GardenScene
from games.quintal_cerrado.systems.pest_system import PestSystem
from games.quintal_cerrado.systems.plant_growth_system import (
    COLD_SNAP_SHADE_COVER,
    PlantGrowthSystem,
)
from games.quintal_cerrado.systems.soil_system import SoilSystem
from games.quintal_cerrado.systems.weather_system import (
    CONDITION_DURATION,
    FORECAST_LENGTH,
    WeatherSystem,
)
from games.quintal_cerrado.weather import CALM_CONDITION_ID, WeatherState
from pyguara.common.random import RandomStream
from tests.test_quintal_cerrado_growth import (  # noqa: F401
    _nights,
    _plant_at,
    _plant_component,
    _resolve,
    game_container,
    scene,
)


class TestWeatherSystem:
    """The forecasted cycle, in isolation from soil/pests/growth."""

    def test_a_fresh_system_starts_calm(self) -> None:
        """Not rolled -- see the system's own module docstring for why an
        immediately-active random condition would have been the wrong call."""
        system = WeatherSystem()

        assert system.state.condition_id == CALM_CONDITION_ID
        assert system.state.growth_multiplier == 1.0
        assert system.state.moisture_gain_per_second == 0.0
        assert system.state.evaporation_multiplier == 1.0
        assert system.state.pest_spread_multiplier == 1.0
        assert not system.state.cold_snap

    def test_the_forecast_starts_at_the_configured_length(self) -> None:
        assert len(WeatherSystem().forecast) == FORECAST_LENGTH

    def test_a_short_tick_does_not_change_the_condition(self) -> None:
        system = WeatherSystem(rng=RandomStream(1))

        system.update(CONDITION_DURATION - 0.1)

        assert system.state.condition_id == CALM_CONDITION_ID

    def test_the_condition_advances_to_the_forecasts_head(self) -> None:
        system = WeatherSystem(rng=RandomStream(1))
        expected = system.forecast[0]

        system.update(CONDITION_DURATION)

        assert system.state.condition_id == expected
        assert len(system.forecast) == FORECAST_LENGTH  # refilled, not shrunk

    def test_a_seeded_rng_makes_a_reproducible_forecast(self) -> None:
        def forecast_for(seed: int) -> list[str]:
            return WeatherSystem(rng=RandomStream(seed)).forecast

        assert forecast_for(9) == forecast_for(9)

    def test_a_night_turns_the_scene_own_sky(self, scene: GardenScene) -> None:
        """The scene's own system, not a standalone one -- pins that
        `_build_resolver` wires `scene.weather` in, and that exactly one
        condition passes per night."""
        assert scene._resolver is not None
        weather_system = scene._resolver.weather
        expected_next = weather_system.forecast[0]

        _nights(scene)

        assert weather_system.state.condition_id == expected_next
        assert scene.weather.condition_id == expected_next


class TestWeatherEffects:
    """What a non-calm `WeatherState` does to the systems that read it."""

    def test_rain_adds_moisture_to_tilled_soil(self) -> None:
        grid = GardenGrid()
        grid.till((0, 0))
        grid.soil_at((0, 0)).moisture = 0.1
        weather = WeatherState(moisture_gain_per_second=0.5)

        SoilSystem(grid, weather).update(1.0)

        assert grid.soil_at((0, 0)).moisture > 0.1

    def test_rain_does_not_wet_untilled_ground(self) -> None:
        grid = GardenGrid()  # (0, 0) stays raw dirt
        grid.soil_at((0, 0)).moisture = 0.0  # already at the evaporation floor
        weather = WeatherState(moisture_gain_per_second=0.5)

        SoilSystem(grid, weather).update(1.0)

        assert grid.soil_at((0, 0)).moisture == 0.0

    def test_wind_speeds_up_evaporation(self) -> None:
        calm_grid = GardenGrid()
        calm_grid.till((0, 0))
        calm_grid.soil_at((0, 0)).moisture = 1.0
        SoilSystem(calm_grid, WeatherState(evaporation_multiplier=1.0)).update(5.0)

        windy_grid = GardenGrid()
        windy_grid.till((0, 0))
        windy_grid.soil_at((0, 0)).moisture = 1.0
        SoilSystem(windy_grid, WeatherState(evaporation_multiplier=3.0)).update(5.0)

        assert windy_grid.soil_at((0, 0)).moisture < calm_grid.soil_at((0, 0)).moisture

    def test_wind_speeds_up_pest_spread(self, scene: GardenScene) -> None:
        _plant_at(scene, (5, 5), "guandu", stage="mature")
        _plant_at(scene, (5, 6), "guandu", stage="mature")

        scene.grid.soil_at((5, 5)).pest_pressure = 0.8
        PestSystem(
            scene.entity_manager, scene.grid, WeatherState(pest_spread_multiplier=1.0)
        ).update(1.0)
        calm_pressure = scene.grid.soil_at((5, 6)).pest_pressure

        scene.grid.soil_at((5, 5)).pest_pressure = 0.8
        scene.grid.soil_at((5, 6)).pest_pressure = 0.0
        PestSystem(
            scene.entity_manager, scene.grid, WeatherState(pest_spread_multiplier=3.0)
        ).update(1.0)
        windy_pressure = scene.grid.soil_at((5, 6)).pest_pressure

        assert windy_pressure > calm_pressure

    def test_a_cold_snap_stalls_growth_on_an_uncovered_cell(
        self, scene: GardenScene
    ) -> None:
        cell = (2, 2)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.water(cell)
        scene.grid.soil_at(cell).shade_level = 0.0

        PlantGrowthSystem(
            scene.entity_manager, scene.grid, WeatherState(cold_snap=True)
        ).update(5.0)

        assert _plant_component(scene, cell).growth_progress == 0.0

    def test_a_cold_snap_spares_a_canopy_covered_cell(self, scene: GardenScene) -> None:
        """ "Cover the canopy gap" -- the PRD's own phrase for this trade-off."""
        cell = (2, 2)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.water(cell)
        scene.grid.soil_at(cell).shade_level = COLD_SNAP_SHADE_COVER

        PlantGrowthSystem(
            scene.entity_manager, scene.grid, WeatherState(cold_snap=True)
        ).update(5.0)

        assert _plant_component(scene, cell).growth_progress > 0.0

    def test_a_favourable_condition_boosts_growth(self, scene: GardenScene) -> None:
        cell = (2, 2)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.water(cell)

        PlantGrowthSystem(
            scene.entity_manager, scene.grid, WeatherState(growth_multiplier=2.0)
        ).update(1.0)
        boosted = _plant_component(scene, cell).growth_progress

        plant = scene.entity_manager.get_entity(scene.grid.plant_at[cell])
        plant.get_component(PlantComponent).growth_progress = 0.0
        PlantGrowthSystem(
            scene.entity_manager, scene.grid, WeatherState(growth_multiplier=1.0)
        ).update(1.0)
        baseline = _plant_component(scene, cell).growth_progress

        assert boosted == baseline * 2.0
