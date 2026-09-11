"""Binary space partitioning: recursively split a region into a tree of sub-regions.

Genre-agnostic on purpose -- `bounds` and every split are plain `Rect`s in
whatever unit the caller wants (pixels, grid cells), with no "room" or
"dungeon" vocabulary at this layer. `dungeon.py`'s room-carving and
corridor connection is the roguelike recipe built on top; an RTS or TD
map-gen would consume the same tree differently.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect


@dataclass
class BspNode:
    """One node of a BSP tree.

    Attributes:
        bounds: This node's region.
        left: One child after a split, or None for a leaf.
        right: The other child after a split, or None for a leaf.
        room: Set by a caller (see `dungeon.carve_room()`) on leaf nodes
            only -- this module never reads or writes it itself.
    """

    bounds: Rect
    left: BspNode | None = None
    right: BspNode | None = None
    room: Rect | None = None

    @property
    def is_leaf(self) -> bool:
        """Whether this node was never split."""
        return self.left is None and self.right is None

    def leaves(self) -> list[BspNode]:
        """Return every leaf node in this subtree, left-to-right."""
        if self.is_leaf:
            return [self]
        result: list[BspNode] = []
        if self.left is not None:
            result.extend(self.left.leaves())
        if self.right is not None:
            result.extend(self.right.leaves())
        return result


def split_bsp(
    bounds: Rect,
    rng: RandomStream,
    min_leaf_size: int,
    max_depth: int | None = None,
) -> BspNode:
    """Recursively split `bounds` into a binary tree of leaf regions.

    Splits vertically (side-by-side children) when a region is wider than
    tall, horizontally (stacked children) when taller than wide, and picks
    randomly between the two for a near-square region -- the classic BSP
    dungeon-generator heuristic, avoiding a lattice of uniformly skinny
    rooms. A region stops splitting once neither dimension can produce two
    children at least `min_leaf_size` each, or once `max_depth` is reached.

    Args:
        bounds: The region to partition.
        rng: Seeded stream driving every split decision -- the same seed
            and call sequence always produces the same tree.
        min_leaf_size: The smallest a leaf's width or height may be. A
            split is only taken if both resulting children would still
            meet this.
        max_depth: Stop splitting past this recursion depth, regardless of
            size. `None` (the default) splits until size alone stops it.

    Returns:
        The tree's root, `bounds` itself as the top-level region.
    """
    return _split(bounds, rng, min_leaf_size, max_depth, depth=0)


def _split(
    bounds: Rect,
    rng: RandomStream,
    min_leaf_size: int,
    max_depth: int | None,
    depth: int,
) -> BspNode:
    node = BspNode(bounds=bounds)
    if max_depth is not None and depth >= max_depth:
        return node

    can_split_vertically = bounds.width >= min_leaf_size * 2
    can_split_horizontally = bounds.height >= min_leaf_size * 2
    if not can_split_vertically and not can_split_horizontally:
        return node

    if can_split_vertically and can_split_horizontally:
        if abs(bounds.width - bounds.height) < min_leaf_size:
            split_vertically = rng.random() < 0.5
        else:
            split_vertically = bounds.width > bounds.height
    else:
        split_vertically = can_split_vertically

    if split_vertically:
        cut = rng.randint(
            bounds.x + min_leaf_size, bounds.x + bounds.width - min_leaf_size
        )
        left_bounds = Rect(bounds.x, bounds.y, cut - bounds.x, bounds.height)
        right_bounds = Rect(cut, bounds.y, bounds.x + bounds.width - cut, bounds.height)
    else:
        cut = rng.randint(
            bounds.y + min_leaf_size, bounds.y + bounds.height - min_leaf_size
        )
        left_bounds = Rect(bounds.x, bounds.y, bounds.width, cut - bounds.y)
        right_bounds = Rect(bounds.x, cut, bounds.width, bounds.y + bounds.height - cut)

    node.left = _split(left_bounds, rng, min_leaf_size, max_depth, depth + 1)
    node.right = _split(right_bounds, rng, min_leaf_size, max_depth, depth + 1)
    return node
