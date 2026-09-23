# ruff: noqa: F811  (fixtures imported from the growth tests are used by name)
"""Saving, loading, scoring, and the overlays and HUD built around them.

The first tests to exercise `pyguara.persistence` through a real demo: a real
`PersistenceManager` over a `FileStorageBackend` in a temp directory, so what
is asserted is what actually survives a trip through JSON on disk -- not what
survives being handed from one dict to another.

Reuses `tests/test_quintal_cerrado_growth.py`'s container and scene fixtures.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from games.quintal_cerrado import clock, structures
from games.quintal_cerrado.components import (
    AutomationComponent,
    PlantComponent,
    PlayerEconomy,
)
from games.quintal_cerrado.evaluation import EvaluationScene
from games.quintal_cerrado.events import OutbreakStartedEvent
from games.quintal_cerrado.pause import PauseScene
from games.quintal_cerrado.persistence_schema import (
    SAVE_KEY,
    SCHEMA_VERSION,
    SaveFormatError,
    apply_save_payload,
    to_save_payload,
)
from games.quintal_cerrado.scenes import GardenScene, TitleScene
from games.quintal_cerrado.scoring import compute_score
from games.quintal_cerrado.systems.day_resolver import SUB_STEP
from games.quintal_cerrado.turn import SESSION_DAYS, DayCycle
from pyguara.ai.components import AIComponent
from pyguara.common.types import Vector2
from pyguara.events.input import KeyDownEvent, MouseMotionEvent
from pyguara.input.keys import ESCAPE
from pyguara.input.manager import InputManager
from pyguara.persistence.manager import PersistenceManager
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIEventType
from tests.test_quintal_cerrado_growth import (  # noqa: F401
    _force_stage,
    _nights,
    _plant_at,
    _resolve,
    game_container,
    scene,
)


def _persistence(scene: GardenScene) -> PersistenceManager:
    return scene.container.get(PersistenceManager)


def _plant(scene: GardenScene, cell: tuple[int, int]) -> PlantComponent:
    entity = scene.entity_manager.get_entity(scene.grid.plant_at[cell])
    return entity.get_component(PlantComponent)


def _fsm_stage(scene: GardenScene, cell: tuple[int, int]) -> str:
    entity = scene.entity_manager.get_entity(scene.grid.plant_at[cell])
    return entity.get_component(AIComponent).fsm._current_state_name  # type: ignore[union-attr]


def _lived_in_garden(scene: GardenScene) -> None:
    """A garden with something of everything in it, to save.

    Ordered so every value a test asserts is set *last*: ticking to infest a
    plant, or buying a structure, would otherwise move them.
    """
    _plant_at(scene, (1, 1), "guandu", stage="mature")
    _plant_at(scene, (2, 1), "baru", stage="harvestable")
    _plant_at(scene, (3, 1), "cagaita", stage="growing")
    _plant_at(scene, (4, 1), "pequi", stage="seedling")
    _plant_at(scene, (5, 1), "baru", stage="mature")
    _plant_at(scene, (6, 1), "guandu", stage="dying")

    # An infested plant that remembers it was mature at 0.6.
    _plant(scene, (5, 1)).growth_progress = 0.6
    scene.grid.soil_at((5, 1)).pest_pressure = 0.8
    _resolve(scene, 0.2)
    assert _plant(scene, (5, 1)).growth_stage == "infested"

    structures.buy_structure(scene.economy, "solar_panel")
    structures.place_structure(
        scene.grid, scene.entity_manager, scene.economy, "solar_panel", (9, 5)
    )
    _plant(scene, (1, 1)).growth_progress = 0.42
    _plant(scene, (1, 1)).health = 0.7
    _plant(scene, (2, 1)).is_chemical_boosted = True
    _plant(scene, (3, 1)).growth_multiplier = 1.4

    scene.grid.soil_at((1, 1)).moisture = 0.91
    scene.grid.soil_at((2, 2)).is_chemically_degraded = True
    scene.grid.soil_at((3, 3)).organic_matter = 0.77

    scene.economy.credits = 321.5
    scene.economy.revenue = 88.0
    scene.economy.organic_sales = 4
    scene.economy.chemical_sales = 2
    scene.economy.inventory = {"soil_sensor": 2}
    scene.economy.unlocked_tech = {"solar_panel", "drip_irrigation"}

    scene.conditions.organic_resolutions = 3
    scene.conditions.chemical_resolutions = 1
    scene.turn = DayCycle(day=4, stamina=7)


def _reload(scene: GardenScene) -> GardenScene:
    """Save `scene`, then build a fresh garden that Continues from the file."""
    assert scene.save_now()
    fresh = GardenScene(scene.event_dispatcher, load=True)
    manager = scene.container.get(SceneManager)
    manager.register(fresh)
    manager.switch_to("GardenScene")
    return fresh


class TestThePayload:
    def test_it_is_plain_json_and_survives_a_trip_through_it(
        self, scene: GardenScene
    ) -> None:
        _lived_in_garden(scene)
        payload = to_save_payload(
            scene.grid,
            scene.entity_manager,
            scene.economy,
            scene.conditions,
            scene.turn,
        )

        assert json.loads(json.dumps(payload)) == payload

    def test_a_saved_file_loads_back_as_plain_dicts_not_dataclasses(
        self, scene: GardenScene
    ) -> None:
        """The engine gap the schema is built around.

        `Serializer` tags a dataclass with `__type__` on save but only
        rebuilds `Vector2`/`Color`/`Rect` on load, so a dataclass comes back
        as a dict. If this ever starts returning a real `PlayerEconomy`,
        the engine learned to round-trip dataclasses and the hand-built
        payload boundary can be revisited -- until then it must not be
        "simplified" away.
        """
        _lived_in_garden(scene)
        assert scene.save_now()

        loaded = _persistence(scene).load_data(SAVE_KEY)

        assert isinstance(loaded, dict)
        assert isinstance(loaded["player"], dict)
        assert not isinstance(loaded["player"], PlayerEconomy)
        assert loaded["version"] == SCHEMA_VERSION

    def test_the_file_is_written_at_the_schema_version(
        self, scene: GardenScene
    ) -> None:
        assert scene.save_now()

        assert SAVE_KEY in _persistence(scene).storage.list_keys()


class TestRoundTrip:
    def test_the_economy_and_the_calendar_come_back(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)

        loaded = _reload(scene)

        assert loaded.economy.credits == 321.5
        assert loaded.economy.revenue == 88.0
        assert loaded.economy.organic_sales == 4
        assert loaded.economy.chemical_sales == 2
        assert loaded.economy.inventory == {"soil_sensor": 2}
        assert loaded.economy.unlocked_tech >= {"solar_panel", "drip_irrigation"}
        assert loaded.turn.day == 4
        assert loaded.turn.stamina == 7

    def test_the_soil_comes_back(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)

        loaded = _reload(scene)

        assert loaded.grid.soil_at((1, 1)).moisture == pytest.approx(0.91, abs=0.01)
        assert loaded.grid.soil_at((2, 2)).is_chemically_degraded
        assert loaded.grid.soil_at((3, 3)).organic_matter == 0.77
        assert loaded.grid.soil_at((1, 1)).soil_type == "tilled_dirt"
        assert loaded.grid.soil_at((10, 7)).soil_type == "raw_dirt"

    def test_every_plant_comes_back_as_it_was(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)
        before = {
            cell: (
                p.species_id,
                p.growth_stage,
                p.is_chemical_boosted,
                round(p.health, 6),
            )
            for cell in scene.grid.plant_at
            for p in [_plant(scene, cell)]
        }

        loaded = _reload(scene)

        after = {
            cell: (
                p.species_id,
                p.growth_stage,
                p.is_chemical_boosted,
                round(p.health, 6),
            )
            for cell in loaded.grid.plant_at
            for p in [_plant(loaded, cell)]
        }
        assert after == before

    def test_a_loaded_plants_machine_agrees_with_its_component(
        self, scene: GardenScene
    ) -> None:
        _lived_in_garden(scene)

        loaded = _reload(scene)

        for cell in loaded.grid.plant_at:
            assert _fsm_stage(loaded, cell) == _plant(loaded, cell).growth_stage

    def test_mid_stage_growth_progress_comes_back(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)

        loaded = _reload(scene)

        assert _plant(loaded, (1, 1)).growth_progress == pytest.approx(0.42, abs=0.02)
        assert _plant(loaded, (1, 1)).health == pytest.approx(0.7, abs=0.01)

    def test_an_infested_plant_still_remembers_where_it_was_going(
        self, scene: GardenScene
    ) -> None:
        _lived_in_garden(scene)
        loaded = _reload(scene)
        assert _plant(loaded, (5, 1)).growth_stage == "infested"

        loaded.grid.soil_at((5, 1)).pest_pressure = 0.0
        _resolve(loaded, 0.3)

        assert _plant(loaded, (5, 1)).growth_stage == "mature"
        assert _plant(loaded, (5, 1)).growth_progress >= 0.59

    def test_structures_come_back(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)

        loaded = _reload(scene)

        entity = loaded.entity_manager.get_entity(loaded.grid.automation_at[(9, 5)])
        structure = entity.get_component(AutomationComponent)
        assert structure.kind == "solar_panel"
        assert structure.powered is True
        assert loaded.grid.automation_at[(9, 5)] == entity.id
        assert not loaded.grid.can_plant((9, 5))

    def test_the_tilemap_layers_are_rebuilt(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)

        loaded = _reload(scene)

        assert loaded.grid.tilemap.layers["terrain"].get_tile((1, 1)) != (
            loaded.grid.tilemap.layers["terrain"].get_tile((10, 7))
        )
        assert loaded.grid.tilemap.layers["flora"].get_tile((1, 1)) != 0
        assert loaded.grid.tilemap.layers["automation"].get_tile((9, 5)) != 0

    def test_a_loaded_garden_keeps_growing(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)
        loaded = _reload(scene)
        loaded.grid.water((1, 1))
        before = _plant(loaded, (1, 1)).growth_progress

        _resolve(loaded, 0.5)

        assert _plant(loaded, (1, 1)).growth_progress > before

    def test_an_overripe_plant_and_seed_stock_come_back(
        self, scene: GardenScene
    ) -> None:
        """The fun-improvement roadmap's Phase 3: a stage this build's
        `_PLANT_STAGES` only just learned, and inventory keys shaped
        nothing like a structure kind -- both need their own coverage
        beyond `_lived_in_garden`'s fixed scenario."""
        _plant_at(scene, (1, 1), "baru", stage="overripe")
        scene.economy.inventory = {
            "soil_sensor": 1,
            "generic_seed": 3,
            "seed:baru": 2,
        }

        loaded = _reload(scene)

        assert _plant(loaded, (1, 1)).growth_stage == "overripe"
        assert loaded.economy.inventory == {
            "soil_sensor": 1,
            "generic_seed": 3,
            "seed:baru": 2,
        }


