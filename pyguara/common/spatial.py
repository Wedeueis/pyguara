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

**There is a native implementation behind the same methods**, worth
8-10x on a tick of insert-everything-then-query-everything and reached
through `accelerate=` or the engine-wide switch. Every consumer gets it
without changing a line, which is the point: the index is shared by
flocking, actor separation, magnet pickups, projectile hits and two
demos, so one port pays for all of them. See
`docs/adr/0004-the-native-boundary.md`, Decision 7 -- which also records
that the ADR had previously ruled this shape out, on reasoning a
measurement contradicted, and what each *consumer* actually gains, which
is far less than the index does.

**One exotic key shape diverges**: the native store holds an exclusive
borrow of itself for the duration of a call, so a key whose `__hash__` or
`__eq__` re-enters the same index raises `RuntimeError: Already
borrowed`. The Python store survives a re-entry that fires once and
recurses to a stack overflow if it fires every time, so this is one store
failing loudly where the other fails slowly rather than one being safe.
No engine key does either -- they are entity ids. The *safe* version of
that shape is relied on throughout, though: a query returns a
materialised list, so iterating one while removing keys from the index is
fine on both stores, and that is pinned by a test rather than left to
chance.

**One pattern is slower on the native store**, and asymptotically so:
alternating `insert` and a query, rather than syncing the whole index and
then sweeping it. The native grid rebuilds on the first query after any
write, so an alternating loop pays O(n) per query where Python pays O(1)
per insert -- measured at 0.13x the Python speed over 4000 keys. Nothing
in the engine does this (`SpatialIndexSystem` syncs, then the consumers
query), but a game could, and `accelerate=False` is the answer if it
does.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterator
from typing import Any, cast

from pyguara.common.types import Rect, Vector2
from pyguara.native import native_module

DEFAULT_CELL_SIZE = 64.0
_FULL_MASK = 0xFFFFFFFF

Cell = tuple[int, int]


class SpatialHash[K]:
    """Buckets keys by position into fixed-size cells for range queries."""

    __slots__ = ("_cell_size", "_cells", "_positions", "_masks", "_native")

    def __init__(
        self, cell_size: float = DEFAULT_CELL_SIZE, *, accelerate: bool | None = None
    ) -> None:
        """Create an empty hash with the given cell size.

        Args:
            cell_size: Width and height of one grid cell, in world units.
                Pick something close to the typical query radius -- too
                small and a query touches many cells, too large and each
                cell holds too many keys to filter cheaply.
            accelerate: Whether to index natively. None, the default,
                defers to the engine-wide setting --
                `PerformanceConfig.native_acceleration`, resolved once at
                bootstrap -- so a game decides this in one place rather
                than per index. True demands the extension and raises if
                it is missing; False forces the Python path. Both are
                overrides for tests and for the parity suite, not a second
                configuration surface.

        Raises:
            RuntimeError: If `accelerate=True` and the extension is absent.
        """
        self._cell_size = cell_size
        self._cells: dict[Cell, set[K]] = defaultdict(set)
        self._positions: dict[K, Vector2] = {}
        self._masks: dict[K, int] = {}

        native = native_module() if accelerate is not False else None
        if accelerate and native is None:
            raise RuntimeError(
                "accelerate=True but the native extension is not available. "
                "Build it with `cargo build --release`, or leave "
                "`accelerate` unset to fall back to Python."
            )
        self._native: Any | None = (
            native.NativeSpatialHash(cell_size) if native else None
        )

    @property
    def accelerated(self) -> bool:
        """Whether this index buckets and queries natively."""
        return self._native is not None

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
        if self._native is not None:
            self._native.insert(key, position, mask)
            return
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
        if self._native is not None:
            self._native.remove(key)
            return
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
        if self._native is not None:
            return cast("list[K]", self._native.query_point(point, mask))
        return [
            key
            for key in self._cells.get(self._cell_of(point), ())
            if self._masks[key] & mask
        ]

    def query_radius(
        self, center: Vector2, radius: float, mask: int = _FULL_MASK
    ) -> list[K]:
        """Every key within `radius` of `center`, confirmed by exact distance.

        The cell range is derived straight from `center +/- radius` rather
        than by building a `Rect` and asking `_cell_of` about its corners,
        and the distance test is squared, so a query costs no `Rect`, no
        `Vector2` and no `sqrt` per candidate.

        **The order of the result is not defined and differs between the
        two stores.** Python yields from `set[K]`, so its order is the
        keys' hash order -- which `PYTHONHASHSEED` randomises per process
        for the string keys the engine actually uses, making it unstable
        even between two runs of the same code. The native index returns
        slot order, which is at least stable. A caller that wants a
        particular one of several results must pick it (by distance, by
        id), not take the first.
        """
        if self._native is not None:
            return cast("list[K]", self._native.query_radius(center, radius, mask))
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
        if self._native is not None:
            return cast(
                "list[K]",
                self._native.query_rect(
                    bounds.left, bounds.top, bounds.right, bounds.bottom, mask
                ),
            )
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
