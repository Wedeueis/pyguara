"""`GardenGrid`/`level_builder` logic, headless.

No UI or DI needed: this only exercises `games.quintal_cerrado`'s own use
of `pyguara.tilemap` (tilling a cell, marking it occupied), not the
tilemap package's own behaviour -- `tests/test_tilemap.py` and
`test_tiled_loader.py` already cover that.
"""

from __future__ import annotations

from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.level_builder import RAW_DIRT_GID, TILLED_GID


def test_till_flips_terrain_gid_and_soil_type() -> None:
    grid = GardenGrid()
    cell = (2, 3)

    assert grid.till(cell) is True
    assert grid.soil_at(cell).soil_type == "tilled_dirt"
    assert grid.tilemap.layers["terrain"].get_tile(cell) == TILLED_GID


def test_till_is_a_noop_on_already_tilled_ground() -> None:
    grid = GardenGrid()
    cell = (0, 0)
    grid.till(cell)

    assert grid.till(cell) is False
    assert grid.soil_at(cell).soil_type == "tilled_dirt"


def test_till_out_of_bounds_reports_false_rather_than_raising() -> None:
    grid = GardenGrid()

    assert grid.till((-1, 0)) is False
    assert grid.till((0, 999)) is False


def test_untilled_ground_starts_as_raw_dirt() -> None:
    grid = GardenGrid()
    cell = (5, 5)

    assert grid.soil_at(cell).soil_type == "raw_dirt"
    assert grid.tilemap.layers["terrain"].get_tile(cell) == RAW_DIRT_GID


def test_can_plant_requires_tilled_ground() -> None:
    grid = GardenGrid()
    cell = (1, 1)

    assert grid.can_plant(cell) is False
    grid.till(cell)
    assert grid.can_plant(cell) is True


def test_can_plant_is_false_once_occupied() -> None:
    grid = GardenGrid()
    cell = (1, 1)
    grid.till(cell)
    grid.mark_planted(cell, "plant-entity-id")

    assert grid.can_plant(cell) is False


def test_mark_planted_records_occupancy_and_flora_gid() -> None:
    grid = GardenGrid()
    cell = (4, 2)
    grid.till(cell)

    grid.mark_planted(cell, "plant-entity-id")

    assert grid.plant_at[cell] == "plant-entity-id"
    assert grid.tilemap.layers["flora"].get_tile(cell) != 0
