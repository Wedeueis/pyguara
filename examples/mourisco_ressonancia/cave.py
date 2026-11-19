"""Mourisco: Ressonância - the cave itself.

A hand-authored tile grid, because the level's *shape* is the puzzle: a
procedural cave would make the platforming and the sightlines accidental.
Solid tiles become static physics bodies, which is what the echolocation
raycasts actually hit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyguara.common.grid import Cell
from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2

TILE = 32.0

# '#' solid rock, '.' open air, 'P' player spawn, 'E' the exit,
# 's' a spider's perch, 'b' a bat roost.
CAVE_WIDTH = 72
CAVE_HEIGHT = 26


def generate_cave(seed: int = 31337) -> list[str]:
    """Carve a cave out of solid rock, deterministically.

    Solid-first rather than open-first, which is the whole reason it looks
    like a cave: a pulse in a carved tunnel lights the wall a few metres
    away, where a pulse in a mostly-open box lights almost nothing and
    returns black. An earlier hand-drawn map was open-first and read as
    scattered floating blocks for exactly that reason.

    A single meandering trunk passage guarantees the level is completable
    (the walk only ever advances toward the exit), with chambers and dead
    ends hung off it for places worth pulsing into.
    """
    rng = RandomStream(seed)
    grid = [["#"] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]

    def carve(cx: int, cy: int, radius: int) -> None:
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                # Keep a solid border so the cave is sealed.
                if 1 <= x < CAVE_WIDTH - 1 and 1 <= y < CAVE_HEIGHT - 1:
                    grid[y][x] = "."

    # The trunk: always steps right, wanders vertically.
    y = CAVE_HEIGHT // 2
    branch_points: list[tuple[int, int]] = []
    for x in range(3, CAVE_WIDTH - 3):
        # Narrow on purpose: the wall has to sit inside pulse range,
        # or a chirp lights nothing and the cave reads as void.
        carve(x, y, 1 if rng.uniform(0, 1) > 0.4 else 2)
        if rng.uniform(0, 1) > 0.55:
            y += 1 if rng.uniform(0, 1) > 0.5 else -1
            y = max(4, min(CAVE_HEIGHT - 5, y))
        if x % 9 == 0:
            branch_points.append((x, y))

    # Side passages and chambers, so the trunk is not the only thing to
    # find and a scream has somewhere interesting to reach.
    for bx, by in branch_points:
        direction = 1 if rng.uniform(0, 1) > 0.5 else -1
        cy = by
        for _step in range(int(rng.uniform(3, 8))):
            cy += direction
            cy = max(3, min(CAVE_HEIGHT - 4, cy))
            carve(bx + int(rng.uniform(-1, 2)), cy, 1)
        carve(bx, cy, int(rng.uniform(2, 3)))

    rows = ["".join(row) for row in grid]

    # Spawn on the left of the trunk, on the first cell with floor under
    # it so the player starts standing rather than mid-fall.
    spawn_x = 4
    spawn_y = next(
        (
            y
            for y in range(CAVE_HEIGHT - 2, 0, -1)
            if rows[y][spawn_x] == "." and rows[y + 1][spawn_x] == "#"
        ),
        CAVE_HEIGHT // 2,
    )
    spawn = (spawn_x, spawn_y)

    # Seal anything the player could fall into and not climb out of. Done
    # before placing the exit or any creature, so nothing can be stranded
    # in a pocket that is about to be filled in.
    rows = seal_untraversable(rows, spawn)
    layout = parse_cave(rows)
    reachable = traversable_cells(layout, spawn)

    # The exit goes at the furthest reachable point, which both guarantees
    # it is escapable and makes the goal the deepest part of the cave
    # rather than an arbitrary coordinate.
    goal = max(reachable, key=lambda cell: (cell[0] - spawn_x) ** 2 + cell[1] ** 2)

    grid = [list(row) for row in rows]
    grid[spawn[1]][spawn[0]] = "P"
    grid[goal[1]][goal[0]] = "E"

    # Creatures, in reachable air well away from the spawn so the opening
    # seconds are not an ambush.
    candidates = sorted(
        cell
        for cell in reachable
        if abs(cell[0] - spawn_x) > 10 and cell not in (spawn, goal)
    )
    placed = 0
    attempts = 0
    while placed < 9 and attempts < 400 and candidates:
        attempts += 1
        cell = candidates[int(rng.uniform(0, len(candidates)))]
        if grid[cell[1]][cell[0]] != ".":
            continue
        grid[cell[1]][cell[0]] = "s" if placed % 3 == 2 else "b"
        placed += 1

    return ["".join(row) for row in grid]


@dataclass
class CaveLayout:
    """Parsed level geometry and spawn points."""

    solids: set[Cell] = field(default_factory=set)
    player_spawn: Vector2 = field(default_factory=lambda: Vector2(64, 64))
    exit_position: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    spider_perches: list[Vector2] = field(default_factory=list)
    bat_roosts: list[Vector2] = field(default_factory=list)
    width: int = 0
    height: int = 0

    @property
    def world_width(self) -> float:
        """Level width in pixels."""
        return self.width * TILE

    @property
    def world_height(self) -> float:
        """Level height in pixels."""
        return self.height * TILE

    def is_solid(self, cell: Cell) -> bool:
        """Whether `cell` is rock (out of bounds counts as rock)."""
        x, y = cell
        if not (0 <= x < self.width and 0 <= y < self.height):
            return True
        return cell in self.solids

    def tile_rect(self, cell: Cell) -> Rect:
        """The world-space rect of one tile."""
        return Rect(int(cell[0] * TILE), int(cell[1] * TILE), int(TILE), int(TILE))


def parse_cave(rows: list[str] | None = None) -> CaveLayout:
    """Turn the ASCII map into geometry and spawn points."""
    rows = rows if rows is not None else CAVERN
    layout = CaveLayout(width=len(rows[0]), height=len(rows))

    for y, row in enumerate(rows):
        for x, glyph in enumerate(row):
            centre = Vector2(x * TILE + TILE / 2, y * TILE + TILE / 2)
            if glyph == "#":
                layout.solids.add((x, y))
            elif glyph == "P":
                layout.player_spawn = centre
            elif glyph == "E":
                layout.exit_position = centre
            elif glyph == "s":
                layout.spider_perches.append(centre)
            elif glyph == "b":
                layout.bat_roosts.append(centre)

    return layout


def exposed_faces(layout: CaveLayout) -> list[tuple[Cell, Rect]]:
    """Every solid tile with at least one open neighbour, and its rect.

    Only these are worth drawing or lighting: a tile buried inside the rock
    can never be seen, and skipping them keeps the per-frame draw count
    proportional to the cave's *surface* rather than its volume.
    """
    faces: list[tuple[Cell, Rect]] = []
    for cell in layout.solids:
        x, y = cell
        neighbours = ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
        if any(not layout.is_solid(n) for n in neighbours):
            faces.append((cell, layout.tile_rect(cell)))
    return faces


# How many tiles the player can gain in one jump. Derived from
# `systems.JUMP_SPEED` / `GRAVITY` (about 3.4 tiles) and rounded *down*:
# a level that assumes the absolute apex is a level that softlocks on a
# missed input.
JUMP_TILES = 3


def _moves_from(layout: CaveLayout, cell: Cell) -> list[Cell]:
    """Cells reachable from `cell` by one platformer move.

    A deliberately conservative model of `PlayerController`: walk or steer
    sideways through open air, fall, and -- only when standing on solid
    ground -- jump straight up through open air. It ignores the fine
    detail of the arc, which is what makes it safe to build levels on: it
    never claims a move the player cannot actually make.
    """
    x, y = cell
    moves: list[Cell] = []

    for neighbour in ((x - 1, y), (x + 1, y)):
        if not layout.is_solid(neighbour):
            moves.append(neighbour)

    if not layout.is_solid((x, y + 1)):
        moves.append((x, y + 1))
    else:
        # Standing on something, so a jump is available.
        for height in range(1, JUMP_TILES + 1):
            above = (x, y - height)
            if layout.is_solid(above):
                break
            moves.append(above)

    return moves


def traversable_cells(layout: CaveLayout, start: Cell) -> set[Cell]:
    """Open cells the player can reach from `start` *and* get back from.

    Plain reachability is not enough, and assuming it is caused a real
    softlock: a shaft deeper than a jump is perfectly reachable -- you
    fall in -- and is a dead end the run never recovers from. Keeping only
    the cells that can also return means every open cell is somewhere the
    player can leave again.
    """
    forward: dict[Cell, list[Cell]] = {}
    open_cells = [
        (x, y)
        for y in range(layout.height)
        for x in range(layout.width)
        if not layout.is_solid((x, y))
    ]
    for cell in open_cells:
        forward[cell] = _moves_from(layout, cell)

    backward: dict[Cell, list[Cell]] = {cell: [] for cell in open_cells}
    for cell, targets in forward.items():
        for target in targets:
            if target in backward:
                backward[target].append(cell)

    def _flood(graph: dict[Cell, list[Cell]]) -> set[Cell]:
        seen = {start}
        stack = [start]
        while stack:
            for nxt in graph.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    if start not in forward:
        return set()
    return _flood(forward) & _flood(backward)


def seal_untraversable(rows: list[str], start: Cell) -> list[str]:
    """Fill in every open cell the player could not reach or could not leave.

    Repeated to a fixed point, because filling a cell changes the answer:
    new rock is new floor, which can put a previously unreachable ledge
    within jumping range.
    """
    for _pass in range(6):
        layout = parse_cave(rows)
        keep = traversable_cells(layout, start)
        grid = [list(row) for row in rows]
        changed = False
        for y in range(layout.height):
            for x in range(layout.width):
                if layout.is_solid((x, y)) or (x, y) in keep:
                    continue
                grid[y][x] = "#"
                changed = True
        rows = ["".join(row) for row in grid]
        if not changed:
            break
    return rows


def march(
    layout: CaveLayout, origin: Vector2, direction: Vector2, max_distance: float
) -> list[tuple[float, Cell]]:
    """Cells a ray crosses, with the distance at which it enters each.

    A DDA march rather than fixed-step sampling: it visits each crossed
    cell exactly once and lands exactly on the boundary, so there are no
    gaps at grazing angles and no wasted samples inside a cell.

    Stops at the first solid cell (which *is* included -- that surface is
    what the pulse illuminates), so rock casts an acoustic shadow and the
    sweep never reveals what is behind it.

    Returns:
        `(distance, cell)` in increasing distance order.
    """
    crossed: list[tuple[float, Cell]] = []
    if max_distance <= 0.0:
        return crossed

    length = direction.length
    if length < 1e-6:
        return crossed
    dx, dy = direction.x / length, direction.y / length

    cell_x = int(math.floor(origin.x / TILE))
    cell_y = int(math.floor(origin.y / TILE))

    step_x = 1 if dx >= 0 else -1
    step_y = 1 if dy >= 0 else -1

    # Distance along the ray between successive grid lines on each axis,
    # and to the first one. `inf` when the ray is axis-parallel, which
    # correctly means "never crosses a line on that axis".
    t_delta_x = abs(TILE / dx) if abs(dx) > 1e-9 else math.inf
    t_delta_y = abs(TILE / dy) if abs(dy) > 1e-9 else math.inf

    if abs(dx) > 1e-9:
        next_boundary_x = (cell_x + (1 if step_x > 0 else 0)) * TILE
        t_max_x = (next_boundary_x - origin.x) / dx
    else:
        t_max_x = math.inf
    if abs(dy) > 1e-9:
        next_boundary_y = (cell_y + (1 if step_y > 0 else 0)) * TILE
        t_max_y = (next_boundary_y - origin.y) / dy
    else:
        t_max_y = math.inf

    distance = 0.0
    while distance <= max_distance:
        cell = (cell_x, cell_y)
        crossed.append((distance, cell))
        if layout.is_solid(cell):
            break

        if t_max_x < t_max_y:
            distance = t_max_x
            t_max_x += t_delta_x
            cell_x += step_x
        else:
            distance = t_max_y
            t_max_y += t_delta_y
            cell_y += step_y

    return crossed


@dataclass
class Formation:
    """A stalactite or stalagmite, for silhouette interest."""

    base: Vector2
    tip: Vector2
    width: float


def cave_formations(layout: CaveLayout, seed: int = 20260912) -> list[Formation]:
    """Scatter stalactites/stalagmites on exposed ceilings and floors.

    Generated once from a seeded stream rather than per frame: these are
    geometry, not an effect, and a cave whose spikes rearrange themselves
    every frame would be unreadable.
    """
    rng = RandomStream(seed)
    formations: list[Formation] = []

    for cell in sorted(layout.solids):
        x, y = cell
        below_open = not layout.is_solid((x, y + 1))
        above_open = not layout.is_solid((x, y - 1))

        if below_open and rng.uniform(0, 1) > 0.55:
            base = Vector2(x * TILE + TILE / 2, (y + 1) * TILE)
            formations.append(
                Formation(
                    base=base,
                    tip=Vector2(base.x, base.y + rng.uniform(10.0, 26.0)),
                    width=rng.uniform(6.0, 12.0),
                )
            )
        if above_open and rng.uniform(0, 1) > 0.7:
            base = Vector2(x * TILE + TILE / 2, y * TILE)
            formations.append(
                Formation(
                    base=base,
                    tip=Vector2(base.x, base.y - rng.uniform(8.0, 20.0)),
                    width=rng.uniform(5.0, 10.0),
                )
            )

    return formations


# Built at import time, after every helper it depends on is defined.
CAVERN = generate_cave()