class TestLoadingAnOutbreak:
    def _mid_outbreak(self, scene: GardenScene) -> None:
        for cell in ((2, 2), (5, 5), (9, 3)):
            _plant_at(scene, cell, "guandu")
        scene.conditions.phase = "stable"
        ai = scene.conditions.entity.get_component(AIComponent)
        ai.fsm._transition_to("outbreak")
        scene.conditions.organic_resolutions = 2

    def test_reloading_does_not_seed_the_outbreak_again(
        self, scene: GardenScene
    ) -> None:
        self._mid_outbreak(scene)
        saved_pressure = sum(s.pest_pressure for row in scene.grid.soil for s in row)
        assert saved_pressure > 0
        started: list[OutbreakStartedEvent] = []
        scene.event_dispatcher.subscribe(OutbreakStartedEvent, started.append)
        started.clear()

        loaded = _reload(scene)

        assert loaded.conditions.phase == "outbreak"
        assert started == []
        assert sum(s.pest_pressure for row in loaded.grid.soil for s in row) == (
            pytest.approx(saved_pressure)
        )

    def test_reloading_a_resolved_phase_does_not_count_it_twice(
        self, scene: GardenScene
    ) -> None:
        ai = scene.conditions.entity.get_component(AIComponent)
        ai.fsm._transition_to("resolved_organic")
        assert scene.conditions.organic_resolutions == 1

        loaded = _reload(scene)

        assert loaded.conditions.phase == "resolved_organic"
        assert loaded.conditions.organic_resolutions == 1


