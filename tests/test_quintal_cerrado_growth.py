"""Plant growth, shade, pests, treatments and the economy, headless.

Drives `GardenScene.system_manager.update(dt)` directly -- the same call
`SceneManager.fixed_update()` makes automatically for every active scene
-- rather than a full `Application.run()` loop, so a stage transition
that should take a few seconds of simulated ticks stays a fast test.

No real window: builds the same minimal, mocked container
`tests/test_quintal_cerrado_screens.py` uses, rather than
`bootstrap.configure_game_container()`, which opens a real `PygameWindow`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado import garden_states, treatments
from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    PlantComponent,
    specific_seed_key,
)
from games.quintal_cerrado.economy import (
    COMPOST_COST,
    OVERRIPE_WEED_SEED_BONUS,
    SPRAY_COST,
    sale_value,
)
from games.quintal_cerrado.events import OutbreakResolvedEvent, OutbreakStartedEvent
from games.quintal_cerrado.persistence_schema import SCHEMA_VERSION
from games.quintal_cerrado.scenes import GardenScene
from games.quintal_cerrado.soil_health_effect import SoilHealthEffect
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.systems import weed_spread_system as weed_module
from games.quintal_cerrado.systems.weed_spread_system import (
    PROPAGATION_INTERVAL,
    WeedSpreadSystem,
)
from pyguara.ai.components import AIComponent
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.manager import AudioManager
from pyguara.common.random import RandomStream
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import MigrationManager
from pyguara.persistence.storage import FileStorageBackend
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager

SCREEN = (960, 640)
FIXED_DT = 1 / 60


@pytest.fixture
def game_container(tmp_path: Path) -> DIContainer:
    """Enough of the game's container for a scene to build itself."""
    dispatcher = EventDispatcher()
    ui_manager = UIManager(dispatcher)
    ui_manager.set_screen_size(*SCREEN)

    container = DIContainer()
    container.register_instance(DIContainer, container)
    container.register_instance(EventDispatcher, dispatcher)
    container.register_instance(UIManager, ui_manager)
    scene_manager = SceneManager()
    container.register_instance(SceneManager, scene_manager)
    container.register_instance(ResourceManager, ResourceManager())
    container.register_instance(ComponentRegistry, get_component_registry())
    container.register_instance(PrefabCache, PrefabCache())
    container.register_instance(IRenderer, MagicMock(spec=IRenderer))  # type: ignore[type-abstract]
    container.register_instance(UIRenderer, MagicMock(spec=UIRenderer))  # type: ignore[type-abstract]
    container.register_instance(IAudioSystem, MagicMock(spec=IAudioSystem))  # type: ignore[type-abstract]
    container.register_singleton(AudioManager, AudioManager)
    # GPU-owning effects: see the identical comment in
    # test_quintal_cerrado_screens.py's `game_container` fixture.
    container.register_instance(StormEffect, MagicMock(spec=StormEffect))
    container.register_instance(VignetteEffect, MagicMock(spec=VignetteEffect))
    container.register_instance(SoilHealthEffect, MagicMock(spec=SoilHealthEffect))
    input_manager = InputManager(dispatcher, MagicMock(spec=IInputBackend))
    container.register_instance(InputManager, input_manager)
    # A real store in a temp directory: the garden saves on exit, and a test
    # must never write into the repository's own `saves/`.
    container.register_instance(
        PersistenceManager,
        PersistenceManager(
            FileStorageBackend(base_path=str(tmp_path / "saves")),
            MigrationManager(current_version=SCHEMA_VERSION),
        ),
    )
    scene_manager.set_container(container)
    return container


@pytest.fixture
def scene(game_container: DIContainer) -> GardenScene:
    garden = GardenScene(game_container.get(EventDispatcher))
    game_container.get(SceneManager).register(garden)
    game_container.get(SceneManager).switch_to("GardenScene")
    return garden


def _tick(scene: GardenScene, seconds: float) -> None:
    for _ in range(round(seconds / FIXED_DT)):
        scene.system_manager.update(FIXED_DT)
        scene.entity_manager.flush_pending_removals()


def _plant_component(scene: GardenScene, cell: tuple[int, int]) -> PlantComponent:
    entity = scene.entity_manager.get_entity(scene.grid.plant_at[cell])
    return entity.get_component(PlantComponent)


