"""Rasterise a polygon on the CPU, by pygame's rules, without pygame.

The wgpu pipeline draws quads, and an arbitrary polygon is not one, so the
UI renderer rasterises one into a mask the size of its bounding box and
draws that once. Polygons in a UI are rare and small -- a dropdown's arrow,
a slider's notch -- so this is plain Python.

**These are pygame's rules, transcribed** from `draw.c` in pygame-ce 2.5.6:
the scanline fill (`draw_fillpoly`), including its floor-then-ceil pairing
of crossings and its second pass over flat edges; the separate triangle fill
(`draw_filltri`), with its `float` slopes; and the thick outline
(`draw_line_width`), which repeats a Bresenham line across the minor axis
rather than drawing a rotated rectangle. The pygame renderer is the
reference this backend is held to, so the same polygon covers the same
pixels on both.
"""

from __future__ import annotations

import math
import struct


class _Mask:
    """Coverage, one byte per pixel, 0 or 255."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.alpha = bytearray(width * height)

    def row(self, x1: int, y: int, x2: int) -> None:
        if not 0 <= y < self.height:
            return
        left, right = max(0, min(x1, x2)), min(self.width - 1, max(x1, x2))
        if left <= right:
            start = y * self.width
            self.alpha[start + left : start + right + 1] = b"\xff" * (right - left + 1)

    def column(self, y1: int, x: int, y2: int) -> None:
        if not 0 <= x < self.width:
            return
        for y in range(max(0, min(y1, y2)), min(self.height - 1, max(y1, y2)) + 1):
            self.alpha[y * self.width + x] = 255

    def rgba(self) -> bytes:
        """White pixels carrying the coverage in alpha."""
        out = bytearray(len(self.alpha) * 4)
        out[0::4] = out[1::4] = out[2::4] = b"\xff" * len(self.alpha)
        out[3::4] = self.alpha
        return bytes(out)


def _fill(mask: _Mask, xs: list[int], ys: list[int]) -> None:
    """Pygame's `draw_fillpoly`."""
    count = len(xs)
    top, bottom = min(ys), max(ys)
    if top == bottom:
        mask.row(min(xs), top, max(xs))
        return
    for y in range(top, bottom + 1):
        crossings: list[int] = []
        for i in range(count):
            before = i - 1 if i else count - 1
            y1, y2 = ys[before], ys[i]
            if y1 < y2:
                x1, x2 = xs[before], xs[i]
            elif y1 > y2:
                y1, y2 = ys[i], ys[before]
                x1, x2 = xs[i], xs[before]
            else:
                continue
            if (y1 <= y < y2) or (y == bottom and y2 == bottom):
                # A C float, rounded towards the inside by pairing.
                along = (y - y1) * (x2 - x1) / float(y2 - y1)
                along = (
                    math.floor(along) if len(crossings) % 2 == 0 else math.ceil(along)
                )
                crossings.append(int(along) + x1)
        crossings.sort()
        for i in range(0, len(crossings) - 1, 2):
            mask.row(crossings[i], y, crossings[i + 1])
    for i in range(count):
        before = i - 1 if i else count - 1
        y = ys[i]
        if top < y < bottom and ys[before] == y:
            mask.row(xs[i], y, xs[before])


def _f32(value: float) -> float:
    """Round to a C `float`, as pygame's triangle fill computes in."""
    rounded: float = struct.unpack("f", struct.pack("f", value))[0]
    return rounded


def _fill_triangle(mask: _Mask, xs: list[int], ys: list[int]) -> None:
    """Pygame's `draw_filltri`: three points take this path, not the scanline.

    Each edge is stepped with a slope held as a C `float` and truncated
    towards zero, which rounds differently from the scanline fill's
    floor-and-ceil pairing -- which is why it has to be its own function.
    """
    (p0x, p1x, p2x), (p0y, p1y, p2y) = xs, ys
    if p1y < p0y:
        p0x, p0y, p1x, p1y = p1x, p1y, p0x, p0y
    if p2y < p1y:
        p1x, p1y, p2x, p2y = p2x, p2y, p1x, p1y
        if p1y < p0y:
            p0x, p0y, p1x, p1y = p1x, p1y, p0x, p0y
    if p0y == p1y == p2y and p0x == p1x and p1x != p2x:
        p1x, p1y, p2x, p2y = p2x, p2y, p1x, p1y
    d1 = _f32((p2x - p0x) / ((p2y - p0y) + 1e-17))
    d2 = _f32((p1x - p0x) / ((p1y - p0y) + 1e-17))
    d3 = _f32((p2x - p1x) / ((p2y - p1y) + 1e-17))
    for y in range(p0y, p2y + 1):
        x1 = p0x + int(_f32((y - p0y) * d1))
        if y < p1y:
            x2 = p0x + int(_f32((y - p0y) * d2))
        else:
            x2 = p1x + int(_f32((y - p1y) * d3))
        mask.row(x1, y, x2)


def _line(mask: _Mask, x1: int, y1: int, x2: int, y2: int, width: int) -> None:
    """Pygame's `draw_line_width`, and `draw_line` for a width of one."""
    if width < 1:
        return
    extra = 1 - (width % 2)
    half = width // 2 if width > 1 else 0
    if width == 1:
        extra = 0
    across_x = abs(x1 - x2) <= abs(y1 - y2)
    if x1 == x2 and y1 == y2:
        mask.row(x1 - half + extra, y1, x1 + half)
        return
    dx, dy = abs(x2 - x1), abs(y2 - y1)
    sx = 1 if x2 > x1 else -1
    sy = 1 if y2 > y1 else -1
    # C's `/` truncates towards zero; Python's `//` floors.
    err = int((dx if dx > dy else -dy) / 2)
    if across_x:
        while y1 != y2 + sy:
            mask.row(x1 - half + extra, y1, x1 + half)
            e2 = err
            if e2 > -dx:
                err -= dy
                x1 += sx
            if e2 < dy:
                err += dx
                y1 += sy
    else:
        while x1 != x2 + sx:
            mask.column(y1 - half + extra, x1, y1 + half)
            e2 = err
            if e2 > -dx:
                err -= dy
                x1 += sx
            if e2 < dy:
                err += dx
                y1 += sy


def rasterise_polygon(
    points: list[tuple[int, int]], width: int = 0
) -> tuple[bytes, int, int, int, int]:
    """Rasterise a polygon, filled or outlined, as pygame draws it.

    Args:
        points: The corners, in pixels.
        width: 0 fills; more draws a closed outline that thick.

    Returns:
        `(pixels, left, top, box_width, box_height)`: white RGBA with the
        coverage in alpha, for the box whose top-left corner is
        `(left, top)`. The box has one pixel of room on the far side,
        because pygame's edges are inclusive.
    """
    xs = [int(x) for x, _ in points]
    ys = [int(y) for _, y in points]
    # A thick outline grows across its line by up to half the width.
    grow = width // 2 + 1 if width > 1 else 0
    left, top = min(xs) - grow, min(ys) - grow
    box_width = max(xs) - left + 1 + grow
    box_height = max(ys) - top + 1 + grow
    mask = _Mask(box_width, box_height)
    local_x = [x - left for x in xs]
    local_y = [y - top for y in ys]
    if width <= 0 and len(points) == 3:
        _fill_triangle(mask, local_x, local_y)
    elif width <= 0:
        _fill(mask, local_x, local_y)
    else:
        count = len(points)
        for i in range(count):
            after = (i + 1) % count
            _line(mask, local_x[i], local_y[i], local_x[after], local_y[after], width)
    return mask.rgba(), left, top, box_width, box_height
