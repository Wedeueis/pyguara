"""World-space query wrapper around the bare flow-field functions.

The primitives in `flow_field.py` are graph-space (a `dict[Node, ...]`) and
stateless -- exactly right as building blocks, but every caller wanting "the
direction to steer at this world position, toward whatever I last targeted"
would otherwise re-derive the same grid<->world plumbing. This is that
plumbing, kept as a thin wrapper rather than folded into `flow_field.py`
itself so the pure graph-space functions stay reusable for non-`GridGraph`
callers too.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import cast

from pyguara.ai.pathfinding.flow_field import dijkstra_map, flow_field
from pyguara.ai.pathfinding.grid import GridGraph, GridNode
from pyguara.common.grid import cell_to_world, world_to_cell
from pyguara.common.types import Vector2


class FlowFieldService:
    """Caches one flow field over a `GridGraph` and answers world-space queries.

    Example:
        >>> service = FlowFieldService(graph)
        >>> service.recompute(goals=[prey_cell])
        >>> direction = service.vector_at(dog_transform.position, cell_size=32.0)
    """

    def __init__(self, graph: GridGraph) -> None:
        """Initialize the service over `graph`.

        No field exists until `recompute()` is called -- `vector_at()`
        returns zero vectors until then.
        """
        self._graph = graph
        self._cost_map: dict[GridNode, float] = {}
        self._field: dict[GridNode, GridNode | None] = {}

    def recompute(
        self, goals: Iterable[GridNode], max_cost: float | None = None
    ) -> None:
        """Recompute the field from scratch toward `goals`.

        Args:
            goals: Target cells (e.g. the fleeing prey's current cell).
                Forwarded to `dijkstra_map()` as multiple sources.
            max_cost: Forwarded to `dijkstra_map()`; caps how far the field
                extends.
        """
        self._cost_map = dijkstra_map(self._graph, goals, max_cost=max_cost)
        self._field = flow_field(self._graph, self._cost_map)

    def vector_at(
        self,
        world_pos: Vector2,
        cell_size: float,
        offset: Vector2 = Vector2.zero(),
    ) -> Vector2:
        """Return the normalized flow direction at `world_pos`.

        Args:
            world_pos: A world-space position to query.
            cell_size: Size of one grid cell in world units.
            offset: World offset the grid is anchored at.

        Returns:
            A unit vector toward the next cell along the field, or a zero
            vector if `world_pos`'s cell is unreached (no `recompute()` yet,
            outside `max_cost`, walled off) or is itself a goal.
        """
        cell = world_to_cell(world_pos, cell_size, offset)
        next_cell = self._field.get(cell)
        if next_cell is None:
            return Vector2(0, 0)

        direction = cell_to_world(next_cell, cell_size, offset) - cell_to_world(
            cell, cell_size, offset
        )
        if direction.length < 0.001:
            return Vector2(0, 0)
        return cast(Vector2, direction.normalized())

    def cost_at(self, cell: GridNode) -> float:
        """Return `cell`'s cached cost to the nearest goal.

        Returns:
            `math.inf` if `cell` was unreached by the last `recompute()` --
            useful for "has the prey escaped the reachable area" checks.
        """
        return self._cost_map.get(cell, math.inf)

    @property
    def is_computed(self) -> bool:
        """Whether `recompute()` has run at least once."""
        return bool(self._field)
