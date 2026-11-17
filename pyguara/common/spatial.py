"""A uniform-grid spatial hash for fast "what's near this point" queries.

Positions are bucketed into fixed-size cells, so a radius or rectangle
query looks at a handful of cells. Callers supply any key (usually an
entity id) with a position and an optional filter mask. It is a
broad-phase index: `query_radius` confirms exact distance, but nothing
here knows a key's size or shape.

The index is held in Rust and has no Python implementation. See
`docs/agents/native-extension.md` for what it promises and what it does
not, the result order among them.
"""

from __future__ import annotations

from typing import Any, cast

from pyguara.common.types import Rect, Vector2
from pyguara.native import require_extension

DEFAULT_CELL_SIZE = 64.0
_FULL_MASK = 0xFFFFFFFF


class SpatialHash[K]:
    """Buckets keys by position into fixed-size cells for range queries."""

    __slots__ = ("_cell_size", "_native")

    def __init__(self, cell_size: float = DEFAULT_CELL_SIZE) -> None:
        """Create an empty hash with the given cell size.

        Args:
            cell_size: Width and height of one grid cell, in world units.
                Pick something close to the typical query radius -- too
                small and a query touches many cells, too large and each
                cell holds too many keys to filter cheaply.

        Raises:
            ValueError: If `cell_size` is not finite and positive.
            RuntimeError: If the native extension cannot be imported.
        """
        self._cell_size = cell_size
        self._native: Any = require_extension("SpatialHash").NativeSpatialHash(
            cell_size
        )

    @property
    def cell_size(self) -> float:
        """Width and height of one grid cell, in world units."""
        return self._cell_size

    def __len__(self) -> int:
        """Return how many keys the index holds."""
        return len(self._native)

    def insert(self, key: K, position: Vector2, mask: int = _FULL_MASK) -> None:
        """Add `key`, or reposition it if already present.

        Safe to call every tick for a key that is already tracked, and
        between queries: a write does not rebuild the index by itself.

        Args:
            key: Caller-chosen hashable identifier, typically an entity id.
            position: The key's current world position.
            mask: Bits a query must share at least one of to see this key.

        Raises:
            ValueError: If either coordinate is NaN, or past the cell range
                the index can represent; see
                `rust/src/grid.rs::check_position`.
            OverflowError: If either coordinate is infinite.
        """
        self._native.insert(key, position, mask)

    def remove(self, key: K) -> None:
        """Remove `key`, if present. A no-op otherwise."""
        self._native.remove(key)

    def query_point(self, point: Vector2, mask: int = _FULL_MASK) -> list[K]:
        """Every key sharing `point`'s cell, filtered by `mask`.

        No distance test: a key anywhere in the cell counts, so what comes
        back depends on where the cell boundaries fall. That makes it the
        one query whose result is sensitive to `cell_size`.
        """
        return cast("list[K]", self._native.query_point(point, mask))

    def query_radius(
        self, center: Vector2, radius: float, mask: int = _FULL_MASK
    ) -> list[K]:
        """Every key within `radius` of `center`, confirmed by exact distance.

        The order of the result is not defined. A caller that wants a
        particular one of several results must pick it (by distance, by
        id), not take the first.
        """
        return cast("list[K]", self._native.query_radius(center, radius, mask))

    def query_rect(self, bounds: Rect, mask: int = _FULL_MASK) -> list[K]:
        """Every key whose position lies inside `bounds`.

        Half-open, following `Rect.contains_point`: the left and top edges
        are inclusive and the right and bottom exclusive, as
        `pygame.Rect.collidepoint` has it.
        """
        return cast(
            "list[K]",
            self._native.query_rect(
                bounds.left, bounds.top, bounds.right, bounds.bottom, mask
            ),
        )
