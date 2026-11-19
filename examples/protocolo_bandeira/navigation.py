"""Routing a chaser around the termite mounds, with A*.

`render.py` has always called the mounds "cover to run past", and until
now that was a caption: they were drawn and nothing else, and a chaser
walked straight through one on its way to the player. This module makes
the line true. The mounds become walls on a coarse navigation grid, and
a chaser that cannot see the player asks `pyguara.ai.pathfinding` for a
route around them instead of pushing into the rock.

Three pieces, in the order they are used:

- `ArenaNavGrid` bakes the arena's mounds into a `GridGraph` once, at
  construction. The clearing is scattered once and never regenerated
  (`render.Backdrop`), so the walls never move and there is nothing to
  rebuild per frame.
- `ChaserNavigator` holds one cached path per enemy and hands back the
  direction to steer. It is the thing that keeps A* affordable with a
  wave of chasers on screen: most of them can see the player most of the
  time, and a straight line costs nothing.
- `chase_direction` is what the behaviour tree's `chase_player` action
  calls, through `AIContext.navigator`.

**Line of sight first, A* second.** A chaser with a clear run at the
player steers straight at it, exactly as before -- the path is only
computed when something is in the way. That is not an optimisation bolted
on afterwards; it is what makes the behaviour read correctly. An enemy
that follows grid waypoints across open ground looks like it is walking
on rails, and the arena is open ground nearly everywhere.

The player is not routed and not blocked: an anteater the size of the
one in this arena goes over a mound, and the mounds are there to break
*the swarm's* line, which is the whole point of cover.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyguara.ai.pathfinding import (
    AStarPathfinder,
    GridGraph,
    GridNode,
    OctileDistance,
    path_to_world_coords,
    smooth_path,
    world_to_grid_coords,
)
from pyguara.common.grid import cell_to_world, line
from pyguara.common.types import Rect, Vector2

CELL_SIZE = 32.0
"""World pixels per navigation cell. Coarse on purpose: the arena is a
few hundred pixels across, a chaser is about 20 wide, and a finer grid
would buy accuracy the line-of-sight shortcut throws away anyway."""

CLEARANCE = 14.0
"""How far a mound's influence is grown when blocking cells, in pixels --
roughly a chaser's radius. Without it a route hugs a mound so tightly
that the enemy's body clips through the side of it."""

REPLAN_DISTANCE = 64.0
"""How far the player may drift from the goal a path was planned to
before the path is thrown away. Two cells: less and a chaser re-plans
every frame the player strafes, more and it runs at where the player
used to be."""

ARRIVE_DISTANCE = 18.0
"""How close a chaser must get to a waypoint to consider it reached."""

MAX_PATH_AGE = 1.5
"""Seconds a path is trusted before being re-planned regardless. The
walls never move, but the other enemies shove each other off course, and
a stale path eventually points somewhere its owner has been pushed away
from."""


class ArenaNavGrid:
    """The arena's mounds, as a grid A* can search.

    Built once. The `Backdrop` scatters the clearing at construction and
    never regenerates it, so the walls are as fixed as the ground is.
    """

    def __init__(
        self,
        arena: Rect,
        blockers: list[tuple[Vector2, float]],
        cell_size: float = CELL_SIZE,
    ) -> None:
        """Bake `blockers` into a grid over `arena`.

        Args:
            arena: The play area. The grid covers exactly this, so a
                route never leaves the ground the enemies are clamped to.
            blockers: `(centre, radius)` per obstacle, in world pixels.
            cell_size: World pixels per cell.
        """
        self.cell_size = cell_size
        self.origin = Vector2(float(arena.left), float(arena.top))
        width = max(1, math.ceil(arena.width / cell_size))
        height = max(1, math.ceil(arena.height / cell_size))
        self.graph = GridGraph(width, height, allow_diagonal=True)
        self._heuristic = OctileDistance()
        self._solver = AStarPathfinder()
        self._block(blockers)

    def _block(self, blockers: list[tuple[Vector2, float]]) -> None:
        """Wall off every cell whose centre falls inside a grown blocker."""
        for centre, radius in blockers:
            reach = radius + CLEARANCE
            for cell in self._cells_near(centre, reach):
                if self.graph.in_bounds(cell):
                    self.graph.walls.add(cell)

    def _cells_near(self, centre: Vector2, reach: float) -> list[GridNode]:
        """Every cell whose centre is within `reach` of `centre`."""
        span = math.ceil(reach / self.cell_size) + 1
        origin = self.to_cell(centre)
        found = []
        for dy in range(-span, span + 1):
            for dx in range(-span, span + 1):
                cell = (origin[0] + dx, origin[1] + dy)
                if self.to_world(cell).distance_to(centre) <= reach:
                    found.append(cell)
        return found

    def to_cell(self, position: Vector2) -> GridNode:
        """The cell `position` falls in."""
        return world_to_grid_coords(position, self.cell_size, self.origin)

    def to_world(self, cell: GridNode) -> Vector2:
        """The world centre of `cell`."""
        return cell_to_world(cell, self.cell_size, self.origin)

    def is_clear(self, start: Vector2, end: Vector2) -> bool:
        """Whether nothing blocks the straight run from `start` to `end`.

        The cheap test the whole module is built around: a chaser that
        passes it never pays for a path.

        Args:
            start: Where the chaser is.
            end: Where it wants to be.

        Returns:
            Whether every cell the line crosses is passable.
        """
        crossed = line(self.to_cell(start), self.to_cell(end))
        return all(self.graph.is_passable(cell) for cell in crossed)

    def route(self, start: Vector2, goal: Vector2) -> list[Vector2]:
        """A* from `start` to `goal`, smoothed, in world coordinates.

        Args:
            start: Where the chaser is.
            goal: Where the player is.

        Returns:
            Waypoints, nearest first, with the chaser's own cell dropped
            -- steering at the cell you are standing in is steering
            nowhere. Empty when no route exists, which a caller should
            read as "fall back to a straight line" rather than as "stop":
            a chaser frozen against a rock looks broken, and a chaser
            pressed against one does not.
        """
        start_cell = self._nearest_open(self.to_cell(start))
        goal_cell = self._nearest_open(self.to_cell(goal))
        if start_cell is None or goal_cell is None or start_cell == goal_cell:
            return []
        path = self._solver.find_path(
            self.graph, start_cell, goal_cell, self._heuristic
        )
        if not path:
            return []
        return path_to_world_coords(
            smooth_path(path, self.graph)[1:], self.cell_size, self.origin
        )

    def _nearest_open(self, cell: GridNode) -> GridNode | None:
        """`cell` itself, or the closest passable cell in a small ring.

        An enemy spawns where the wave manager puts it, and the player
        walks over mounds, so either end of a route can legitimately be
        inside a wall. Snapping out beats returning no path at all.
        """
        if self.graph.in_bounds(cell) and self.graph.is_passable(cell):
            return cell
        for ring in range(1, 4):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    candidate = (cell[0] + dx, cell[1] + dy)
                    if self.graph.in_bounds(candidate) and self.graph.is_passable(
                        candidate
                    ):
                        return candidate
        return None


