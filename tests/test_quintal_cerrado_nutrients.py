# ruff: noqa: F811  - pytest fixtures are imported by name from the growth suite
"""Soil nutrients: four levers, each owning one effect, pulling on each other.

The design rule these tests defend is that a nutrient earns its place by
governing something nothing else governs -- and that nitrogen, the obvious
lever, brings the problem calcium answers.
"""

from __future__ import annotations

import pytest

from games.quintal_cerrado import nutrients
from games.quintal_cerrado.components import PlantComponent, SoilCell, compost_cell
from games.quintal_cerrado.economy import sale_value
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.scenes import GardenScene
from games.quintal_cerrado.systems.nutrient_system import (
    NutrientSystem,
)
from tests.test_quintal_cerrado_growth import (  # noqa: F401
    _nights,
    _plant_at,
    _resolve,
    game_container,
    scene,
)


def _rich(**levels: float) -> SoilCell:
    soil = SoilCell()
    for key, value in levels.items():
        setattr(soil, key, value)
    return soil


class TestEachNutrientOwnsOneEffect:
    """MECE: add a fifth only when it governs something none of these do."""

    def test_nitrogen_grows_faster(self) -> None:
        poor = nutrients.growth_multiplier(_rich(nitrogen=0.0))
        fed = nutrients.growth_multiplier(_rich(nitrogen=1.0))

        assert fed > poor == 1.0

    def test_phosphorus_makes_the_harvest_worth_more(self) -> None:
        plant = PlantComponent(species_id="baru")

        plain = sale_value(plant, _rich(phosphorus=0.0))
        fed = sale_value(plant, _rich(phosphorus=1.0))

        assert fed > plain
        assert sale_value(plant) == plain, "no soil means no bonus, not a crash"

    def test_potassium_hardens_against_cold_and_drought(self) -> None:
        assert nutrients.hardiness(_rich(potassium=0.0)) == 0.0
        assert nutrients.hardiness(_rich(potassium=1.0)) > 0.0

    def test_calcium_turns_pests_away(self) -> None:
        bare = nutrients.pest_susceptibility(_rich())
        guarded = nutrients.pest_susceptibility(_rich(calcium=1.0))

        assert guarded < bare

    def test_nitrogen_draws_the_pests_calcium_answers(self) -> None:
        """The tension the whole system is built around."""
        fed = nutrients.pest_susceptibility(_rich(nitrogen=1.0))
        bare = nutrients.pest_susceptibility(_rich())
        both = nutrients.pest_susceptibility(_rich(nitrogen=1.0, calcium=1.0))

        assert fed > bare, "the obvious lever costs something"
        assert both < fed, "and calcium is what pays it"

    def test_nothing_else_changes_when_one_nutrient_moves(self) -> None:
        """Each lever moves its own effect and no other."""
        base = _rich()
        nitrogen = _rich(nitrogen=1.0)

        assert nutrients.value_multiplier(nitrogen) == nutrients.value_multiplier(base)
        assert nutrients.hardiness(nitrogen) == nutrients.hardiness(base)


class TestTheSoilReadout:
    """One reading and one word, never four numbers."""

    def test_vitality_rises_as_the_ground_is_fed(self) -> None:
        assert nutrients.vitality(_rich()) < nutrients.vitality(
            _rich(nitrogen=1.0, phosphorus=1.0, potassium=1.0, calcium=1.0)
        )

    def test_it_names_the_scarcest_nutrient(self) -> None:
        soil = _rich(nitrogen=0.9, phosphorus=0.05, potassium=0.9, calcium=0.9)

        short = nutrients.scarcest(soil)

        assert short is not None and short.short == "P"

    def test_well_fed_ground_has_nothing_to_name(self) -> None:
        assert (
            nutrients.scarcest(_rich(**dict.fromkeys(nutrients.NUTRIENTS, 0.8))) is None
        )


class TestWhatGrowingCosts:
    """Plants feed, and the grown ones give back."""

    def _system(self, scene: GardenScene) -> NutrientSystem:
        return NutrientSystem(scene.entity_manager, scene.grid)

    def test_a_growing_plant_draws_on_its_cell(self, scene: GardenScene) -> None:
        _plant_at(scene, (3, 3), "cagaita", stage="growing")
        before = scene.grid.soil_at((3, 3)).nitrogen

        self._system(scene).resolve_night()

        assert scene.grid.soil_at((3, 3)).nitrogen < before

    def test_a_bigger_plant_eats_more(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "guandu", stage="growing")
        _plant_at(scene, (6, 6), "baru", stage="growing")

        self._system(scene).resolve_night()

        light = 1.0 - scene.grid.soil_at((2, 2)).nitrogen / SoilCell().nitrogen
        heavy = 1.0 - scene.grid.soil_at((6, 6)).nitrogen / SoilCell().nitrogen
        assert heavy > light

    def test_a_legume_feeds_its_neighbours(self, scene: GardenScene) -> None:
        """Which is the whole reason to interplant one."""
        _plant_at(scene, (4, 4), "guandu", stage="mature")
        neighbour = scene.grid.soil_at((5, 4)).nitrogen

        self._system(scene).resolve_night()

        assert scene.grid.soil_at((4, 4)).nitrogen > SoilCell().nitrogen
        assert scene.grid.soil_at((5, 4)).nitrogen > neighbour

    def test_a_seedling_legume_gives_nothing_yet(self, scene: GardenScene) -> None:
        """The payoff is for leaving something standing."""
        _plant_at(scene, (4, 4), "guandu", stage="seedling")

        self._system(scene).resolve_night()

        assert scene.grid.soil_at((5, 4)).nitrogen == pytest.approx(SoilCell().nitrogen)

    @pytest.mark.parametrize(
        ("species_id", "nutrient"),
        [("guandu", "nitrogen"), ("baru", "potassium"), ("pequi", "calcium")],
    )
    def test_each_giver_gives_its_own_nutrient(
        self, scene: GardenScene, species_id: str, nutrient: str
    ) -> None:
        _plant_at(scene, (5, 5), species_id, stage="mature")

        self._system(scene).resolve_night()

        assert getattr(scene.grid.soil_at((5, 5)), nutrient) > SoilCell().nitrogen

    def test_compost_feeds_what_the_plants_took(self) -> None:
        soil = SoilCell(soil_type="tilled_dirt", nitrogen=0.0, phosphorus=0.0)

        assert compost_cell(soil)

        assert soil.nitrogen > 0.0 and soil.phosphorus > 0.0


