"""Plant growth, shade, and companion-bonus logic, headless.

Drives `GardenScene.system_manager.update(dt)` directly -- the same call
`SceneManager.fixed_update()` makes automatically for every active scene
-- rather than a full `Application.run()` loop, so a stage transition
that should take a few seconds of simulated ticks stays a fast test.

No real window: builds the same minimal, mocked container
`tests/test_quintal_cerrado_screens.py` uses, rather than
`bootstrap.configure_game_container()`, which opens a real `PygameWindow`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.scenes import GardenScene
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.audio.audio_system import IAudioSystem
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager

SCREEN = (960, 640)
FIXED_DT = 1 / 60


@pytest.fixture
def game_container() -> DIContainer:
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
    input_manager = InputManager(dispatcher, MagicMock(spec=IInputBackend))
    container.register_instance(InputManager, input_manager)
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

        seen_stages = set()
        for _ in range(round(30 / FIXED_DT)):
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

    def test_harvestable_growth_progress_does_not_climb_unbounded(
        self, scene: GardenScene
    ) -> None:
        cell = (0, 0)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        scene.grid.water(cell)

        _tick(scene, SPECIES_TABLE["guandu"].stage_seconds * 3 + 1.0)
        plant = _plant_component(scene, cell)
        assert plant.growth_stage == "harvestable"
        progress_at_harvest = plant.growth_progress

        _tick(scene, 5.0)
        assert _plant_component(scene, cell).growth_progress == progress_at_harvest

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
