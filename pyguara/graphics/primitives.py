"""Many rectangles, circles or lines, drawn from arrays in one call.

Each row of an array draws exactly what the matching `draw_rect`,
`draw_circle` or `draw_line` call would, truncation to whole pixels
included. On a `PrimitiveArrayRenderer` the array crosses to the GPU in
one call; on any other renderer the rows are drawn one call at a time.
Colours are 0 to 255, coordinates are screen pixels, values are read as
float32, and an outline of 0 fills. The columns are in the example.

Example:
    # rects:   x, y, width, height, red, green, blue, alpha, outline
    # circles: x, y, radius, outline, red, green, blue, alpha
    # lines:   start_x, start_y, end_x, end_y, width, red, green, blue, alpha
    rows = numpy.zeros((len(enemies), 9), dtype=numpy.float32)
    rows[:, 0:2] = positions
    rows[:, 2:4] = (8, 8)
    rows[:, 4:8] = (220, 40, 40, 255)
    primitives.draw_rects(renderer, rows)
"""

from __future__ import annotations

from typing import Any

import numpy as np

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import PrimitiveArrayRenderer

RECT_COLUMNS = 9
CIRCLE_COLUMNS = 8
LINE_COLUMNS = 9


def as_rows(rows: Any, columns: int) -> np.ndarray[Any, np.dtype[np.float32]]:
    """Return `rows` as a contiguous little-endian float32 array.

    Args:
        rows: Anything `numpy.asarray` accepts, one row per primitive.
        columns: How many columns a row has.

    Returns:
        A `(count, columns)` array. An empty input gives `(0, columns)`.

    Raises:
        ValueError: If the rows do not have `columns` columns.
    """
    array = np.ascontiguousarray(rows, dtype="<f4")
    if array.size == 0:
        return np.zeros((0, columns), dtype="<f4")
    if array.ndim != 2 or array.shape[1] != columns:
        raise ValueError(
            f"expected rows of {columns} columns, got an array of shape {array.shape}"
        )
    return array


def draw_rects(renderer: Any, rows: Any) -> None:
    """Draw one rectangle per row; see the module docstring for the columns."""
    if isinstance(renderer, PrimitiveArrayRenderer):
        renderer.draw_rects(rows)
        return
    for x, y, width, height, red, green, blue, alpha, outline in as_rows(
        rows, RECT_COLUMNS
    ).tolist():
        renderer.draw_rect(
            Rect(x, y, width, height),
            Color(int(red), int(green), int(blue), int(alpha)),
            int(outline),
        )


def draw_circles(renderer: Any, rows: Any) -> None:
    """Draw one circle per row; see the module docstring for the columns."""
    if isinstance(renderer, PrimitiveArrayRenderer):
        renderer.draw_circles(rows)
        return
    for x, y, radius, outline, red, green, blue, alpha in as_rows(
        rows, CIRCLE_COLUMNS
    ).tolist():
        renderer.draw_circle(
            Vector2(x, y),
            radius,
            Color(int(red), int(green), int(blue), int(alpha)),
            int(outline),
        )


def draw_lines(renderer: Any, rows: Any) -> None:
    """Draw one line per row; see the module docstring for the columns."""
    if isinstance(renderer, PrimitiveArrayRenderer):
        renderer.draw_lines(rows)
        return
    for start_x, start_y, end_x, end_y, width, red, green, blue, alpha in as_rows(
        rows, LINE_COLUMNS
    ).tolist():
        renderer.draw_line(
            Vector2(start_x, start_y),
            Vector2(end_x, end_y),
            Color(int(red), int(green), int(blue), int(alpha)),
            int(width),
        )