class TestARefusedSave:
    def _valid(self, scene: GardenScene) -> dict[str, Any]:
        _lived_in_garden(scene)
        return to_save_payload(
            scene.grid,
            scene.entity_manager,
            scene.economy,
            scene.conditions,
            scene.turn,
        )

    def _blank(self, scene: GardenScene) -> GardenScene:
        blank = GardenScene(scene.event_dispatcher)
        manager = scene.container.get(SceneManager)
        manager.register(blank)
        manager.switch_to("GardenScene")
        return blank

    @pytest.mark.parametrize(
        "damage",
        [
            lambda p: p.update(version=SCHEMA_VERSION + 1),
            lambda p: p.pop("player"),
            lambda p: p["player"].update(credits="lots"),
            lambda p: p["player"].update(inventory={"death_ray": 1}),
            lambda p: p["conditions"].update(phase="apocalypse"),
            lambda p: p["grid"].pop(),
            lambda p: p["grid"][0].update(x=99),
            lambda p: p["grid"][7]["plant"].update(growth_stage="zombie")
            if p["grid"][7]["plant"]
            else p["grid"][13]["plant"].update(growth_stage="zombie"),
            lambda p: p["grid"][0].update(automation={"kind": "mine", "powered": 1}),
        ],
        ids=[
            "newer-version",
            "missing-player",
            "wrong-type",
            "unknown-structure-in-inventory",
            "unknown-phase",
            "missing-cell",
            "cell-outside-plot",
            "unknown-plant-stage",
            "unknown-structure-in-grid",
        ],
    )
    def test_a_bad_save_is_refused_and_changes_nothing(
        self, scene: GardenScene, damage: Any
    ) -> None:
        payload = self._valid(scene)
        # Make sure the plant the lambda reaches for exists at index 13.
        payload = copy.deepcopy(payload)
        damage(payload)
        blank = self._blank(scene)
        credits = blank.economy.credits

        with pytest.raises(SaveFormatError):
            apply_save_payload(
                payload,
                blank.grid,
                blank.entity_manager,
                blank.economy,
                blank.conditions,
            )

        assert blank.economy.credits == credits
        assert blank.grid.plant_at == {}
        assert blank.grid.automation_at == {}

    def test_something_that_is_not_a_save_at_all_is_refused(
        self, scene: GardenScene
    ) -> None:
        for junk in (None, [], "save", 42):
            with pytest.raises(SaveFormatError):
                apply_save_payload(
                    junk,
                    scene.grid,
                    scene.entity_manager,
                    scene.economy,
                    scene.conditions,
                )

    def _continue_with(self, scene: GardenScene) -> GardenScene:
        """Continue from whatever is on disk, without the outgoing garden's
        save-on-exit touching it first."""
        scene.save_now = lambda: True  # type: ignore[method-assign]
        fresh = GardenScene(scene.event_dispatcher, load=True)
        manager = scene.container.get(SceneManager)
        manager.register(fresh)
        manager.switch_to("GardenScene")
        return fresh

    def test_continuing_with_no_save_starts_fresh_and_says_so(
        self, scene: GardenScene
    ) -> None:
        storage = _persistence(scene).storage
        for key in storage.list_keys():
            storage.delete(key)

        fresh = self._continue_with(scene)

        assert fresh.grid.plant_at == {}
        assert fresh._hud is not None
        assert fresh._hud.message_label.text == "No usable save"

    def test_a_corrupt_file_on_disk_starts_fresh_and_says_so(
        self, scene: GardenScene
    ) -> None:
        _persistence(scene).storage.save(SAVE_KEY, b"this is not a save")

        fresh = self._continue_with(scene)

        assert fresh.grid.plant_at == {}
        assert fresh.economy.credits == PlayerEconomy().credits
        assert fresh._hud is not None
        assert fresh._hud.message_label.text == "No usable save"

    def test_a_readable_file_that_is_not_a_valid_save_says_it_is_unreadable(
        self, scene: GardenScene
    ) -> None:
        # Well-formed on disk, wrong in content: exercises the schema's refusal
        # through the scene rather than through `apply_save_payload` directly.
        _persistence(scene).save_data(
            SAVE_KEY, {"version": SCHEMA_VERSION + 5}, save_version=SCHEMA_VERSION
        )

        fresh = self._continue_with(scene)

        assert fresh.grid.plant_at == {}
        assert fresh._hud is not None
        assert "unreadable" in fresh._hud.message_label.text


