"""The tile inspector and the in-world hover tooltip."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import TILE_SIZE, GardenGrid
from games.quintal_cerrado.garden_widget import TOOLTIP_DELAY, GardenGridCanvas
from games.quintal_cerrado.hud import LAYER_RUNGS, PEST_CALM, CellInspector, pest_color
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIEventType


@pytest.fixture
def ui() -> UIManager:
    manager = UIManager(EventDispatcher())
    manager.set_screen_size(960, 640)
    return manager


@pytest.fixture
def inspector(ui: UIManager) -> CellInspector:
    return CellInspector(ui, Vector2(600, 90), 328)


def _ui_renderer() -> Any:
    renderer = MagicMock(spec=UIRenderer)
    renderer.get_text_size.return_value = (20, 12)
    return renderer


def _canvas(grid: GardenGrid | None = None) -> GardenGridCanvas:
    return GardenGridCanvas(Vector2(24, 90), grid or GardenGrid(), EntityManager())


def _hover(canvas: GardenGridCanvas, cell: tuple[int, int] | None) -> None:
    """Move the cursor onto `cell`, or off the grid entirely."""
    position = (
        Vector2(canvas.rect.x - 40, canvas.rect.y - 40)
        if cell is None
        else Vector2(
            canvas.rect.x + cell[0] * TILE_SIZE + 5,
            canvas.rect.y + cell[1] * TILE_SIZE + 5,
        )
    )
    canvas._process_input(UIEventType.MOUSE_MOVE, position, 0)


class TestPestSeverityColour:
    """A pest gauge that never changes colour hides how bad it is."""

    @pytest.mark.parametrize(
        ("pressure", "expected"),
        [(0.0, PEST_CALM), (0.32, PEST_CALM), (0.4, "amber"), (0.7, "crimson")],
    )
    def test_the_fill_steps_through_calm_amber_and_crimson(
        self, pressure: float, expected: Any
    ) -> None:
        color = pest_color(pressure)
        if expected == "amber":
            assert color.r > 200 and color.g > 130
        elif expected == "crimson":
            assert color.r > 200 and color.g < 120
        else:
            assert color == expected

    def test_the_inspector_recolours_its_pest_bar(
        self, inspector: CellInspector
    ) -> None:
        grid, entities = GardenGrid(), EntityManager()
        grid.soil_at((1, 1)).pest_pressure = 0.8

        inspector.update(grid, entities, (1, 1))

        assert inspector.bars["pest_pressure"].fill_color == pest_color(0.8)


class TestTheInspectorCard:
    """The portrait, the detail line and the syntropic ladder."""

    def _planted(self, species_id: str, stage: str = "mature") -> tuple[Any, Any, Any]:
        grid, entities = GardenGrid(), EntityManager()
        entity = entities.create_entity()
        entity.add_component(PlantComponent(species_id=species_id, growth_stage=stage))
        grid.till((2, 2))
        grid.mark_planted((2, 2), entity.id)
        return grid, entities, entity

    def test_it_shows_the_plant_under_the_cursor(
        self, inspector: CellInspector
    ) -> None:
        grid, entities, _ = self._planted("baru")

        inspector.update(grid, entities, (2, 2))

        assert inspector.panel.plant is not None
        assert inspector.panel.plant.species_id == "baru"
        assert "Baru" in inspector.panel.detail
        assert "mature" in inspector.panel.detail

    def test_an_empty_tile_clears_the_portrait(self, inspector: CellInspector) -> None:
        grid, entities, _ = self._planted("baru")
        inspector.update(grid, entities, (2, 2))

        inspector.update(grid, entities, (5, 5))

        assert inspector.panel.plant is None
        assert inspector.panel.detail == ""

    def test_degraded_soil_is_called_out(self, inspector: CellInspector) -> None:
        grid, entities = GardenGrid(), EntityManager()
        grid.soil_at((1, 1)).is_chemically_degraded = True

        inspector.update(grid, entities, (1, 1))

        assert inspector.panel.degraded

    def test_a_sprayed_plant_says_so(self, inspector: CellInspector) -> None:
        grid, entities, entity = self._planted("guandu")
        entity.get_component(PlantComponent).is_chemical_boosted = True

        inspector.update(grid, entities, (2, 2))

        assert "pulverizado" in inspector.panel.detail

    @pytest.mark.parametrize("species_id", sorted(SPECIES_TABLE))
    def test_every_species_sits_on_one_rung_of_the_ladder(
        self, species_id: str
    ) -> None:
        """The ladder has a rung for each `Species.canopy_layer`, so no
        species can hover over a card with nothing lit."""
        layers = {layer for _name, layer in LAYER_RUNGS}

        assert SPECIES_TABLE[species_id].canopy_layer in layers

    def test_it_draws_the_whole_card(self, inspector: CellInspector) -> None:
        grid, entities, _ = self._planted("pequi", stage="harvestable")
        inspector.update(grid, entities, (2, 2))
        renderer = _ui_renderer()

        inspector.panel.render(renderer)

        assert renderer.draw_rect.called
        assert renderer.draw_circle.called, "the portrait's plant"


class TestTheHoverTooltip:
    """It follows the cursor, waits for a dwell, and leaves with it."""

    def test_it_waits_for_the_cursor_to_settle(self) -> None:
        canvas = _canvas()
        _hover(canvas, (3, 3))

        canvas.update(TOOLTIP_DELAY / 2)
        assert not canvas.tooltip_visible()

        canvas.update(TOOLTIP_DELAY)
        assert canvas.tooltip_visible()

    def test_moving_to_another_tile_restarts_the_dwell(self) -> None:
        canvas = _canvas()
        _hover(canvas, (3, 3))
        canvas.update(TOOLTIP_DELAY * 2)
        assert canvas.tooltip_visible()

        _hover(canvas, (4, 3))

        assert not canvas.tooltip_visible()

    def test_leaving_the_grid_hides_it_but_keeps_the_inspector_fed(self) -> None:
        """`hover_cell` deliberately persists for the inspector; the
        tooltip must not."""
        canvas = _canvas()
        _hover(canvas, (3, 3))
        canvas.update(TOOLTIP_DELAY * 2)

        _hover(canvas, None)
        canvas.update(TOOLTIP_DELAY * 2)

        assert not canvas.tooltip_visible()
        assert canvas.hover_cell == (3, 3)

    def test_it_draws_over_the_hovered_tile_once_visible(self) -> None:
        grid = GardenGrid()
        grid.soil_at((3, 3)).moisture = 0.6
        canvas = _canvas(grid)
        renderer = MagicMock(spec=IRenderer)
        _hover(canvas, (3, 3))
        canvas.update(TOOLTIP_DELAY * 2)

        canvas.render_world(renderer)

        tooltip_fills = [
            call.args[0]
            for call in renderer.draw_rect.call_args_list
            if isinstance(call.args[1], Color) and call.args[1].a == 232
        ]
        assert tooltip_fills, "the tooltip card was drawn"
        card = tooltip_fills[0]
        assert canvas.rect.x <= card.x
        assert card.x + card.width <= canvas.rect.right

    def test_nothing_is_drawn_before_the_dwell(self) -> None:
        canvas = _canvas()
        renderer = MagicMock(spec=IRenderer)
        _hover(canvas, (3, 3))

        canvas.render_world(renderer)

        assert not [
            call
            for call in renderer.draw_rect.call_args_list
            if isinstance(call.args[1], Color) and call.args[1].a == 232
        ]
