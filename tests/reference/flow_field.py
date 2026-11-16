"""The flow-field service as plain Python, for the Rust one to be held to.

Built on `dijkstra_map` and `flow_field`, the generic graph functions the
engine still ships for graphs that are not grids. `FlowFieldService`
computes the same field natively and must agree with this bit for bit.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import cast

from pyguara.ai.pathfinding.flow_field import dijkstra_map, flow_field
from pyguara.ai.pathfinding.grid import GridGraph, GridNode
from pyguara.common.grid import cell_to_world, world_to_cell
from pyguara.common.types import Vector2


class ReferenceFlowField:
    """Answers what `FlowFieldService` answers, from two dicts."""

    def __init__(self, graph: GridGraph) -> None:
        """Hold `graph`; no field exists until `recompute()`."""
        self._graph = graph
        self.cost_map: dict[GridNode, float] = {}
        self.field: dict[GridNode, GridNode | None] = {}

    def recompute(
        self, goals: Iterable[GridNode], max_cost: float | None = None
    ) -> None:
        """Compute the field toward `goals`, every time it is asked."""
        self.cost_map = dijkstra_map(self._graph, frozenset(goals), max_cost=max_cost)
        self.field = flow_field(self._graph, self.cost_map)

    def vector_at(
        self,
        world_pos: Vector2,
        cell_size: float,
        offset: Vector2 = Vector2.zero(),
    ) -> Vector2:
        """Return the unit direction at `world_pos`, or zero."""
        cell = world_to_cell(world_pos, cell_size, offset)
        next_cell = self.field.get(cell)
        if next_cell is None:
            return Vector2(0, 0)

        direction = cell_to_world(next_cell, cell_size, offset) - cell_to_world(
            cell, cell_size, offset
        )
        if direction.length < 0.001:
            return Vector2(0, 0)
        return cast(Vector2, direction.normalized())

    def cost_at(self, cell: GridNode) -> float:
        """Return `cell`'s cost to the nearest goal, or infinity."""
        return self.cost_map.get(cell, math.inf)

    @property
    def is_computed(self) -> bool:
        """Whether the last `recompute()` reached any cell."""
        return bool(self.field)