class TestWhenItSaves:
    def test_leaving_the_garden_saves_it(self, scene: GardenScene) -> None:
        storage = _persistence(scene).storage
        for key in storage.list_keys():
            storage.delete(key)

        scene.container.get(SceneManager).cleanup()

        assert SAVE_KEY in storage.list_keys()

    def test_sleeping_saves_the_garden(self, scene: GardenScene) -> None:
        """Replaces the old 60-second autosave: between two mornings there
        is nothing a save could have missed."""
        storage = _persistence(scene).storage
        for key in storage.list_keys():
            storage.delete(key)

        scene.end_day()

        assert SAVE_KEY in storage.list_keys()

    def test_nothing_is_saved_just_for_time_passing(self, scene: GardenScene) -> None:
        storage = _persistence(scene).storage
        for key in storage.list_keys():
            storage.delete(key)

        for _ in range(600):
            scene.update(1 / 60)

        assert SAVE_KEY not in storage.list_keys()


class TestTheTitleScreen:
    def _title(self, scene: GardenScene) -> TitleScene:
        title = TitleScene(scene.event_dispatcher)
        manager = scene.container.get(SceneManager)
        manager.register(title)
        manager.switch_to("TitleScene")
        return title

    def _buttons(self, scene: GardenScene) -> dict[str, Any]:
        from pyguara.ui.types import UILayer

        found = {}
        for root in scene.container.get(UIManager).elements(UILayer.CONTENT):
            for child in [root, *root.children]:
                if getattr(child, "text", None) in ("Continue", "New Garden"):
                    found[child.text] = child
        return found

    def test_continue_is_disabled_until_there_is_a_save(
        self, scene: GardenScene
    ) -> None:
        storage = _persistence(scene).storage
        for key in storage.list_keys():
            storage.delete(key)

        self._title(scene)
        # Switching away from the garden saved it; remove that to test "none".
        for key in storage.list_keys():
            storage.delete(key)
        self._title(scene)

        assert not self._buttons(scene)["Continue"].enabled
        assert self._buttons(scene)["New Garden"].enabled

    def test_continue_resumes_the_saved_garden(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)
        title = self._title(scene)
        assert self._buttons(scene)["Continue"].enabled

        title._on_continue(None)

        current = scene.container.get(SceneManager).current_scene
        assert isinstance(current, GardenScene)
        assert current.economy.credits == 321.5
        assert len(current.grid.plant_at) == 6

    def test_new_garden_ignores_the_save(self, scene: GardenScene) -> None:
        _lived_in_garden(scene)
        title = self._title(scene)

        title._on_new(None)

        current = scene.container.get(SceneManager).current_scene
        assert isinstance(current, GardenScene)
        assert current.grid.plant_at == {}
        assert current.economy.credits == PlayerEconomy().credits