class TestGrowthProgression:
    def test_a_solo_plant_advances_through_every_stage(
        self, scene: GardenScene
    ) -> None:
        cell = (0, 0)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.water(cell)

        # 12s: guandu (stage_seconds=3.0) reaches harvestable in ~9s and
        # would not go "overripe" for another ~4.5s after that -- comfortable
        # margin to see every growth stage without also seeing the ripening
        # one, which `TestOverripening` covers on its own.
        seen_stages = set()
        for _ in range(round(12 / FIXED_DT)):
            scene.system_manager.update(FIXED_DT)
            scene.entity_manager.flush_pending_removals()
            seen_stages.add(_plant_component(scene, cell).growth_stage)

        assert seen_stages == {"seedling", "growing", "mature", "harvestable"}

    def test_a_solo_plant_has_no_growth_bonus(self, scene: GardenScene) -> None:
        cell = (0, 0)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")

        scene.system_manager.update(FIXED_DT)

        assert _plant_component(scene, cell).growth_multiplier == 1.0

    def test_overripe_growth_progress_does_not_climb_unbounded(
        self, scene: GardenScene
    ) -> None:
        """`"harvestable"` itself is meant to keep accumulating now -- that
        is its ripeness clock (`TestOverripening`) -- but `"overripe"`,
        what it reaches once that clock runs out, must freeze the same as
        `"infested"`/`"dying"` always have, or a save would carry an
        ever-growing number for no reason."""
        cell = (0, 0)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.water(cell)

        # ~9s to harvestable, ~4.5s more to overripe: 16s is comfortably past.
        _tick(scene, 16.0)
        plant = _plant_component(scene, cell)
        assert plant.growth_stage == "overripe"
        progress_at_overripe = plant.growth_progress

        _tick(scene, 5.0)
        assert _plant_component(scene, cell).growth_progress == progress_at_overripe

    def test_growth_stalls_below_the_moisture_threshold(
        self, scene: GardenScene
    ) -> None:
        cell = (0, 0)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.soil_at(cell).moisture = 0.0

        _tick(scene, 5.0)

        assert _plant_component(scene, cell).growth_progress == 0.0
        assert _plant_component(scene, cell).growth_stage == "seedling"

    def test_watering_resumes_stalled_growth(self, scene: GardenScene) -> None:
        cell = (0, 0)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.soil_at(cell).moisture = 0.0
        _tick(scene, 2.0)
        assert _plant_component(scene, cell).growth_progress == 0.0

        scene.grid.water(cell)
        _tick(scene, 2.0)

        assert _plant_component(scene, cell).growth_progress > 0.0


class TestStratificationBonus:
    def test_ground_cover_gets_a_bonus_next_to_a_different_layer(
        self, scene: GardenScene
    ) -> None:
        scene.grid.till((5, 5))
        scene._plant((5, 5), "baru")
        scene.grid.till((5, 6))
        scene._plant((5, 6), "guandu")

        scene.system_manager.update(FIXED_DT)

        assert _plant_component(scene, (5, 6)).growth_multiplier > 1.0

    def test_ground_cover_gets_no_bonus_next_to_its_own_layer(
        self, scene: GardenScene
    ) -> None:
        scene.grid.till((5, 5))
        scene._plant((5, 5), "guandu")
        scene.grid.till((5, 6))
        scene._plant((5, 6), "guandu")

        scene.system_manager.update(FIXED_DT)

        assert _plant_component(scene, (5, 6)).growth_multiplier == 1.0

    def test_understory_needs_a_matured_canopy_neighbor_to_be_shaded(
        self, scene: GardenScene
    ) -> None:
        scene.grid.till((3, 3))
        scene._plant((3, 3), "baru")
        scene.grid.water((3, 3))
        scene.grid.till((3, 4))
        scene._plant((3, 4), "cagaita")

        # Baru has not matured yet -- no shade, no bonus.
        scene.system_manager.update(FIXED_DT)
        assert _plant_component(scene, (3, 4)).growth_multiplier == 1.0

        # Run until Baru (the slower canopy species) reaches "mature".
        for _ in range(round(60 / FIXED_DT)):
            scene.system_manager.update(FIXED_DT)
            scene.entity_manager.flush_pending_removals()
            if _plant_component(scene, (3, 3)).growth_stage in (
                "mature",
                "harvestable",
            ):
                break

        scene.system_manager.update(FIXED_DT)
        assert scene.grid.soil_at((3, 4)).shade_level > 0.0
        assert _plant_component(scene, (3, 4)).growth_multiplier > 1.0

    def test_canopy_never_gets_a_bonus(self, scene: GardenScene) -> None:
        scene.grid.till((5, 5))
        scene._plant((5, 5), "baru")
        scene.grid.till((5, 6))
        scene._plant((5, 6), "guandu")

        scene.system_manager.update(FIXED_DT)

        assert _plant_component(scene, (5, 5)).growth_multiplier == 1.0


