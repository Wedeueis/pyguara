"""GardenGridCanvas: the plot's own drawing surface, click input and juice.

A deliberate, novel combination: no existing capstone clicks on *world*
content through the UI system. `pyguara.ui.components.canvas.Canvas`
exists for exactly this ("a mini-map, a model preview, a custom graph"),
and `UIManager` already routes every mouse event to whichever widget is
under the cursor via `_process_input` -- so the grid gets working,
focus-stack-aware mouse input for free by being a `Canvas` subclass,
instead of adding a second, unexercised raw-`InputManager` mouse path.
`Slider._process_input` is the closest existing precedent for the pattern,
not an exact one: nothing else turns a click into *game* state this way.

Also owns the plot's visual feedback: a `juice.Motes` particle burst on
tilling, watering, harvesting, and every plant stage change (including the
first, "just planted" one), a brief overshoot-scale pop on a stage change,
a slow idle sway so a mature plot doesn't read as a field of static
stickers, and a moisture tint on the soil itself so watering is something
a player can see, not just a number gating growth off-screen. A static
grid of coloured circles would prove the simulation runs; it wouldn't read
as *alive* the way every other capstone's world does.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from games.quintal_cerrado import art
from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import (
    GRID_HEIGHT,
    GRID_WIDTH,
    TILE_SIZE,
    GardenGrid,
)
from games.quintal_cerrado.juice import FloatingLabels, Motes
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.common.grid import Cell, cell_to_world, neighbors8
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.canvas import Canvas
from pyguara.ui.types import UIEventType

TILL_DUST = Color(196, 158, 110)
WATER_DROPLET = Color(120, 180, 200)
HARVEST_GOLD = Color(240, 210, 130)
COMPOST_COLOR = Color(126, 150, 88)
SPRAY_COLOR = Color(214, 226, 170)
PEST_BURST = Color(120, 76, 158)
WILT_BURST = Color(140, 128, 112)
GAIN_COLOR = Color(255, 226, 140)
WARN_COLOR = Color(236, 120, 96)

ALERT_COLOR = (190, 50, 50)
ALERT_MAX_ALPHA = 95
ALERT_DECAY = 1.3
"""Per-second decay of the outbreak alert flash; ~0.75s to clear."""

SWAY_SPEED = 1.6
"""Radians per second the idle sway's sine advances at."""

SWAY_AMPLITUDE = 1.6
"""Peak sway offset in pixels -- a breath, not a wobble."""

POP_DECAY = 2.4
"""Per-second decay rate of a plant's pop bounce; ~0.4s to settle."""


