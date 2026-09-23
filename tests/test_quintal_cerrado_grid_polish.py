"""The plot's backdrop, its tile depth, and the tool-aware cursor."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado import art
from games.quintal_cerrado.garden_grid import TILE_SIZE, GardenGrid
from games.quintal_cerrado.garden_widget import (
    CURSOR_BLOCKED,
    CURSOR_OK,
    GardenGridCanvas,
)
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import IRenderer
from pyguara.ui.types import UIEventType


def _renderer() -> Any:
    return MagicMock(spec=IRenderer)


def _rects(renderer: Any) -> list[tuple[Rect, Color]]:
    return [
        (call.args[0], call.args[1])
        for call in renderer.draw_rect.call_args_list
        if isinstance(call.args[0], Rect) and isinstance(call.args[1], Color)
    ]


class TestTheBackdrop:
    """Warm earth with a fixed speckle, behind everything."""

    def test_it_covers_the_screen_before_anything_else(self) -> None:
        renderer = _renderer()

        art.draw_backdrop(renderer, 960, 640)

        first_rect, first_color = _rects(renderer)[0]
        assert (first_rect.width, first_rect.height) == (960, 640)
        assert first_color == art.WORLD_BACKDROP

    def test_the_speckle_is_the_same_grain_every_run(self) -> None:
        """Texture, not an event: a backdrop that reshuffled each launch
        would read as noise."""
        first, second = _renderer(), _renderer()

        art.draw_backdrop(first, 960, 640)
        art.draw_backdrop(second, 960, 640)

        assert _rects(first) == _rects(second)

    def test_every_fleck_lands_on_screen(self) -> None:
        renderer = _renderer()

        art.draw_backdrop(renderer, 960, 640)

        for rect, _color in _rects(renderer)[1:]:
            assert 0 <= rect.x <= 960 and 0 <= rect.y <= 640


class TestTileDepth:
    """Worked ground sits into the plot; raw ground stands proud of it."""

    def _edges(self, kind: str) -> list[Color]:
        renderer = _renderer()
        art.draw_soil_tile(renderer, Rect(0, 0, TILE_SIZE, TILE_SIZE), kind)
        return [call.args[2] for call in renderer.draw_line.call_args_list]

    def test_a_tile_is_bevelled_on_all_four_sides(self) -> None:
        """Only top and bottom read as stripes, not as tiles."""
        assert len(self._edges("raw_dirt")) == 4

    def test_tilled_soil_inverts_the_bevel(self) -> None:
        raw_top = self._edges("raw_dirt")[0]
        tilled_top = self._edges("tilled_dirt")[0]

        assert raw_top != tilled_top, "raw is lit on top, tilled is shaded"

    def test_the_grid_line_is_mixed_towards_the_tile(self) -> None:
        """The full-strength wire cut the plot into 96 loud boxes."""
        renderer = _renderer()

        art.draw_soil_tile(renderer, Rect(0, 0, TILE_SIZE, TILE_SIZE), "raw_dirt")

        outlines = [
            call.args[1]
            for call in renderer.draw_rect.call_args_list
            if call.kwargs.get("width") == 1
        ]
        assert outlines == [art.RAW_DIRT.lerp(art.GRID_LINE, art.GRID_LINE_MIX)]


class TestTheCursor:
    """It says whether the click would land, before it is spent."""

    def _canvas(self, grid: GardenGrid | None = None) -> GardenGridCanvas:
        return GardenGridCanvas(Vector2(24, 90), grid or GardenGrid(), EntityManager())

    def _hover(self, canvas: GardenGridCanvas, cell: tuple[int, int]) -> None:
        canvas._process_input(
            UIEventType.MOUSE_MOVE,
            Vector2(
                canvas.rect.x + cell[0] * TILE_SIZE + 5,
                canvas.rect.y + cell[1] * TILE_SIZE + 5,
            ),
            0,
        )

    def _tints(self, canvas: GardenGridCanvas) -> list[Color]:
        renderer = _renderer()
        canvas.render_world(renderer)
        return [
            color
            for _rect, color in _rects(renderer)
            if (color.r, color.g, color.b)
            in {
                (CURSOR_OK.r, CURSOR_OK.g, CURSOR_OK.b),
                (CURSOR_BLOCKED.r, CURSOR_BLOCKED.g, CURSOR_BLOCKED.b),
            }
        ]

    @pytest.mark.parametrize(
        ("allows", "expected"), [(True, CURSOR_OK), (False, CURSOR_BLOCKED)]
    )
    def test_it_takes_its_colour_from_the_tool(
        self, allows: bool, expected: Color
    ) -> None:
        canvas = self._canvas()
        canvas.tool_allows = lambda _cell: allows
        self._hover(canvas, (2, 2))

        tints = self._tints(canvas)

        assert tints
        assert (tints[0].r, tints[0].g, tints[0].b) == (
            expected.r,
            expected.g,
            expected.b,
        )

    def test_it_is_translucent_so_the_soil_still_reads(self) -> None:
        canvas = self._canvas()
        canvas.tool_allows = lambda _cell: True
        self._hover(canvas, (2, 2))

        assert self._tints(canvas)[0].a < 80

    def test_no_tint_without_a_validator(self) -> None:
        """A scene that never wires one gets a plain ring, not a crash."""
        canvas = self._canvas()
        self._hover(canvas, (2, 2))

        assert not self._tints(canvas)

    def test_nothing_is_drawn_once_the_cursor_leaves_the_plot(self) -> None:
        canvas = self._canvas()
        canvas.tool_allows = lambda _cell: True
        self._hover(canvas, (2, 2))
        assert self._tints(canvas)

        canvas._process_input(
            UIEventType.MOUSE_MOVE, Vector2(canvas.rect.x - 30, canvas.rect.y - 30), 0
        )

        assert not self._tints(canvas)
