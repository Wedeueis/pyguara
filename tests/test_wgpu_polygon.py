"""The wgpu UI's polygon rasteriser against `pygame.draw.polygon`.

`polygon.py` transcribes pygame's fill and thick-line rules so the UI's
polygons cover the same pixels on both renderers. Held to pygame itself, on
random polygons, filled and outlined.
"""

from __future__ import annotations

import random

import pygame
import pytest

from pyguara.graphics.backends.wgpu.polygon import rasterise_polygon


def _pygame_mask(
    points: list[tuple[int, int]], width: int, size: int
) -> set[tuple[int, int]]:
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.polygon(surface, (255, 255, 255, 255), points, width)
    return {
        (x, y) for y in range(size) for x in range(size) if surface.get_at((x, y)).a
    }


def _our_mask(points: list[tuple[int, int]], width: int) -> set[tuple[int, int]]:
    pixels, left, top, box_width, box_height = rasterise_polygon(points, width)
    return {
        (left + i % box_width, top + i // box_width)
        for i in range(box_width * box_height)
        if pixels[i * 4 + 3]
    }


def _polygons(seed: int, count: int) -> list[list[tuple[int, int]]]:
    rng = random.Random(seed)
    shapes = []
    for _ in range(count):
        corners = rng.randint(3, 7)
        shapes.append(
            [(rng.randint(8, 72), rng.randint(8, 72)) for _ in range(corners)]
        )
    return shapes


@pytest.mark.parametrize("width", [0, 1, 2, 3, 4])
def test_random_polygons_cover_what_pygame_covers(width: int) -> None:
    for points in _polygons(seed=width, count=150):
        assert _our_mask(points, width) == _pygame_mask(points, width, 80), points


@pytest.mark.parametrize(
    "points",
    [
        [(10, 10), (40, 10), (40, 10)],  # flat: one row
        [(10, 10), (40, 10), (40, 30), (10, 30)],  # axis-aligned, flat edges
        [(20, 10), (30, 20), (20, 30), (10, 20)],  # diamond
        [(5, 5), (60, 5), (30, 6)],  # a sliver
    ],
)
@pytest.mark.parametrize("width", [0, 2])
def test_degenerate_shapes(points: list[tuple[int, int]], width: int) -> None:
    assert _our_mask(points, width) == _pygame_mask(points, width, 80)