class TestMoisture:
    def test_moisture_evaporates_over_time(self, scene: GardenScene) -> None:
        cell = (0, 0)
        scene.grid.water(cell)
        after_watering = scene.grid.soil_at(cell).moisture

        _tick(scene, 10.0)

        assert scene.grid.soil_at(cell).moisture < after_watering

    def test_moisture_never_drops_below_zero(self, scene: GardenScene) -> None:
        cell = (0, 0)
        scene.grid.soil_at(cell).moisture = 0.01

        _tick(scene, 5.0)

        assert scene.grid.soil_at(cell).moisture == 0.0

    def test_watering_a_saturated_cell_is_a_noop(self, scene: GardenScene) -> None:
        cell = (0, 0)
        scene.grid.soil_at(cell).moisture = 1.0

        assert scene.grid.water(cell) is False
        assert scene.grid.soil_at(cell).moisture == 1.0


def _force_stage(scene: GardenScene, cell: tuple[int, int], stage: str) -> None:
    """Put a planted plant straight into `stage` through its own FSM.

    Through `_transition_to`, not by writing `growth_stage`, so the state's
    `on_enter()` runs and the machine and the component agree.
    """
    entity = scene.entity_manager.get_entity(scene.grid.plant_at[cell])
    entity.get_component(AIComponent).fsm._transition_to(stage)


def _plant_at(
    scene: GardenScene, cell: tuple[int, int], species: str, stage: str = "growing"
) -> None:
    scene.grid.till(cell)
    scene._plant(cell, species)
    _force_stage(scene, cell, stage)


class TestPestPressure:
    def test_pressure_spreads_to_a_vulnerable_neighbour(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (5, 5), "guandu")
        _plant_at(scene, (5, 6), "cagaita")
        scene.grid.soil_at((5, 5)).pest_pressure = 0.8

        _tick(scene, 3.0)

        assert scene.grid.soil_at((5, 6)).pest_pressure > 0.0

    def test_seedlings_are_immune(self, scene: GardenScene) -> None:
        _plant_at(scene, (5, 5), "guandu")
        _plant_at(scene, (5, 6), "cagaita", stage="seedling")
        # Dry, so the seedling cannot grow out of its immunity mid-test.
        scene.grid.soil_at((5, 6)).moisture = 0.0
        scene.grid.soil_at((5, 5)).pest_pressure = 0.8

        _tick(scene, 5.0)

        assert scene.grid.soil_at((5, 6)).pest_pressure == 0.0
        assert _plant_component(scene, (5, 6)).health == 1.0

    def test_a_monoculture_spreads_faster_than_a_mixed_plot(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (2, 2), "guandu")
        _plant_at(scene, (2, 3), "guandu")
        _plant_at(scene, (8, 2), "guandu")
        _plant_at(scene, (8, 3), "cagaita")
        scene.grid.soil_at((2, 2)).pest_pressure = 0.8
        scene.grid.soil_at((8, 2)).pest_pressure = 0.8

        _tick(scene, 2.0)

        assert (
            scene.grid.soil_at((2, 3)).pest_pressure
            > scene.grid.soil_at((8, 3)).pest_pressure
        )

    def test_organic_matter_speeds_up_decay(self, scene: GardenScene) -> None:
        rich, poor = (2, 2), (8, 2)
        scene.grid.soil_at(rich).organic_matter = 1.0
        scene.grid.soil_at(poor).organic_matter = 0.0
        scene.grid.soil_at(rich).pest_pressure = 0.6
        scene.grid.soil_at(poor).pest_pressure = 0.6

        _tick(scene, 3.0)

        assert (
            scene.grid.soil_at(rich).pest_pressure
            < scene.grid.soil_at(poor).pest_pressure
        )

    def test_pests_with_no_host_die_off_faster(self, scene: GardenScene) -> None:
        hosted, empty = (2, 2), (8, 2)
        _plant_at(scene, hosted, "guandu")
        scene.grid.soil_at(hosted).pest_pressure = 0.4
        scene.grid.soil_at(empty).pest_pressure = 0.4

        _tick(scene, 3.0)

        assert (
            scene.grid.soil_at(empty).pest_pressure
            < scene.grid.soil_at(hosted).pest_pressure
        )

    def test_a_grown_pequi_repels_pests(self, scene: GardenScene) -> None:
        near, far = (2, 2), (8, 2)
        _plant_at(scene, (2, 3), "pequi", stage="mature")
        scene.grid.soil_at(near).pest_pressure = 0.6
        scene.grid.soil_at(far).pest_pressure = 0.6

        _tick(scene, 3.0)

        assert (
            scene.grid.soil_at(near).pest_pressure
            < scene.grid.soil_at(far).pest_pressure
        )

    def test_a_young_pequi_does_not_repel_yet(self, scene: GardenScene) -> None:
        near, far = (2, 2), (8, 2)
        _plant_at(scene, (2, 3), "pequi", stage="growing")
        scene.grid.soil_at(near).pest_pressure = 0.6
        scene.grid.soil_at(far).pest_pressure = 0.6

        _tick(scene, 3.0)

        assert scene.grid.soil_at(near).pest_pressure == pytest.approx(
            scene.grid.soil_at(far).pest_pressure
        )


