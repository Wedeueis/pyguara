"""The spatial hash as plain Python, for the Rust one to be held to.

Buckets are `set`s, so a query's order is the keys' hash order, which
`PYTHONHASHSEED` changes per process for string keys. That makes this the
index to test a caller against when the claim is "the result does not
depend on the order": the Rust index returns a stable order and would let
such a test pass by luck. Membership agrees with `SpatialHash` exactly.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterator

from pyguara.common.spatial import DEFAULT_CELL_SIZE
from pyguara.common.types import Rect, Vector2

_FULL_MASK = 0xFFFFFFFF

Cell = tuple[int, int]


class ReferenceSpatialHash[K]:
    """Buckets keys by position into fixed-size cells for range queries."""

    __slots__ = ("_cell_size", "_cells", "_positions", "_masks")

    def __init__(self, cell_size: float = DEFAULT_CELL_SIZE) -> None:
        """Create an empty hash with the given cell size."""
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

        Raises:
            ValueError: If either coordinate is NaN, as `math.floor`
                would. The native index also rejects a coordinate past
                the cell range it can represent; see
                `rust/src/grid.rs::check_position`.
            OverflowError: If either coordinate is infinite, likewise.
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
        """Every key sharing `point`'s cell, filtered by `mask`.

        No distance test: a key anywhere in the cell counts, so what comes
        back depends on where the cell boundaries fall. That makes it the
        one query whose result is sensitive to `cell_size`, and the reason
        the native index re-confirms a candidate's cell rather than
        trusting its bucket.
        """
        return [
            key
            for key in self._cells.get(self._cell_of(point), ())
            if self._masks[key] & mask
        ]

    def query_radius(
        self, center: Vector2, radius: float, mask: int = _FULL_MASK
    ) -> list[K]:
        """Every key within `radius` of `center`, confirmed by exact distance.

        The order of the result is not defined and differs between the two
        stores. A caller that wants a particular one of several results must
        pick it (by distance, by id), not take the first.
        """
        cell_size = self._cell_size
        min_cx = math.floor((center.x - radius) / cell_size)
        max_cx = math.floor((center.x + radius) / cell_size)
        min_cy = math.floor((center.y - radius) / cell_size)
        max_cy = math.floor((center.y + radius) / cell_size)

        x, y = center.x, center.y
        radius_sq = radius * radius
        positions = self._positions
        masks = self._masks

        found: list[K] = []
        for key in self._candidates(min_cx, max_cx, min_cy, max_cy):
            if not masks[key] & mask:
                continue
            position = positions[key]
            offset_x = position.x - x
            offset_y = position.y - y
            if offset_x * offset_x + offset_y * offset_y <= radius_sq:
                found.append(key)
        return found

    def query_rect(self, bounds: Rect, mask: int = _FULL_MASK) -> list[K]:
        """Every key whose position lies inside `bounds`.

        Half-open, following `Rect.contains_point`: the left and top edges
        are inclusive and the right and bottom exclusive, as
        `pygame.Rect.collidepoint` has it.
        """
        min_cell = self._cell_of(Vector2(bounds.left, bounds.top))
        max_cell = self._cell_of(Vector2(bounds.right, bounds.bottom))
        return [
            key
            for key in self._candidates(
                min_cell[0], max_cell[0], min_cell[1], max_cell[1]
            )
            if self._masks[key] & mask and bounds.contains_point(self._positions[key])
        ]

    def _candidates(
        self, min_cx: int, max_cx: int, min_cy: int, max_cy: int
    ) -> Iterator[K]:
        """Yield every key in the cells spanning the given cell range.

        A generator rather than a set union, and that is safe rather than
        merely faster: `insert` discards a key from its old cell before
        adding it to the new one, so a key lives in exactly one cell and
        the union had nothing to deduplicate. It was paying for a set
        allocation, plus an `update` per touched cell, to remove
        duplicates that cannot occur.
        """
        cells = self._cells
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                cell = cells.get((cx, cy))
                if cell is not None:
                    yield from cell

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
