"""The flagship #28 recipe: a dungeon of rooms with doors and a critical path.

Built entirely on `bsp.py`'s genre-agnostic tree -- a room is a smaller
`Rect` carved inside a leaf's bounds, and the BSP merge tree itself *is*
the critical path: connecting each subtree's representative room to its
sibling's, bottom-up, both guarantees every room is reachable and
produces the branching structure a roguelike floor wants, with no
separate graph or MST algorithm needed. "Doors" are left implicit --
wherever a corridor `Rect` meets a room `Rect` is where one would go; this
doesn't model them as a separate structure.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect
from pyguara.kits.procgen.bsp import BspNode, split_bsp


@dataclass
class DungeonLayout:
    """The result of `generate_dungeon()`.

    Attributes:
        rooms: One `Rect` per BSP leaf, in generation order.
        corridors: Connecting `Rect` segments (each an axis-aligned strip
            `corridor_width` wide), enough of them, together with `rooms`,
            to make every room reachable from every other.
    """

    rooms: list[Rect]
    corridors: list[Rect]


def carve_room(
    leaf_bounds: Rect, rng: RandomStream, min_size: int = 3, padding: int = 1
) -> Rect:
    """Carve a randomly sized, randomly placed room inside a BSP leaf.

    Args:
        leaf_bounds: The leaf region to carve into.
        rng: Seeded stream driving size and placement.
        min_size: The room's minimum width and height, if the leaf has
            room for it. A leaf smaller than `min_size + padding * 2` gets
            a room filling whatever space is actually available instead
            of raising.
        padding: Minimum gap kept between the room and the leaf's edges,
            on every side.

    Returns:
        The room, always fully inside `leaf_bounds`.
    """
    available_width = max(leaf_bounds.width - padding * 2, 1)
    available_height = max(leaf_bounds.height - padding * 2, 1)

    width = rng.randint(min(min_size, available_width), available_width)
    height = rng.randint(min(min_size, available_height), available_height)

    x_slack = available_width - width
    y_slack = available_height - height
    x = leaf_bounds.x + padding + (rng.randint(0, x_slack) if x_slack > 0 else 0)
    y = leaf_bounds.y + padding + (rng.randint(0, y_slack) if y_slack > 0 else 0)

    return Rect(x, y, width, height)


def generate_dungeon(
    bounds: Rect,
    rng: RandomStream,
    min_leaf_size: int = 6,
    room_min_size: int = 3,
    room_padding: int = 1,
    corridor_width: int = 1,
    max_depth: int | None = None,
) -> DungeonLayout:
    """Generate a connected dungeon layout: BSP, carve a room per leaf, connect.

    Args:
        bounds: The overall region to fill.
        rng: Seeded stream; the same seed always produces the same layout.
        min_leaf_size: Forwarded to `split_bsp()`.
        room_min_size: Forwarded to `carve_room()`.
        room_padding: Forwarded to `carve_room()`.
        corridor_width: Width of every connecting corridor segment.
        max_depth: Forwarded to `split_bsp()`.

    Returns:
        The generated layout.
    """
    root = split_bsp(bounds, rng, min_leaf_size, max_depth)
    for leaf in root.leaves():
        leaf.room = carve_room(leaf.bounds, rng, room_min_size, room_padding)

    _, corridors = _connect(root, rng, corridor_width)
    rooms = [leaf.room for leaf in root.leaves() if leaf.room is not None]
    return DungeonLayout(rooms=rooms, corridors=corridors)


def _connect(
    node: BspNode, rng: RandomStream, corridor_width: int
) -> tuple[Rect, list[Rect]]:
    """Connect a subtree's rooms bottom-up.

    Returns:
        A room from this subtree to represent it to the caller's own
        connection one level up, and every corridor segment added so far
        in this subtree.
    """
    if node.is_leaf:
        assert node.room is not None  # generate_dungeon() carves every leaf first
        return node.room, []

    assert node.left is not None and node.right is not None
    left_room, left_corridors = _connect(node.left, rng, corridor_width)
    right_room, right_corridors = _connect(node.right, rng, corridor_width)

    connector = _corridor_between(left_room, right_room, corridor_width)
    representative = rng.choice([left_room, right_room])
    return representative, [*left_corridors, *right_corridors, *connector]


def _corridor_between(a: Rect, b: Rect, width: int) -> list[Rect]:
    """Return an L-shaped corridor's segments, from `a`'s center to `b`'s."""
    ax, ay = a.centerx, a.centery
    bx, by = b.centerx, b.centery
    half = width // 2

    horizontal = Rect(min(ax, bx) - half, ay - half, abs(bx - ax) + width, width)
    vertical = Rect(bx - half, min(ay, by) - half, width, abs(by - ay) + width)
    return [horizontal, vertical]
