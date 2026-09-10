"""A uniform-grid spatial hash for fast "what's near this point" queries.

Bucketing world positions into fixed-size cells turns a radius or rectangle
query into "look at a handful of cells" instead of "scan every entry" --
the same trade physics engines make for broad-phase collision, generalised
here for gameplay code with no physics body at all: pooled projectiles, AI
perception targets, click-picking, RTS selection. It knows nothing about
entities or components -- callers supply whatever key they like (an entity
id, typically) alongside a position and an optional filter mask.

This is a broad-phase index only. `query_radius` confirms exact distance
before returning a key (cheap, since positions are already tracked), but it
knows nothing of a key's own size or shape -- a caller wanting exact overlap
fetches its own per-key extent data and confirms it, the same way
`IPhysicsEngine.region_query` is a cheap AABB filter that callers refine
with `overlap_box_all`/`overlap_circle`.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Generic, TypeVar

from pyguara.common.types import Rect, Vector2

DEFAULT_CELL_SIZE = 64.0
_FULL_MASK = 0xFFFFFFFF

Cell = tuple[int, int]
K = TypeVar("K")


class SpatialHash(Generic[K]):  # noqa: UP046 -- mypy is pinned to python_version
    # 3.10 (pyproject.toml), which rejects PEP 695 `class SpatialHash[K]` syntax.
    """Buckets keys by position into fixed-size cells for range queries."""

    __slots__ = ("_cell_size", "_cells", "_positions", "_masks")

    def __init__(self, cell_size: float = DEFAULT_CELL_SIZE) -> None:
        """Create an empty hash with the given cell size.

        Args:
            cell_size: Width and height of one grid cell, in world units.
                Pick something close to the typical query radius -- too
                small and a query touches many cells, too large and each
                cell holds too many keys to filter cheaply.
        """
        self._cell_size = cell_size
        self._cells: dict[Cell, set[K]] = defaultdict(set)
        self._positions: dict[K, Vector2] = {}
        self._masks: dict[K, int] = {}

    def insert(self, key: K, position: Vector2, mask: int = _FULL_MASK) -> None:
        """Add `key`, or reposition it if already present.

        Safe to call every tick for a key that's already tracked -- moving
        within the same cell is just an updated position, no bucket churn.

        Args:
            key: Caller-chosen identifier, typically an entity id.
            position: The key's current world position.
            mask: Bits a query must share at least one of to see this key.
        """
        old_position = self._positions.get(key)
        if old_position is not None:
            if self._cell_of(old_position) == self._cell_of(position):
                self._positions[key] = position
                self._masks[key] = mask
                return
            self._discard_from_cell(key, old_position)
        self._cells[self._cell_of(position)].add(key)
        self._positions[key] = position
        self._masks[key] = mask

    def remove(self, key: K) -> None:
        """Remove `key`, if present. A no-op otherwise."""
        position = self._positions.pop(key, None)
        if position is None:
            return
        del self._masks[key]
        self._discard_from_cell(key, position)

    def query_point(self, point: Vector2, mask: int = _FULL_MASK) -> list[K]:
        """Every key sharing `point`'s cell, filtered by `mask`."""
        return [
            key
            for key in self._cells.get(self._cell_of(point), ())
            if self._masks[key] & mask
        ]

    def query_radius(
        self, center: Vector2, radius: float, mask: int = _FULL_MASK
    ) -> list[K]:
        """Every key within `radius` of `center`, confirmed by exact distance."""
        bounds = Rect(
            int(math.floor(center.x - radius)),
            int(math.floor(center.y - radius)),
            int(math.ceil(radius * 2)),
            int(math.ceil(radius * 2)),
        )
        return [
            key
            for key in self._candidates(bounds)
            if self._masks[key] & mask
            and center.distance_to(self._positions[key]) <= radius
        ]

    def query_rect(self, bounds: Rect, mask: int = _FULL_MASK) -> list[K]:
        """Every key whose position lies inside `bounds`."""
        return [
            key
            for key in self._candidates(bounds)
            if self._masks[key] & mask and bounds.contains_point(self._positions[key])
        ]

    def _candidates(self, bounds: Rect) -> set[K]:
        """Union of every cell `bounds` touches."""
        min_cell = self._cell_of(Vector2(bounds.left, bounds.top))
        max_cell = self._cell_of(Vector2(bounds.right, bounds.bottom))
        found: set[K] = set()
        for cx in range(min_cell[0], max_cell[0] + 1):
            for cy in range(min_cell[1], max_cell[1] + 1):
                found.update(self._cells.get((cx, cy), ()))
        return found

    def _discard_from_cell(self, key: K, position: Vector2) -> None:
        cell = self._cell_of(position)
        self._cells[cell].discard(key)
        if not self._cells[cell]:
            del self._cells[cell]

    def _cell_of(self, position: Vector2) -> Cell:
        return (
            math.floor(position.x / self._cell_size),
            math.floor(position.y / self._cell_size),
        )