class TestScoring:
    def test_an_empty_garden_scores_nothing(self, scene: GardenScene) -> None:
        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.total == 0
        assert score.grade == "Seed"

    def test_soil_health_is_the_humus_of_the_tilled_soil(
        self, scene: GardenScene
    ) -> None:
        for cell in ((0, 0), (1, 0)):
            scene.grid.till(cell)
            scene.grid.soil_at(cell).organic_matter = 1.0

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.soil_health == pytest.approx(1.0)

    def test_untilled_ground_does_not_dilute_soil_health(
        self, scene: GardenScene
    ) -> None:
        scene.grid.till((0, 0))
        scene.grid.soil_at((0, 0)).organic_matter = 0.8

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.soil_health == pytest.approx(0.8)

    def test_chemical_damage_halves_a_cells_contribution(
        self, scene: GardenScene
    ) -> None:
        scene.grid.till((0, 0))
        soil = scene.grid.soil_at((0, 0))
        soil.organic_matter = 1.0
        soil.is_chemically_degraded = True

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.soil_health == pytest.approx(0.5)

    def test_biodiversity_counts_distinct_living_species(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (0, 0), "guandu")
        _plant_at(scene, (1, 0), "guandu")
        _plant_at(scene, (2, 0), "baru")

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.biodiversity == pytest.approx(2 / 4)

    def test_a_dying_plant_does_not_count_towards_biodiversity(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (0, 0), "guandu")
        _plant_at(scene, (1, 0), "baru")
        _force_stage(scene, (1, 0), "dying")

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.biodiversity == pytest.approx(1 / 4)

    def test_a_weed_infested_plot_does_not_count_towards_biodiversity(
        self, scene: GardenScene
    ) -> None:
        """A weed is not a "species" the player is growing on purpose --
        an overrun plot must not score as thriving biodiversity for it."""
        _plant_at(scene, (0, 0), "guandu")
        _plant_at(scene, (1, 0), "weed")
        _plant_at(scene, (2, 0), "weed")

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.biodiversity == pytest.approx(1 / 4)

    def test_revenue_is_earnings_not_the_balance(self, scene: GardenScene) -> None:
        scene.economy.revenue = 300.0
        scene.economy.credits = 0.0

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.revenue == pytest.approx(0.5)

    def test_revenue_is_capped(self, scene: GardenScene) -> None:
        scene.economy.revenue = 10_000.0

        assert compute_score(
            scene.grid, scene.entity_manager, scene.economy
        ).revenue == pytest.approx(1.0)

    def test_the_organic_share_is_of_all_sales(self, scene: GardenScene) -> None:
        scene.economy.organic_sales = 3
        scene.economy.chemical_sales = 1

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.organic == pytest.approx(0.75)

    def test_a_perfect_garden_scores_a_thousand(self, scene: GardenScene) -> None:
        for index, species in enumerate(("guandu", "cagaita", "baru", "pequi")):
            _plant_at(scene, (index, 0), species)
            scene.grid.soil_at((index, 0)).organic_matter = 1.0
        scene.economy.revenue = 600.0
        scene.economy.organic_sales = 5

        score = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert score.total == 1000
        assert score.grade == "Guardian of the Cerrado"

    def test_going_chemical_scores_lower_than_staying_organic(
        self, scene: GardenScene
    ) -> None:
        for cell in ((0, 0), (1, 0)):
            scene.grid.till(cell)
            scene.grid.soil_at(cell).organic_matter = 0.9
        scene.economy.revenue = 300.0
        scene.economy.organic_sales, scene.economy.chemical_sales = 4, 0
        organic = compute_score(scene.grid, scene.entity_manager, scene.economy)

        for cell in ((0, 0), (1, 0)):
            scene.grid.soil_at(cell).is_chemically_degraded = True
        scene.economy.organic_sales, scene.economy.chemical_sales = 0, 4
        chemical = compute_score(scene.grid, scene.entity_manager, scene.economy)

        assert chemical.total < organic.total


