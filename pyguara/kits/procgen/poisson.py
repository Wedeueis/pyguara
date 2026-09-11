"""Poisson-disc sampling: natural, minimum-spacing point placement.

The "constraint-placement" algorithm family #28 names, scoped to the
specific, well-defined piece: Bridson's algorithm, guaranteeing every
returned point sits at least `min_distance` from every other. Generic
frequency/dependency/exclusion rule-checking between placed item types is
a separate, heavier concern -- deliberately not built here.
"""

from __future__ import annotations

import math

from pyguara.common.grid import Cell, world_to_cell
from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2

# At cell_size = min_distance / sqrt(2), at most one accepted point can
# ever land in a cell, and every point within min_distance of a candidate
# is guaranteed to fall within this many cells of it in each axis --
# Bridson's own choice, matched here.
_ACCEL_SEARCH_RADIUS = 2


def poisson_disc_sample(
    bounds: Rect,
    min_distance: float,
    rng: RandomStream,
    max_attempts: int = 30,
) -> list[Vector2]:
    """Scatter points within `bounds`, each at least `min_distance` apart.

    Bridson's algorithm: grow outward from a random seed point, proposing
    candidates in the annulus between `min_distance` and `2 * min_distance`
    around a random active point, accepting the first candidate that
    clears every existing point. An acceleration grid keyed by
    `pyguara.common.grid.Cell` (sized `min_distance / sqrt(2)` per side)
    keeps each spacing check local instead of scanning every prior point.

    Args:
        bounds: The region to fill.
        min_distance: The minimum allowed distance between any two
            returned points. Must be positive.
        rng: Seeded stream driving every random draw.
        max_attempts: Candidate points tried around an active point before
            it's retired from further growth. Higher values pack tighter
            but cost more.

    Returns:
        The accepted points, in the order accepted. Roughly, but not
        exactly, evenly spaced -- genuinely random within the spacing
        constraint, not a lattice. Empty if `bounds` has no area.

    Raises:
        ValueError: `min_distance` is not positive.
    """
    if min_distance <= 0:
        raise ValueError("poisson_disc_sample: min_distance must be positive")
    if bounds.width <= 0 or bounds.height <= 0:
        return []

    cell_size = min_distance / math.sqrt(2)
    origin = Vector2(bounds.left, bounds.top)
    accepted_by_cell: dict[Cell, Vector2] = {}

    def in_bounds(point: Vector2) -> bool:
        return (
            bounds.left <= point.x <= bounds.right
            and bounds.top <= point.y <= bounds.bottom
        )

    def is_far_enough(point: Vector2) -> bool:
        center = world_to_cell(point, cell_size, origin)
        for dx in range(-_ACCEL_SEARCH_RADIUS, _ACCEL_SEARCH_RADIUS + 1):
            for dy in range(-_ACCEL_SEARCH_RADIUS, _ACCEL_SEARCH_RADIUS + 1):
                neighbor = accepted_by_cell.get((center[0] + dx, center[1] + dy))
                if neighbor is not None and point.distance_to(neighbor) < min_distance:
                    return False
        return True

    def accept(point: Vector2) -> None:
        accepted_by_cell[world_to_cell(point, cell_size, origin)] = point

    initial = Vector2(
        rng.uniform(bounds.left, bounds.right),
        rng.uniform(bounds.top, bounds.bottom),
    )
    points = [initial]
    active = [initial]
    accept(initial)

    while active:
        index = rng.randint(0, len(active) - 1)
        source = active[index]

        placed = False
        for _ in range(max_attempts):
            angle = rng.uniform(0, 2 * math.pi)
            radius = rng.uniform(min_distance, 2 * min_distance)
            candidate = Vector2(
                source.x + radius * math.cos(angle),
                source.y + radius * math.sin(angle),
            )
            if in_bounds(candidate) and is_far_enough(candidate):
                points.append(candidate)
                active.append(candidate)
                accept(candidate)
                placed = True
                break

        if not placed:
            active.pop(index)

    return points
