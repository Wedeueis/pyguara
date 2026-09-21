"""GardenGrid: one plot's terrain, soil chemistry, and what is planted where.

Composes a `Tilemap` (via `level_builder`) with a parallel `SoilCell` grid
and entity-id occupancy maps -- see `components.py`'s module docstring for
why soil chemistry stays outside the ECS while plants and automation
structures are real entities.
"""

from __future__ import annotations

from games.quintal_cerrado.components import SoilCell, till_cell, water_cell
from games.quintal_cerrado.level_builder import TILLED_GID, build_tilemap
from pyguara.common.grid import Cell, cell_to_world
from pyguara.common.types import Vector2
from pyguara.tilemap.layer import EMPTY_GID
from pyguara.tilemap.tilemap import Tilemap

GRID_WIDTH = 12
GRID_HEIGHT = 8
TILE_SIZE = 48


class GardenGrid:
    """The plot's terrain, soil state, and occupancy."""

    def __init__(self) -> None:
        """Build a fresh, barren plot."""
        self.tilemap: Tilemap = build_tilemap(GRID_WIDTH, GRID_HEIGHT, TILE_SIZE)
        self.soil: list[list[SoilCell]] = [
            [SoilCell() for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)
        ]
        # Cell -> entity id. The tile a plant/structure occupies on
        # `flora`/`automation` is a redundant occupancy marker for O(1)
        # neighbour scans; this dict is where the entity itself is found.
        self.plant_at: dict[Cell, str] = {}
        self.automation_at: dict[Cell, str] = {}

    def in_bounds(self, cell: Cell) -> bool:
        """Report whether `cell` falls inside the plot."""
        x, y = cell
        return 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT

    def soil_at(self, cell: Cell) -> SoilCell:
        """The `SoilCell` at `cell`.

        Args:
            cell: A cell already confirmed `in_bounds` -- this does not
                check bounds itself.
        """
        x, y = cell
        return self.soil[y][x]

    def cell_center_world(self, cell: Cell) -> Vector2:
        """The world-space centre of `cell`, for placing a planted entity."""
        return cell_to_world(cell, TILE_SIZE)

    def till(self, cell: Cell) -> bool:
        """Till a raw-dirt cell to tilled dirt.

        Args:
            cell: The cell to till.

        Returns:
            Whether tilling changed anything -- out of bounds or already
            tilled/occupied both report False rather than raising, since a
            click landing on either is an ordinary outcome, not an error.
        """
        if not self.in_bounds(cell):
            return False
        if not till_cell(self.soil_at(cell)):
            return False
        self.tilemap.layers["terrain"].set_tile(cell, TILLED_GID)
        return True

    def water(self, cell: Cell) -> bool:
        """Raise a cell's moisture.

        Works regardless of `soil_type` -- raw dirt takes water same as
        tilled ground -- there's no reason to gate this the way `till`/
        `can_plant` gate on being tilled.

        Args:
            cell: The cell to water.

        Returns:
            Whether watering changed anything -- out of bounds or already
            saturated both report False rather than raising.
        """
        if not self.in_bounds(cell):
            return False
        return water_cell(self.soil_at(cell))

    def can_plant(self, cell: Cell) -> bool:
        """Report whether `cell` is tilled, in bounds, and unoccupied.

        A structure occupies its cell too -- nothing grows under a solar
        panel.
        """
        if (
            not self.in_bounds(cell)
            or cell in self.plant_at
            or cell in self.automation_at
        ):
            return False
        return self.soil_at(cell).soil_type == "tilled_dirt"

    def mark_planted(self, cell: Cell, entity_id: str) -> None:
        """Record that `entity_id` now occupies `cell`.

        Args:
            cell: A cell already confirmed `can_plant`.
            entity_id: The planted entity's id.
        """
        self.plant_at[cell] = entity_id
        self.tilemap.layers["flora"].set_tile(cell, 1)

    def unmark_planted(self, cell: Cell) -> None:
        """Clear `cell`'s occupancy after a harvest.

        Leaves the underlying soil tilled -- a harvested plot is ready to
        replant immediately, matching the till → seed → water → grow →
        harvest loop's own rhythm rather than forcing a re-till first.

        Args:
            cell: A cell that was `plant_at`.
        """
        self.plant_at.pop(cell, None)
        self.tilemap.layers["flora"].set_tile(cell, EMPTY_GID)

    def can_build(self, cell: Cell) -> bool:
        """Report whether a structure can go on `cell`.

        Any in-bounds cell with nothing on it: a structure does not need
        tilled soil, but it does not share a cell with a plant or another
        structure.
        """
        return (
            self.in_bounds(cell)
            and cell not in self.plant_at
            and cell not in self.automation_at
        )

    def mark_built(self, cell: Cell, entity_id: str) -> None:
        """Record that the structure `entity_id` now occupies `cell`.

        Args:
            cell: A cell already confirmed `can_build`.
            entity_id: The structure entity's id.
        """
        self.automation_at[cell] = entity_id
        self.tilemap.layers["automation"].set_tile(cell, 1)