class TestTheOverlays:
    def _title(self, scene: GardenScene) -> None:
        # `_quit_to_title` switches to a scene called TitleScene.
        manager = scene.container.get(SceneManager)
        manager.register(TitleScene(scene.event_dispatcher))

    def test_evaluating_saves_first_and_shows_the_score(
        self, scene: GardenScene
    ) -> None:
        storage = _persistence(scene).storage
        for key in storage.list_keys():
            storage.delete(key)

        scene.open_evaluation()

        assert SAVE_KEY in storage.list_keys()
        current = scene.container.get(SceneManager).current_scene
        assert isinstance(current, EvaluationScene)
        assert (
            current.score.total
            == compute_score(scene.grid, scene.entity_manager, scene.economy).total
        )
        assert set(current.bars) == {"soil", "biodiversity", "revenue", "organic"}

    def test_keep_playing_returns_to_a_running_garden(self, scene: GardenScene) -> None:
        scene.open_evaluation()
        evaluation = scene.container.get(SceneManager).current_scene

        evaluation._close()

        assert scene.container.get(SceneManager).current_scene is scene
        assert scene.system_manager.enabled

    def test_the_evaluation_arrives_after_the_last_night_once(
        self, scene: GardenScene
    ) -> None:
        manager = scene.container.get(SceneManager)
        scene.turn = DayCycle(day=SESSION_DAYS, stamina=0)

        scene.end_day()
        assert isinstance(manager.current_scene, EvaluationScene)

        manager.current_scene._close()
        scene.end_day()
        assert manager.current_scene is scene, "it is offered once, not nightly"

    def test_a_session_loaded_past_its_last_day_is_not_evaluated_again(
        self, scene: GardenScene
    ) -> None:
        scene.turn = DayCycle(day=SESSION_DAYS + 1, stamina=4)
        loaded = _reload(scene)

        loaded.update(1 / 60)

        assert loaded.container.get(SceneManager).current_scene is loaded

    def test_the_pause_menu_opens_on_a_real_escape_and_stays_open(
        self, scene: GardenScene
    ) -> None:
        """Esc both opens and closes the menu -- the same race as the store's `O`."""
        manager = scene.container.get(SceneManager)

        scene.container.get(InputManager).process_event(KeyDownEvent(key_code=ESCAPE))

        assert isinstance(manager.current_scene, PauseScene)

    def test_escape_closes_the_pause_menu_once_a_frame_has_passed(
        self, scene: GardenScene
    ) -> None:
        manager = scene.container.get(SceneManager)
        input_manager = scene.container.get(InputManager)
        input_manager.process_event(KeyDownEvent(key_code=ESCAPE))

        manager.current_scene.update(1 / 60)
        input_manager.process_event(KeyDownEvent(key_code=ESCAPE))

        assert manager.current_scene is scene

    def test_the_menu_button_opens_the_pause_menu(self, scene: GardenScene) -> None:
        assert scene._menu_button is not None

        scene._menu_button.on_click(scene._menu_button)

        assert isinstance(scene.container.get(SceneManager).current_scene, PauseScene)

    def test_saving_from_the_pause_menu_writes_and_says_so(
        self, scene: GardenScene
    ) -> None:
        storage = _persistence(scene).storage
        for key in storage.list_keys():
            storage.delete(key)
        scene._open_pause()
        pause = scene.container.get(SceneManager).current_scene
        assert isinstance(pause, PauseScene)

        pause._save(None)  # type: ignore[arg-type]

        assert SAVE_KEY in storage.list_keys()
        assert pause.message is not None
        assert pause.message.text == "Garden saved"

    def test_evaluate_from_the_pause_menu_replaces_it_with_the_evaluation(
        self, scene: GardenScene
    ) -> None:
        scene._open_pause()
        pause = scene.container.get(SceneManager).current_scene

        pause._evaluate(None)

        assert isinstance(
            scene.container.get(SceneManager).current_scene, EvaluationScene
        )

    def test_save_and_quit_returns_to_the_title_having_saved(
        self, scene: GardenScene
    ) -> None:
        self._title(scene)
        storage = _persistence(scene).storage
        for key in storage.list_keys():
            storage.delete(key)
        scene._open_pause()

        scene._quit_to_title()

        assert isinstance(scene.container.get(SceneManager).current_scene, TitleScene)
        assert SAVE_KEY in storage.list_keys()