@dataclass
class _PlantVisual:
    """Per-plant animation state, keyed by entity id.

    Owned by the canvas, not `PlantComponent` -- this is pure presentation
    (how a stage change *reads*), not simulation state the save schema or
    any system needs, so it stays out of the data-only component.
    """

    known_stage: str
    pop: float = 1.0
    sway_seed: float = 0.0


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
        self._motes = Motes()
        self._labels = FloatingLabels()
        self._visuals: dict[str, _PlantVisual] = {}
        self._elapsed = 0.0
        self._alert = 0.0

    def _cell_at(self, position: Vector2) -> Cell | None:
        """The cell under a screen-space `position`, or None off-grid."""
        local_x = position.x - self.rect.x
        local_y = position.y - self.rect.y
        if local_x < 0 or local_y < 0:
            return None
        cell = (int(local_x // TILE_SIZE), int(local_y // TILE_SIZE))
        return cell if self.grid.in_bounds(cell) else None

    def _cell_screen_center(self, cell: Cell) -> Vector2:
        """The screen-space centre of `cell`."""
        local_center = cell_to_world(cell, TILE_SIZE)
        return Vector2(self.rect.x + local_center.x, self.rect.y + local_center.y)

    def celebrate_till(self, cell: Cell) -> None:
        """Kick up a puff of dust -- call right after a successful till.

        Args:
            cell: The cell that was just tilled.
        """
        self._motes.burst(
            self._cell_screen_center(cell), TILL_DUST, count=7, speed=35.0, life=0.4
        )

    def celebrate_water(self, cell: Cell) -> None:
        """Splash a few droplets -- call right after a successful watering.

        Args:
            cell: The cell that was just watered.
        """
        self._motes.burst(
            self._cell_screen_center(cell), WATER_DROPLET, count=6, speed=25.0, life=0.5
        )

    def celebrate_harvest(self, cell: Cell, species_id: str) -> None:
        """Burst the species' colour plus a gold accent -- the loop's payoff.

        A bigger, two-colour beat than a stage change's burst: harvesting
        is the moment the loop closes and the cell is free again, and
        should read as more rewarding than "the plant grew a bit".

        Args:
            cell: The cell that was just harvested.
            species_id: The harvested plant's species, for its colour.
        """
        species = SPECIES_TABLE.get(species_id)
        color = species.color if species is not None else Color.WHITE
        center = self._cell_screen_center(cell)
        self._motes.burst(center, color, count=16, speed=70.0, life=0.7)
        self._motes.burst(center, HARVEST_GOLD, count=8, speed=90.0, life=0.5)

    def celebrate_compost(self, cell: Cell) -> None:
        """Turn over some rich earth -- call right after a successful compost.

        Args:
            cell: The cell that was just composted.
        """
        self._motes.burst(
            self._cell_screen_center(cell), COMPOST_COLOR, count=9, speed=30.0, life=0.6
        )

    def celebrate_spray(self, cell: Cell) -> None:
        """Puff a pale chemical cloud over the cell and its eight neighbours.

        Args:
            cell: The centre of the spray.
        """
        for target in [cell, *neighbors8(cell)]:
            if self.grid.in_bounds(target):
                self._motes.burst(
                    self._cell_screen_center(target),
                    SPRAY_COLOR,
                    count=5,
                    speed=28.0,
                    life=0.7,
                    radius=4.0,
                )

    def spawn_label(self, cell: Cell, text: str, color: Color) -> None:
        """Float a short piece of text up from a cell: "+16", "Need 15".

        Args:
            cell: The cell it rises from.
            text: What to show.
            color: Its colour; it fades out as it rises.
        """
        self._labels.spawn(
            text, self._cell_screen_center(cell) - Vector2(10, 14), color
        )

    def flash_alert(self) -> None:
        """Wash the plot red for a moment -- an outbreak just began."""
        self._alert = 1.0

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

    def update(self, dt: float) -> None:
        """Advance particles and every planted entity's pop/sway animation."""
        super().update(dt)
        self._elapsed += dt
        self._motes.update(dt)
        self._labels.update(dt)
        self._alert = max(0.0, self._alert - dt * ALERT_DECAY)
        self._update_plant_visuals(dt)

    def _update_plant_visuals(self, dt: float) -> None:
        live_ids: set[str] = set()
        for cell, entity_id in self.grid.plant_at.items():
            live_ids.add(entity_id)
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None or not entity.has_component(PlantComponent):
                continue
            plant = entity.get_component(PlantComponent)

            visual = self._visuals.get(entity_id)
            if visual is None:
                # First frame this entity has been seen -- treat it the
                # same as a stage change: a pop and a burst, so planting
                # itself reads as an event and not just a shape appearing.
                visual = _PlantVisual(
                    known_stage=plant.growth_stage,
                    sway_seed=hash(entity_id) % 100 / 16.0,
                )
                self._visuals[entity_id] = visual
                self._celebrate_stage(cell, plant.species_id, plant.growth_stage)
                continue

            if plant.growth_stage != visual.known_stage:
                visual.known_stage = plant.growth_stage
                visual.pop = 1.0
                self._celebrate_stage(cell, plant.species_id, plant.growth_stage)
            elif visual.pop > 0.0:
                visual.pop = max(0.0, visual.pop - dt * POP_DECAY)

        # Drop tracking for anything no longer planted -- nothing removes a
        # plant yet in this phase, but a future harvest/death should not
        # leak an animation state entry forever.
        for stale_id in set(self._visuals) - live_ids:
            del self._visuals[stale_id]

    def _celebrate_stage(self, cell: Cell, species_id: str, stage: str) -> None:
        """Burst on a stage change -- in the pest's colour if it is bad news."""
        species = SPECIES_TABLE.get(species_id)
        color = species.color if species is not None else Color.WHITE
        if stage == "infested":
            color = PEST_BURST
        elif stage == "dying":
            color = WILT_BURST
        self._motes.burst(
            self._cell_screen_center(cell), color, count=10, speed=45.0, life=0.55
        )

    def render(self, renderer: UIRenderer) -> None:
        """Draw every soil cell, then whatever occupies it, then particles."""
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
                soil = self.grid.soil_at((x, y))
                art.draw_soil_tile(
                    renderer,
                    rect,
                    kind,
                    moisture=soil.moisture,
                    degraded=soil.is_chemically_degraded,
                )
                if soil.pest_pressure > 0.05:
                    art.draw_pest_marks(
                        renderer, rect, soil.pest_pressure, self._elapsed
                    )

        self._draw_plants(renderer)
        self._motes.render(renderer)
        self._labels.render(renderer)
        if self._alert > 0.0:
            renderer.draw_rect(
                self.rect, Color(*ALERT_COLOR, int(ALERT_MAX_ALPHA * self._alert))
            )

        for child in self.children:
            if child.visible:
                child.render(renderer)

    def _draw_plants(self, renderer: UIRenderer) -> None:
        """Draw every planted cell's plant, at its current growth stage.

        Reads each occupant's `PlantComponent` fresh rather than caching a
        colour on the tile -- the `flora` layer only marks a cell occupied
        (see `garden_grid.py`'s module docstring), never what is growing
        there.
        """
        for cell, entity_id in self.grid.plant_at.items():
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None or not entity.has_component(PlantComponent):
                continue
            plant = entity.get_component(PlantComponent)
            species = SPECIES_TABLE.get(plant.species_id)
            if species is None:
                continue

            visual = self._visuals.get(entity_id)
            pop = visual.pop if visual is not None else 0.0
            sway = 0.0
            if visual is not None:
                sway = (
                    math.sin(self._elapsed * SWAY_SPEED + visual.sway_seed)
                    * SWAY_AMPLITUDE
                )

            art.draw_plant(
                renderer,
                self._cell_screen_center(cell),
                species.color,
                plant.growth_stage,
                pop=pop,
                sway=sway,
                elapsed=self._elapsed,
            )