@dataclass
class _Route:
    """One enemy's cached path.

    Attributes:
        waypoints: What is left of it, nearest first.
        planned_for: Where the player was when it was planned.
        age: Seconds since it was planned.
    """

    waypoints: list[Vector2] = field(default_factory=list)
    planned_for: Vector2 = field(default_factory=Vector2.zero)
    age: float = 0.0


class ChaserNavigator:
    """Per-enemy path cache, and the steering direction it produces.

    One instance for the whole scene, keyed by entity id. Paths are
    dropped when their owner dies (`forget`), when the player has moved
    far enough to invalidate them, and when they simply get old.
    """

    def __init__(self, grid: ArenaNavGrid) -> None:
        """Bind the navigator to the arena it routes over.

        Args:
            grid: The baked arena grid.
        """
        self.grid = grid
        self._routes: dict[str, _Route] = {}
        self.plans = 0
        """How many A* searches have been run. Read by the tests, to pin
        that a chaser with a clear view does not pay for one."""

    def direction(
        self, entity_id: str, position: Vector2, target: Vector2, dt: float
    ) -> Vector2:
        """Which way `entity_id` should move to reach `target`.

        Args:
            entity_id: Whose path to use.
            position: Where it is now.
            target: Where the player is.
            dt: Seconds since the last call, ageing the cached path.

        Returns:
            A unit vector, or a zero vector when it is already there.
        """
        if self.grid.is_clear(position, target):
            # The common case: open ground, and no path to pay for.
            self._routes.pop(entity_id, None)
            return _toward(position, target)

        route = self._routes.get(entity_id)
        if route is not None:
            route.age += dt
            if (
                route.age > MAX_PATH_AGE
                or route.planned_for.distance_to(target) > REPLAN_DISTANCE
            ):
                route = None

        if route is None:
            route = _Route(
                waypoints=self.grid.route(position, target), planned_for=target
            )
            self.plans += 1
            self._routes[entity_id] = route

        while route.waypoints and position.distance_to(route.waypoints[0]) < (
            ARRIVE_DISTANCE
        ):
            route.waypoints.pop(0)

        if not route.waypoints:
            # Either the route ran out or none was found. Push on toward
            # the player rather than standing still against the rock.
            return _toward(position, target)
        return _toward(position, route.waypoints[0])

    def waypoints(self, entity_id: str) -> list[Vector2]:
        """`entity_id`'s remaining path, for the debug overlay and tests."""
        route = self._routes.get(entity_id)
        return list(route.waypoints) if route is not None else []

    def forget(self, entity_id: str) -> None:
        """Drop `entity_id`'s path -- it died, or went back to the pool.

        Args:
            entity_id: Whose path to drop.
        """
        self._routes.pop(entity_id, None)

    def retain(self, live_ids: set[str]) -> None:
        """Drop every cached path whose owner is no longer active.

        The enemies come from a pool, so their ids are handed out again.
        Without this a respawned chaser would inherit the route its
        predecessor died holding, and set off toward a corner of the
        arena. Called once per AI tick, with the active set the tick is
        about to walk -- so a route can never outlive the enemy by more
        than the frame it died in.

        Args:
            live_ids: The enemies still on the field.
        """
        for entity_id in [key for key in self._routes if key not in live_ids]:
            del self._routes[entity_id]


def _toward(position: Vector2, target: Vector2) -> Vector2:
    """The unit vector from `position` to `target`, or zero if they meet."""
    delta = target - position
    return delta.normalize() if delta.magnitude > 0 else Vector2.zero()
