# ruff: noqa: F811  - pytest fixtures are imported by name from the growth suite
"""The turn loop: stamina spent on actions, and a night that resolves the day.

The garden used to simulate every frame, which punished thinking. Now
nothing moves until the player sleeps, and what a day *is* is the stamina
in it.
"""

from __future__ import annotations

import pytest

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.evaluation import EvaluationScene
from games.quintal_cerrado.scenes import GardenScene, slot_status
from games.quintal_cerrado.systems.day_resolver import DayReport
from games.quintal_cerrado.turn import (
    MAX_STAMINA,
    SESSION_DAYS,
    TILL_COST,
    DayCycle,
    action_cost,
)
from pyguara.ai.ai_system import AISystem
from pyguara.di.container import DIContainer
from pyguara.scene.manager import SceneManager
from tests.test_quintal_cerrado_growth import (  # noqa: F401
    _force_stage,
    _nights,
    _plant_at,
    _resolve,
    game_container,
    scene,
)


def _plant(scene: GardenScene, cell: tuple[int, int]) -> PlantComponent:
    """The `PlantComponent` growing on `cell`."""
    entity = scene.entity_manager.get_entity(scene.grid.plant_at[cell])
    return entity.get_component(PlantComponent)


class TestActionCosts:
    """What the table charges, and what it leaves free."""

    @pytest.mark.parametrize(
        ("tool", "expected"),
        [("till", 2), ("water", 1), ("harvest", 1), ("compost", 2), ("spray", 3)],
    )
    def test_each_tool_has_its_price(self, tool: str, expected: int) -> None:
        assert action_cost(tool) == expected

    def test_every_species_costs_the_same_to_sow(self) -> None:
        assert action_cost("plant_guandu") == action_cost("plant_pequi") == 1

    def test_building_is_free_because_the_store_already_charged(self) -> None:
        assert action_cost("build_solar_panel") == 0

    def test_an_unknown_tool_is_free_rather_than_unusable(self) -> None:
        assert action_cost("teleport") == 0


class TestTheDayCycle:
    """The pool itself."""

    def test_spending_takes_from_the_pool(self) -> None:
        turn = DayCycle()

        assert turn.spend(3)

        assert turn.stamina == MAX_STAMINA - 3

    def test_it_refuses_what_it_cannot_pay_and_keeps_the_rest(self) -> None:
        turn = DayCycle(stamina=2)

        assert not turn.spend(3)

        assert turn.stamina == 2

    def test_sleeping_starts_a_new_day_with_a_full_pool(self) -> None:
        turn = DayCycle(day=3, stamina=1)

        turn.sleep()

        assert turn.day == 4
        assert turn.stamina == turn.max_stamina

    def test_leftover_stamina_does_not_carry_over(self) -> None:
        """Ending a day early is a choice, not banked energy."""
        turn = DayCycle(stamina=MAX_STAMINA)

        turn.sleep()

        assert turn.stamina == MAX_STAMINA

    def test_it_knows_the_last_day(self) -> None:
        assert not DayCycle(day=SESSION_DAYS - 1).is_final_day
        assert DayCycle(day=SESSION_DAYS).is_final_day