class TestInfestation:
    def test_pest_pressure_makes_a_plant_infested(self, scene: GardenScene) -> None:
        _plant_at(scene, (3, 3), "baru", stage="mature")
        scene.grid.soil_at((3, 3)).pest_pressure = 0.8

        _tick(scene, 0.2)

        assert _plant_component(scene, (3, 3)).growth_stage == "infested"

    def test_a_seedling_is_never_infested(self, scene: GardenScene) -> None:
        scene.grid.till((3, 3))
        scene._plant((3, 3), "baru")
        scene.grid.soil_at((3, 3)).pest_pressure = 0.9

        _tick(scene, 3.0)

        assert _plant_component(scene, (3, 3)).growth_stage == "seedling"

    def test_an_infested_plant_does_not_grow(self, scene: GardenScene) -> None:
        _plant_at(scene, (3, 3), "baru", stage="mature")
        scene.grid.soil_at((3, 3)).organic_matter = 0.0
        scene.grid.soil_at((3, 3)).pest_pressure = 0.8
        scene.grid.water((3, 3))
        _tick(scene, 0.2)
        assert _plant_component(scene, (3, 3)).growth_stage == "infested"
        progress = _plant_component(scene, (3, 3)).growth_progress

        _tick(scene, 3.0)

        assert _plant_component(scene, (3, 3)).growth_progress == progress

    def test_it_recovers_to_the_stage_and_progress_it_left(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (3, 3), "baru", stage="mature")
        _plant_component(scene, (3, 3)).growth_progress = 0.6
        scene.grid.soil_at((3, 3)).pest_pressure = 0.8
        _tick(scene, 0.2)
        assert _plant_component(scene, (3, 3)).growth_stage == "infested"

        scene.grid.soil_at((3, 3)).pest_pressure = 0.0
        _tick(scene, 0.2)

        plant = _plant_component(scene, (3, 3))
        assert plant.growth_stage == "mature"
        assert plant.growth_progress >= 0.6

    def test_an_untreated_plant_dies(self, scene: GardenScene) -> None:
        _plant_at(scene, (3, 3), "baru", stage="mature")
        soil = scene.grid.soil_at((3, 3))
        soil.organic_matter = 0.0
        soil.pest_pressure = 0.9

        _tick(scene, 45.0)

        assert _plant_component(scene, (3, 3)).growth_stage == "dying"

    def test_a_dying_plant_stays_dying(self, scene: GardenScene) -> None:
        _plant_at(scene, (3, 3), "baru", stage="mature")
        _force_stage(scene, (3, 3), "dying")

        _tick(scene, 5.0)

        assert _plant_component(scene, (3, 3)).growth_stage == "dying"


