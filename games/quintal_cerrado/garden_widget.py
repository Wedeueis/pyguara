"""GardenGridCanvas: the plot's own drawing surface and click input.

A deliberate, novel combination: no existing capstone clicks on *world*
content through the UI system. `pyguara.ui.components.canvas.Canvas`
exists for exactly this ("a mini-map, a model preview, a custom graph"),
and `UIManager` already routes every mouse event to whichever widget is
under the cursor via `_process_input` -- so the grid gets working,
focus-stack-aware mouse input for free by being a `Canvas` subclass,
instead of adding a second, unexercised raw-`InputManager` mouse path.
`Slider._process_input` is the closest existing precedent for the pattern,
not an exact one: nothing else turns a click into *game* state this way.
"""

from __future__ import annotations

from collections.abc import Callable

from games.quintal_cerrado import art
from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import (
    GRID_HEIGHT,
    GRID_WIDTH,
    TILE_SIZE,
    GardenGrid,
)
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.common.grid import Cell, cell_to_world
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.canvas import Canvas
from pyguara.ui.types import UIEventType


class GardenGridCanvas(Canvas):
    """Draws the plot and turns a left click into a `Cell`.

    Attributes:
        on_cell_clicked: Called with the clicked cell. Set by the owning
            scene rather than passed to `__init__` -- the same
            `on_click`-after-construction pattern every stock widget uses.
    """

    def __init__(
        self, position: Vector2, grid: GardenGrid, entity_manager: EntityManager
    ) -> None:
        """Initialize the canvas over `grid`'s full pixel extent.

        Args:
            position: Top-left corner, in screen space.
            grid: The plot to draw and click into.
            entity_manager: Where planted entities live -- the canvas reads
                each occupied cell's `PlantComponent` to draw it, rather
                than the tilemap's `flora` layer keeping a second copy of
                the species/colour as tile data.
        """
        super().__init__(
            position, Vector2(GRID_WIDTH * TILE_SIZE, GRID_HEIGHT * TILE_SIZE)
        )
        self.grid = grid
        self._entity_manager = entity_manager
        self.on_cell_clicked: Callable[[Cell], None] | None = None

    def _cell_at(self, position: Vector2) -> Cell | None:
        """The cell under a screen-space `position`, or None off-grid."""
        local_x = position.x - self.rect.x
        local_y = position.y - self.rect.y
        if local_x < 0 or local_y < 0:
            return None
        cell = (int(local_x // TILE_SIZE), int(local_y // TILE_SIZE))
        return cell if self.grid.in_bounds(cell) else None

    def _process_input(
        self, event_type: UIEventType, position: Vector2, button: int
    ) -> bool:
        if event_type == UIEventType.MOUSE_DOWN and button == 1:
            cell = self._cell_at(position)
            if cell is not None:
                if self.on_cell_clicked is not None:
                    self.on_cell_clicked(cell)
                return True
        return super()._process_input(event_type, position, button)

    def render(self, renderer: UIRenderer) -> None:
        """Draw every soil cell, then whatever occupies it."""
        terrain = self.grid.tilemap.layers["terrain"]
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                gid = terrain.get_tile((x, y))
                kind = self.grid.tilemap.properties_for(gid).get("kind", "raw_dirt")
                rect = Rect(
                    self.rect.x + x * TILE_SIZE,
                    self.rect.y + y * TILE_SIZE,
                    TILE_SIZE,
                    TILE_SIZE,
                )
                art.draw_soil_tile(renderer, rect, kind)

        self._draw_plants(renderer)

        for child in self.children:
            if child.visible:
                child.render(renderer)

    def _draw_plants(self, renderer: UIRenderer) -> None:
        """Draw every planted cell's seedling.

        Reads each occupant's `PlantComponent` fresh rather than caching a
        colour on the tile -- the `flora` layer only marks a cell occupied
        (see `garden_grid.py`'s module docstring), never what is growing
        there.
        """
        for cell, entity_id in self.grid.plant_at.items():
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None or not entity.has_component(PlantComponent):
                continue
            species = SPECIES_TABLE.get(entity.get_component(PlantComponent).species_id)
            if species is None:
                continue
            local_center = cell_to_world(cell, TILE_SIZE)
            screen_center = Vector2(
                self.rect.x + local_center.x, self.rect.y + local_center.y
            )
            art.draw_seedling(renderer, screen_center, species.color)