class TestTheCalendar:
    """There is no clock any more: a day ends when the player sleeps."""

    def test_the_readout_counts_days_of_the_session(self) -> None:
        assert clock.format_day(1) == f"Dia 1 / {SESSION_DAYS}"
        assert clock.format_day(SESSION_DAYS) == f"Dia {SESSION_DAYS} / {SESSION_DAYS}"

    def test_days_left_never_goes_negative(self) -> None:
        assert clock.days_left(1) == SESSION_DAYS - 1
        assert clock.days_left(SESSION_DAYS) == 0
        assert clock.days_left(SESSION_DAYS + 5) == 0

    def test_nothing_moves_the_day_but_sleeping(self, scene: GardenScene) -> None:
        for _ in range(120):
            scene.update(1 / 60)
        assert scene.turn.day == 1

        scene.end_day()

        assert scene.turn.day == 2

    def test_a_night_restores_the_pool(self, scene: GardenScene) -> None:
        scene.turn.stamina = 1

        scene.end_day()

        assert scene.turn.stamina == scene.turn.max_stamina


class TestTheHud:
    def test_it_shows_the_day_and_the_power_budget(self, scene: GardenScene) -> None:
        scene.turn = DayCycle(day=2, stamina=5)
        scene.update(1 / 60)
        assert scene._hud is not None
        assert scene._hud.day_label.text == f"Dia 2 / {SESSION_DAYS}"
        assert scene._hud.resources.power == (0, 0)

        scene.economy.inventory["solar_panel"] = 1
        structures.place_structure(
            scene.grid, scene.entity_manager, scene.economy, "solar_panel", (0, 0)
        )
        scene.economy.inventory["drip_irrigation"] = 1
        structures.place_structure(
            scene.grid, scene.entity_manager, scene.economy, "drip_irrigation", (2, 0)
        )
        _resolve(scene, SUB_STEP)
        scene.update(1 / 60)

        assert scene._hud.resources.power == (1, 3)

    def test_the_inspector_prompts_until_something_is_hovered(
        self, scene: GardenScene
    ) -> None:
        scene.update(1 / 60)

        assert scene._inspector is not None
        assert "Hover" in scene._inspector.title.text

    def test_a_real_mouse_move_sets_the_hovered_cell(self, scene: GardenScene) -> None:
        assert scene._canvas is not None
        canvas = scene._canvas
        x = canvas.rect.x + 3 * 48 + 10
        y = canvas.rect.y + 2 * 48 + 10

        scene.container.get(InputManager).process_event(
            MouseMotionEvent(x=x, y=y, rel_x=1, rel_y=1)
        )

        assert canvas.hover_cell == (3, 2)

    def test_leaving_the_plot_keeps_the_last_hovered_cell(
        self, scene: GardenScene
    ) -> None:
        assert scene._canvas is not None
        canvas = scene._canvas
        canvas._process_input(
            UIEventType.MOUSE_MOVE,
            Vector2(canvas.rect.x + 5, canvas.rect.y + 5),
            0,
        )
        canvas._process_input(UIEventType.MOUSE_MOVE, Vector2(2, 2), 0)

        assert canvas.hover_cell == (0, 0)

    def test_the_inspector_describes_the_soil_and_plant_under_the_cursor(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (3, 2), "baru", stage="mature")
        scene.grid.soil_at((3, 2)).moisture = 0.5
        scene.grid.soil_at((3, 2)).pest_pressure = 0.25
        assert scene._canvas is not None
        scene._canvas.hover_cell = (3, 2)

        scene.update(1 / 60)

        assert scene._inspector is not None
        # The title carries the tile; the plant sits on its own line under
        # the portrait.
        assert "Tilled soil" in scene._inspector.title.text
        assert "Baru" in scene._inspector.panel.detail
        assert "mature" in scene._inspector.panel.detail
        assert scene._inspector.panel.plant is not None
        assert scene._inspector.bars["moisture"].value == pytest.approx(0.5, abs=0.02)
        assert scene._inspector.bars["pest_pressure"].value == pytest.approx(0.25)

    def test_clicking_a_tile_points_the_inspector_at_it(
        self, scene: GardenScene
    ) -> None:
        assert scene._canvas is not None
        canvas = scene._canvas

        canvas._process_input(
            UIEventType.MOUSE_DOWN,
            Vector2(canvas.rect.x + 5 * 48 + 4, canvas.rect.y + 3 * 48 + 4),
            1,
        )

        assert canvas.hover_cell == (5, 3)

    def test_the_inspector_names_a_structure(self, scene: GardenScene) -> None:
        scene.economy.inventory["solar_panel"] = 1
        structures.place_structure(
            scene.grid, scene.entity_manager, scene.economy, "solar_panel", (4, 4)
        )
        assert scene._canvas is not None
        scene._canvas.hover_cell = (4, 4)

        scene.update(1 / 60)

        assert scene._inspector is not None
        assert "Solar Micro-Panel" in scene._inspector.panel.detail

    def test_the_plot_is_not_dimmed_by_a_clock_any_more(
        self, scene: GardenScene
    ) -> None:
        """Night is something the player chooses by sleeping, not a wash
        that creeps over the plot while they read it."""
        assert scene._canvas is not None

        for _ in range(120):
            scene.update(1 / 60)

        assert scene._canvas.darkness == 0.0