class TestTreatments:
    def test_compost_costs_sementes_and_enriches_the_soil(
        self, scene: GardenScene
    ) -> None:
        cell = (2, 2)
        scene.grid.till(cell)
        before = scene.grid.soil_at(cell).organic_matter
        credits = scene.economy.credits

        result = treatments.apply_compost(
            scene.grid, scene.economy, scene.conditions, cell
        )

        assert result == treatments.OK
        assert scene.grid.soil_at(cell).organic_matter > before
        assert scene.economy.credits == credits - COMPOST_COST
        assert scene.conditions.last_treatment == "organic"

    def test_compost_on_raw_dirt_does_nothing_and_costs_nothing(
        self, scene: GardenScene
    ) -> None:
        credits = scene.economy.credits

        result = treatments.apply_compost(
            scene.grid, scene.economy, scene.conditions, (2, 2)
        )

        assert result == treatments.NOTHING
        assert scene.economy.credits == credits

    def test_compost_needs_the_money(self, scene: GardenScene) -> None:
        cell = (2, 2)
        scene.grid.till(cell)
        scene.economy.credits = COMPOST_COST - 1
        before = scene.grid.soil_at(cell).organic_matter

        result = treatments.apply_compost(
            scene.grid, scene.economy, scene.conditions, cell
        )

        assert result == treatments.BROKE
        assert scene.grid.soil_at(cell).organic_matter == before

    def test_spray_clears_a_three_by_three_and_degrades_the_soil(
        self, scene: GardenScene
    ) -> None:
        centre = (5, 5)
        for cell in ((5, 5), (6, 5), (4, 4)):
            scene.grid.soil_at(cell).pest_pressure = 0.7
        far = (9, 5)
        scene.grid.soil_at(far).pest_pressure = 0.7
        credits = scene.economy.credits

        result = treatments.apply_spray(
            scene.grid,
            scene.entity_manager,
            scene.economy,
            scene.conditions,
            centre,
        )

        assert result == treatments.OK
        for cell in ((5, 5), (6, 5), (4, 4)):
            assert scene.grid.soil_at(cell).pest_pressure == 0.0
            assert scene.grid.soil_at(cell).is_chemically_degraded
        assert scene.grid.soil_at(far).pest_pressure == 0.7
        assert not scene.grid.soil_at(far).is_chemically_degraded
        assert scene.economy.credits == credits - SPRAY_COST
        assert scene.conditions.last_treatment == "chemical"

    def test_spray_marks_every_plant_it_reaches(self, scene: GardenScene) -> None:
        _plant_at(scene, (5, 5), "guandu")
        _plant_at(scene, (6, 6), "cagaita")
        _plant_at(scene, (10, 6), "baru")

        treatments.apply_spray(
            scene.grid,
            scene.entity_manager,
            scene.economy,
            scene.conditions,
            (5, 5),
        )

        assert _plant_component(scene, (5, 5)).is_chemical_boosted
        assert _plant_component(scene, (6, 6)).is_chemical_boosted
        assert not _plant_component(scene, (10, 6)).is_chemical_boosted

    def test_spray_needs_the_money(self, scene: GardenScene) -> None:
        scene.economy.credits = SPRAY_COST - 1
        scene.grid.soil_at((5, 5)).pest_pressure = 0.7

        result = treatments.apply_spray(
            scene.grid,
            scene.entity_manager,
            scene.economy,
            scene.conditions,
            (5, 5),
        )

        assert result == treatments.BROKE
        assert scene.grid.soil_at((5, 5)).pest_pressure == 0.7
        assert not scene.grid.soil_at((5, 5)).is_chemically_degraded

    def test_compost_heals_degraded_soil_once_it_is_rich_enough(
        self, scene: GardenScene
    ) -> None:
        cell = (5, 5)
        scene.grid.till(cell)
        treatments.apply_spray(
            scene.grid, scene.entity_manager, scene.economy, scene.conditions, cell
        )
        assert scene.grid.soil_at(cell).is_chemically_degraded

        treatments.apply_compost(scene.grid, scene.economy, scene.conditions, cell)
        assert scene.grid.soil_at(cell).is_chemically_degraded

        treatments.apply_compost(scene.grid, scene.economy, scene.conditions, cell)
        assert not scene.grid.soil_at(cell).is_chemically_degraded

    def test_a_sprayed_plant_grows_faster_but_degraded_soil_slows_it(
        self, scene: GardenScene
    ) -> None:
        plain, sprayed = (2, 2), (9, 5)
        for cell in (plain, sprayed):
            scene.grid.till(cell)
            scene._plant(cell, "guandu")
            scene.grid.water(cell)
        treatments.apply_spray(
            scene.grid,
            scene.entity_manager,
            scene.economy,
            scene.conditions,
            sprayed,
        )

        _tick(scene, 1.0)

        # +50% for the chemical boost, -20% for the degraded soil: net faster.
        assert (
            _plant_component(scene, sprayed).growth_progress
            > _plant_component(scene, plain).growth_progress
        )


