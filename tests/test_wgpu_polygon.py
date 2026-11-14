"""The wgpu UI's polygons: triangulated and outlined in Python for the GPU.

How the pixels compare with pygame is `test_wgpu_pixels.TestBounded`; this
is the geometry.
"""

from __future__ import annotations

import math
import random
import struct

import pytest

from pyguara.graphics.backends.wgpu.polygon import (
    MITER_LIMIT,
    outline_ring,
    polygon_mesh,
    triangulate,
)


def _area(points: list[tuple[float, float]]) -> float:
    return abs(
        sum(
            x1 * y2 - x2 * y1
            for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True)
        )
        / 2
    )


def _triangles_area(
    points: list[tuple[float, float]], triangles: list[tuple[int, int, int]]
) -> float:
    return sum(_area([points[i], points[j], points[k]]) for i, j, k in triangles)


def _star(corners: int, seed: int) -> list[tuple[float, float]]:
    """A simple polygon, concave in places: points by angle, radius random."""
    rng = random.Random(seed)
    radii = [rng.uniform(20, 80) for _ in range(corners)]
    return [
        (
            100 + radius * math.cos(2 * math.pi * i / corners),
            100 + radius * math.sin(2 * math.pi * i / corners),
        )
        for i, radius in enumerate(radii)
    ]


@pytest.mark.parametrize("seed", range(40))
def test_a_simple_polygon_is_covered_exactly_once(seed: int) -> None:
    points = _star(3 + seed % 9, seed)
    triangles = triangulate(points)

    assert len(triangles) == len(points) - 2
    assert _triangles_area(points, triangles) == pytest.approx(_area(points))


def test_either_winding_triangulates() -> None:
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert _triangles_area(square, triangulate(square)) == pytest.approx(100)
    backwards = square[::-1]
    assert _triangles_area(backwards, triangulate(backwards)) == pytest.approx(100)


def test_a_concave_arrow_does_not_fill_its_notch() -> None:
    arrow = [(0.0, 0.0), (100.0, 50.0), (0.0, 100.0), (40.0, 50.0)]
    assert _triangles_area(arrow, triangulate(arrow)) == pytest.approx(_area(arrow))


def test_fewer_than_three_corners_is_nothing() -> None:
    assert triangulate([(0.0, 0.0), (1.0, 1.0)]) == []


def test_an_outline_is_as_wide_as_asked_along_an_edge() -> None:
    square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    vertices, triangles = outline_ring(square, 4.0)

    assert len(triangles) == 2 * len(square)
    # A right-angled corner's miter reaches half the width along each axis.
    xs = sorted({round(x, 6) for x, _ in vertices})
    assert xs == [-2.0, 2.0, 98.0, 102.0]
    # The ring's area: the outer square less the inner one.
    assert _triangles_area(vertices, triangles) == pytest.approx(104**2 - 96**2)


def test_a_sharp_corner_is_cut_at_the_miter_limit() -> None:
    spike = [(0.0, 0.0), (100.0, 2.0), (0.0, 4.0)]
    vertices, _ = outline_ring(spike, 2.0)

    tip = spike[1]
    reach = max(math.dist(tip, vertex) for vertex in vertices[2:4])
    assert reach <= MITER_LIMIT * 1.0 + 1e-6


def test_the_mesh_buffers_are_what_the_mesh_step_reads() -> None:
    vertices, indices, count = polygon_mesh([(0, 0), (10, 0), (0, 10)], 0, (1, 2, 3, 4))

    assert len(vertices) == 3 * 20 and len(indices) == 4 * count == 12
    x, y, u, v, *rgba = struct.unpack("<ffffBBBB", vertices[:20])
    # Corners land on pixel centres, where pygame's edges run.
    assert (x, y, u, v, rgba) == (0.5, 0.5, 0.5, 0.5, [1, 2, 3, 4])