class TestItShowsUpInPlay:
    """The levers reach the simulation, not just their own module."""

    def test_a_worked_bed_runs_down_over_nights(self, scene: GardenScene) -> None:
        _plant_at(scene, (3, 3), "baru", stage="growing")
        scene.grid.water((3, 3))
        before = nutrients.vitality(scene.grid.soil_at((3, 3)))

        _nights(scene, 2)

        assert nutrients.vitality(scene.grid.soil_at((3, 3))) < before

    def test_nitrogen_rich_ground_grows_a_plant_faster(
        self, scene: GardenScene
    ) -> None:
        for cell, nitrogen in (((2, 2), 0.0), ((8, 2), 1.0)):
            _plant_at(scene, cell, "cagaita", stage="growing")
            scene.grid.soil_at(cell).nitrogen = nitrogen
            scene.grid.water(cell)

        _resolve(scene, 0.25)

        plants = {
            cell: scene.entity_manager.get_entity(
                scene.grid.plant_at[cell]
            ).get_component(PlantComponent)
            for cell in ((2, 2), (8, 2))
        }
        assert plants[(8, 2)].growth_progress > plants[(2, 2)].growth_progress

    def test_the_biodiversity_guard_slows_pests_reaching_a_mixed_bed(
        self, scene: GardenScene
    ) -> None:
        """Biodiversity finally pays *during* a session, not only at the end."""
        resolver = scene._resolver
        assert resolver is not None
        for cell, species in (
            ((1, 1), "guandu"),
            ((1, 2), "cagaita"),
            ((2, 1), "baru"),
        ):
            _plant_at(scene, cell, species, stage="growing")
        mixed = resolver.pest._biodiversity_guard((2, 2))

        for cell in ((9, 1), (9, 2), (8, 1)):
            _plant_at(scene, cell, "guandu", stage="growing")
        monoculture = resolver.pest._biodiversity_guard((8, 2))

        assert mixed < monoculture


class TestTheMigration:
    """A v2 garden, saved before nutrients existed, still loads."""

    def _v2_payload(self, scene: GardenScene) -> dict:
        from games.quintal_cerrado.persistence_schema import to_save_payload

        payload = to_save_payload(
            scene.grid,
            scene.entity_manager,
            scene.economy,
            scene.conditions,
            scene.turn,
        )
        payload["version"] = 2
        for record in payload["grid"]:
            for nutrient in ("phosphorus", "potassium", "calcium"):
                record.pop(nutrient)
        return payload

    def test_it_fills_in_the_nutrients_v2_never_had(self, scene: GardenScene) -> None:
        from games.quintal_cerrado.persistence_schema import (
            STARTING_NUTRIENT,
            migrate_v2_to_v3,
        )

        migrated = migrate_v2_to_v3(self._v2_payload(scene))

        assert migrated["version"] == 3
        assert all(
            record["calcium"] == STARTING_NUTRIENT for record in migrated["grid"]
        )

    def test_a_migrated_save_loads_into_a_garden(self, scene: GardenScene) -> None:
        """What #199 asked the demo set to show: the versioning story, not
        just the happy path."""
        from games.quintal_cerrado.persistence_schema import (
            STARTING_NUTRIENT,
            apply_save_payload,
            migrate_v2_to_v3,
        )

        scene.grid.till((2, 2))
        payload = migrate_v2_to_v3(self._v2_payload(scene))
        fresh_grid = GardenGrid()

        turn, _weather = apply_save_payload(
            payload,
            fresh_grid,
            scene.entity_manager,
            scene.economy,
            scene.conditions,
        )

        assert turn.day == scene.turn.day
        assert fresh_grid.soil_at((0, 0)).calcium == pytest.approx(STARTING_NUTRIENT)

    def test_the_manager_carries_an_old_save_forward(self) -> None:
        """Registered on the real `MigrationManager`, as the game wires it."""
        from games.quintal_cerrado.persistence_schema import (
            MIGRATIONS,
            SCHEMA_VERSION,
            STARTING_NUTRIENT,
        )
        from pyguara.persistence.migration import MigrationManager

        manager = MigrationManager(current_version=SCHEMA_VERSION)
        for migration in MIGRATIONS:
            manager.register(migration)

        migrated = manager.migrate({"version": 2, "grid": [{"x": 0, "y": 0}]}, 2)

        assert migrated["version"] == SCHEMA_VERSION
        assert migrated["grid"][0]["potassium"] == pytest.approx(STARTING_NUTRIENT)