class TestEconomy:
    def test_planting_charges_the_seed_cost(self, scene: GardenScene) -> None:
        scene.grid.till((2, 2))
        credits = scene.economy.credits

        scene._plant((2, 2), "baru")

        assert scene.economy.credits == credits - SPECIES_TABLE["baru"].seed_cost

    def test_an_unaffordable_seed_plants_nothing(self, scene: GardenScene) -> None:
        scene.grid.till((2, 2))
        scene.economy.credits = SPECIES_TABLE["baru"].seed_cost - 1

        scene._plant((2, 2), "baru")

        assert (2, 2) not in scene.grid.plant_at
        assert scene.economy.credits == SPECIES_TABLE["baru"].seed_cost - 1

    def test_an_organic_harvest_sells_at_the_premium(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "baru", stage="harvestable")
        credits = scene.economy.credits
        plant = _plant_component(scene, (2, 2))

        scene._harvest((2, 2))

        assert sale_value(plant) == SPECIES_TABLE["baru"].base_price * 2
        assert scene.economy.credits == credits + sale_value(plant)
        assert scene.economy.organic_sales == 1
        assert (2, 2) not in scene.grid.plant_at

    def test_a_chemical_harvest_sells_at_the_discount(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "baru", stage="harvestable")
        _plant_component(scene, (2, 2)).is_chemical_boosted = True
        credits = scene.economy.credits
        plant = _plant_component(scene, (2, 2))

        scene._harvest((2, 2))

        assert sale_value(plant) == SPECIES_TABLE["baru"].base_price // 2
        assert scene.economy.credits == credits + sale_value(plant)
        assert scene.economy.chemical_sales == 1

    def test_the_organic_premium_beats_the_chemical_shortcut(
        self, scene: GardenScene
    ) -> None:
        organic = PlantComponent(species_id="cagaita")
        chemical = PlantComponent(species_id="cagaita", is_chemical_boosted=True)

        assert sale_value(organic) == 4 * sale_value(chemical)

    def test_an_infested_plant_cannot_be_harvested(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "baru", stage="harvestable")
        _force_stage(scene, (2, 2), "infested")
        credits = scene.economy.credits

        scene._harvest((2, 2))

        assert (2, 2) in scene.grid.plant_at
        assert scene.economy.credits == credits

    def test_a_dying_plant_is_cleared_for_nothing(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "baru")
        _force_stage(scene, (2, 2), "dying")
        credits = scene.economy.credits

        scene._harvest((2, 2))

        assert (2, 2) not in scene.grid.plant_at
        assert scene.economy.credits == credits
        assert scene.grid.can_plant((2, 2))


class TestOverripening:
    """Left too long, a harvestable plant goes `"overripe"` -- and pays out
    a seed of its own species instead of Sementes when finally collected."""

    def test_a_harvestable_plant_left_too_long_goes_overripe(
        self, scene: GardenScene
    ) -> None:
        cell = (2, 2)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.water(cell)

        # ~9s to harvestable, ~4.5s more to overripe: 16s is comfortably past.
        _tick(scene, 16.0)

        assert _plant_component(scene, cell).growth_stage == "overripe"

    def test_collecting_it_overripe_stocks_a_seed_instead_of_selling(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (2, 2), "baru", stage="overripe")
        credits = scene.economy.credits

        scene._harvest((2, 2))

        assert scene.economy.credits == credits
        assert scene.economy.inventory[specific_seed_key("baru")] == 1
        assert (2, 2) not in scene.grid.plant_at

    def test_collecting_it_at_its_peak_still_sells_normally(
        self, scene: GardenScene
    ) -> None:
        """The unchanged, `"harvestable"` half of the same tool."""
        _plant_at(scene, (2, 2), "baru", stage="harvestable")
        credits = scene.economy.credits

        scene._harvest((2, 2))

        assert scene.economy.credits > credits
        assert specific_seed_key("baru") not in scene.economy.inventory

    def test_a_stocked_seed_is_spent_before_sementes(self, scene: GardenScene) -> None:
        scene.economy.inventory[specific_seed_key("baru")] = 1
        credits = scene.economy.credits
        scene.grid.till((3, 3))

        scene._plant((3, 3), "baru")

        assert scene.economy.credits == credits
        assert scene.economy.inventory[specific_seed_key("baru")] == 0
        assert (3, 3) in scene.grid.plant_at

    def test_planting_falls_back_to_sementes_once_stock_is_empty(
        self, scene: GardenScene
    ) -> None:
        scene.grid.till((3, 3))
        credits = scene.economy.credits

        scene._plant((3, 3), "baru")

        assert scene.economy.credits == credits - SPECIES_TABLE["baru"].seed_cost