class TestSpendingInTheGarden:
    """Stamina is charged where the click lands, and only when it works."""

    def test_tilling_spends_its_cost(self, scene: GardenScene) -> None:
        scene._set_active_tool("till")

        scene._on_cell_clicked((3, 3))

        assert scene.turn.stamina == MAX_STAMINA - TILL_COST
        assert scene.grid.soil_at((3, 3)).soil_type == "tilled_dirt"

    def test_a_refused_action_costs_nothing(self, scene: GardenScene) -> None:
        """Planting on raw dirt does nothing, so it must not take the day."""
        scene._set_active_tool("plant_guandu")

        scene._on_cell_clicked((3, 3))

        assert scene.turn.stamina == MAX_STAMINA
        assert (3, 3) not in scene.grid.plant_at

    def test_tilling_worked_ground_again_costs_nothing(
        self, scene: GardenScene
    ) -> None:
        scene._set_active_tool("till")
        scene._on_cell_clicked((3, 3))
        spent = scene.turn.stamina

        scene._on_cell_clicked((3, 3))

        assert scene.turn.stamina == spent

    def test_an_exhausted_day_refuses_the_action_entirely(
        self, scene: GardenScene
    ) -> None:
        scene.turn.stamina = 1
        scene._set_active_tool("till")

        scene._on_cell_clicked((3, 3))

        assert scene.turn.stamina == 1
        assert scene.grid.soil_at((3, 3)).soil_type == "raw_dirt"

    def test_the_dock_dims_a_tool_the_day_cannot_afford(
        self, scene: GardenScene
    ) -> None:
        scene.economy.credits = 9999
        assert slot_status("spray", scene.economy, scene.turn)[1]

        scene.turn.stamina = 1

        assert not slot_status("spray", scene.economy, scene.turn)[1]
        assert slot_status("water", scene.economy, scene.turn)[1], "still affordable"

    def test_the_cursor_blocks_what_the_day_cannot_afford(
        self, scene: GardenScene
    ) -> None:
        scene._set_active_tool("till")
        assert scene._tool_allows((4, 4))

        scene.turn.stamina = 1

        assert not scene._tool_allows((4, 4))


class TestTheNight:
    """Sleeping is the only thing that moves the simulation."""

    def test_nothing_grows_while_the_player_thinks(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "guandu", stage="seedling")
        scene.grid.water((2, 2))

        for _ in range(600):
            scene.update(1 / 60)

        assert _plant(scene, (2, 2)).growth_progress == 0.0
        assert _plant(scene, (2, 2)).growth_stage == "seedling"

    def test_a_night_grows_what_is_watered(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "guandu", stage="seedling")
        scene.grid.water((2, 2))

        _nights(scene)

        assert _plant(scene, (2, 2)).growth_stage != "seedling"

    def test_a_night_dries_the_soil(self, scene: GardenScene) -> None:
        scene.grid.till((1, 1))
        scene.grid.water((1, 1))
        wet = scene.grid.soil_at((1, 1)).moisture

        _nights(scene)

        assert scene.grid.soil_at((1, 1)).moisture < wet

    def test_a_night_reports_what_it_did(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "guandu", stage="mature")
        scene.grid.water((2, 2))

        report = scene.end_day()

        assert isinstance(report, DayReport)
        assert report.day == 1
        assert report.weather_id
        assert report.ripened or report.stages_grown

    def test_a_quiet_night_says_so(self, scene: GardenScene) -> None:
        report = scene.end_day()

        assert report.quiet

    def test_sleeping_advances_the_day_and_refills_the_pool(
        self, scene: GardenScene
    ) -> None:
        scene.turn.stamina = 2

        scene.end_day()

        assert scene.turn.day == 2
        assert scene.turn.stamina == MAX_STAMINA

    def test_the_sleep_slot_ends_the_day(self, scene: GardenScene) -> None:
        assert scene._sleep_button is not None

        scene._sleep_button.on_click(scene._sleep_button)

        assert scene.turn.day == 2

    def test_no_system_is_registered_to_tick(self, scene: GardenScene) -> None:
        """The resolver owns them, and the engine's AISystem is dropped so
        the plant and garden FSMs cannot run on real seconds."""
        assert scene.system_manager.get_system(AISystem) is None
        assert scene._resolver is not None


class TestASessionEnds:
    """Twelve days, then the score."""

    def test_the_evaluation_waits_for_the_last_night(
        self, scene: GardenScene, game_container: DIContainer
    ) -> None:
        manager = game_container.get(SceneManager)
        scene.turn = DayCycle(day=SESSION_DAYS - 1, stamina=1)

        scene.end_day()

        assert not isinstance(manager.current_scene, EvaluationScene)