class TestWeeds:
    """The plot acting on its own, and the generic-seed economy it feeds."""

    def test_pulling_a_weed_grants_a_generic_seed_not_credits(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (2, 2), "weed", stage="harvestable")
        credits = scene.economy.credits

        scene._harvest((2, 2))

        assert scene.economy.credits == credits
        assert scene.economy.inventory[GENERIC_SEED_KEY] == 1
        assert (2, 2) not in scene.grid.plant_at

    def test_pulling_an_overripe_weed_grants_a_bonus(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "weed", stage="overripe")

        scene._harvest((2, 2))

        assert scene.economy.inventory[GENERIC_SEED_KEY] == OVERRIPE_WEED_SEED_BONUS

    def test_sowing_a_generic_seed_spends_stock_and_plants_a_sellable_species(
        self, scene: GardenScene
    ) -> None:
        scene.economy.inventory[GENERIC_SEED_KEY] = 1
        scene.grid.till((3, 3))

        scene._sow_generic((3, 3))

        assert scene.economy.inventory[GENERIC_SEED_KEY] == 0
        assert (3, 3) in scene.grid.plant_at
        planted = SPECIES_TABLE[_plant_component(scene, (3, 3)).species_id]
        assert not planted.is_weed

    def test_sowing_with_no_stock_plants_nothing(self, scene: GardenScene) -> None:
        scene.grid.till((3, 3))

        scene._sow_generic((3, 3))

        assert (3, 3) not in scene.grid.plant_at

    def test_a_check_below_the_propagation_interval_does_nothing(
        self, scene: GardenScene
    ) -> None:
        """A short tick (most of this suite's own ticks) must never trigger
        a check -- the whole reason it is timer-gated, not per-tick."""
        scene.grid.till((2, 2))
        system = WeedSpreadSystem(scene.entity_manager, scene.grid, RandomStream(1))

        system.update(PROPAGATION_INTERVAL - 0.1)

        assert not scene.grid.plant_at

    def test_a_mature_plant_can_spread_to_a_free_neighbour(
        self, scene: GardenScene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(
            SPECIES_TABLE, "guandu", replace(SPECIES_TABLE["guandu"], spread_chance=1.0)
        )
        _plant_at(scene, (5, 5), "guandu", stage="mature")
        scene.grid.till((5, 6))  # the only free neighbour
        system = WeedSpreadSystem(scene.entity_manager, scene.grid, RandomStream(3))

        system.update(PROPAGATION_INTERVAL)

        assert (5, 6) in scene.grid.plant_at
        assert _plant_component(scene, (5, 6)).species_id == "guandu"

    def test_a_growing_plant_does_not_spread(
        self, scene: GardenScene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Too young to have anything to spare -- see `SPREADING_STAGES`."""
        monkeypatch.setitem(
            SPECIES_TABLE, "guandu", replace(SPECIES_TABLE["guandu"], spread_chance=1.0)
        )
        _plant_at(scene, (5, 5), "guandu", stage="growing")
        scene.grid.till((5, 6))
        system = WeedSpreadSystem(scene.entity_manager, scene.grid, RandomStream(3))

        system.update(PROPAGATION_INTERVAL)

        assert (5, 6) not in scene.grid.plant_at

    def test_a_bare_tilled_cell_can_spontaneously_grow_a_weed(
        self, scene: GardenScene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(weed_module, "SPONTANEOUS_WEED_CHANCE", 1.0)
        scene.grid.till((4, 4))
        system = WeedSpreadSystem(scene.entity_manager, scene.grid, RandomStream(5))

        system.update(PROPAGATION_INTERVAL)

        assert (4, 4) in scene.grid.plant_at
        assert _plant_component(scene, (4, 4)).species_id == "weed"


class TestOutbreakFsm:
    @pytest.fixture(autouse=True)
    def _fast_outbreaks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(garden_states, "OUTBREAK_DELAY", 1.0)
        monkeypatch.setattr(garden_states, "RESOLVED_COOLDOWN", 1.0)

    def _three_plants(self, scene: GardenScene) -> None:
        for cell in ((2, 2), (5, 5), (9, 3)):
            _plant_at(scene, cell, "guandu")

    def test_an_outbreak_needs_enough_established_plants(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (2, 2), "guandu")
        _plant_at(scene, (5, 5), "guandu")

        _tick(scene, 5.0)

        assert scene.conditions.phase == "stable"

    def test_an_outbreak_ignores_seedlings(self, scene: GardenScene) -> None:
        for cell in ((2, 2), (5, 5), (9, 3)):
            _plant_at(scene, cell, "guandu", stage="seedling")
            # Dry, so they stay seedlings for the whole test.
            scene.grid.soil_at(cell).moisture = 0.0

        _tick(scene, 5.0)

        assert scene.conditions.phase == "stable"

    def test_an_outbreak_begins_and_is_announced(self, scene: GardenScene) -> None:
        started: list[OutbreakStartedEvent] = []
        scene.event_dispatcher.subscribe(OutbreakStartedEvent, started.append)
        self._three_plants(scene)

        _tick(scene, 3.0)

        assert scene.conditions.phase == "outbreak"
        assert len(started) == 1
        assert 0 < len(started[0].cells) <= garden_states.OUTBREAK_CELLS
        for cell in started[0].cells:
            assert cell in scene.grid.plant_at

    def test_an_outbreak_only_starts_on_plants(self, scene: GardenScene) -> None:
        self._three_plants(scene)
        _tick(scene, 3.0)

        infested = [
            (x, y)
            for y, row in enumerate(scene.grid.soil)
            for x, soil in enumerate(row)
            if soil.pest_pressure > 0.0
        ]
        assert infested
        assert all(cell in scene.grid.plant_at for cell in infested)

    def test_a_seeded_rng_makes_a_reproducible_outbreak(
        self, game_container: DIContainer
    ) -> None:
        def cells_for(seed: int) -> list[tuple[int, int]]:
            garden = GardenScene(
                game_container.get(EventDispatcher), rng=RandomStream(seed)
            )
            manager = game_container.get(SceneManager)
            manager.register(garden)
            manager.switch_to("GardenScene")
            for cell in ((2, 2), (5, 5), (9, 3), (3, 6), (7, 6)):
                _plant_at(garden, cell, "guandu")
            started: list[OutbreakStartedEvent] = []
            garden.event_dispatcher.subscribe(OutbreakStartedEvent, started.append)
            _tick(garden, 3.0)
            return started[-1].cells

        assert cells_for(7) == cells_for(7)

    def test_it_resolves_organically_once_the_pests_are_gone(
        self, scene: GardenScene
    ) -> None:
        resolved: list[OutbreakResolvedEvent] = []
        scene.event_dispatcher.subscribe(OutbreakResolvedEvent, resolved.append)
        self._three_plants(scene)
        _tick(scene, 3.0)
        assert scene.conditions.phase == "outbreak"

        for row in scene.grid.soil:
            for soil in row:
                soil.pest_pressure = 0.0
        _tick(scene, 0.2)

        assert scene.conditions.phase == "resolved_organic"
        assert scene.conditions.organic_resolutions == 1
        assert resolved[-1].method == "organic"

    def test_it_resolves_chemically_after_a_spray(self, scene: GardenScene) -> None:
        self._three_plants(scene)
        _tick(scene, 3.0)
        assert scene.conditions.phase == "outbreak"

        for row in scene.grid.soil:
            for soil in row:
                soil.pest_pressure = 0.0
        scene.conditions.last_treatment = "chemical"
        _tick(scene, 0.2)

        assert scene.conditions.phase == "resolved_chemical"
        assert scene.conditions.chemical_resolutions == 1

    def test_it_returns_to_stable_after_the_cooldown(self, scene: GardenScene) -> None:
        self._three_plants(scene)
        _tick(scene, 3.0)
        for row in scene.grid.soil:
            for soil in row:
                soil.pest_pressure = 0.0
        _tick(scene, 0.2)
        assert scene.conditions.phase == "resolved_organic"

        _tick(scene, 1.5)

        assert scene.conditions.phase in ("stable", "outbreak")
