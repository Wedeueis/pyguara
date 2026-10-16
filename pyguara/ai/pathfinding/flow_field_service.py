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

# Goals, cutoff, and the graph by content: see `FlowFieldService._key`.
_FieldKey = tuple[
    frozenset[GridNode],
    float | None,
    int,
    int,
    bool,
    frozenset[GridNode],
    frozenset[tuple[GridNode, float]],
]


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
        self._computed_for: _FieldKey | None = None

    def _key(self, goals: frozenset[GridNode], max_cost: float | None) -> _FieldKey:
        """Everything the resulting field depends on, as one hashable value.

        The graph is included **by content**, not by identity, and that is
        the whole safety argument for the skip in `recompute()`. A
        `GridGraph` is mutable and really is mutated at runtime -- a
        pressure plate opening a gate removes that gate's cells from
        `walls` mid-level -- so a key that covered only the goals would
        serve a field that steers through a wall that is still there, or
        around one that is gone. That is the "guard that returns a wrong
        answer" shape, and worth more than the recompute it saves.

        Hashing the walls and the weights is O(cells), which sounds like
        the thing being avoided and is not: measured at **0.03-0.06% of a
        recompute** (2.7 us against 5.0 ms on a 30x20 grid, 77 us against
        241 ms on 160x160). Soundness is therefore free, and -- more
        valuable than the speed -- there is no invalidation contract for a
        caller to forget.

        Args:
            goals: The target cells, already collected.
            max_cost: The cutoff, if any.

        Returns:
            A hashable key equal between two calls exactly when the field
            they would compute is the same.
        """
        graph = self._graph
        return (
            goals,
            max_cost,
            graph.width,
            graph.height,
            graph.allow_diagonal,
            frozenset(graph.walls),
            frozenset(graph.weights.items()),
        )

    def recompute(
        self, goals: Iterable[GridNode], max_cost: float | None = None
    ) -> bool:
        """Recompute the field toward `goals`, unless it already holds it.

        Safe and cheap to call every tick, which is what callers do: a
        system steering toward a moving target has no way to know whether
        the target crossed a cell boundary this frame, so it asks for a
        recompute and this decides.

        That is a change of behaviour from "always recompute", and the
        reason is that a recompute is expensive enough to matter --
        `dijkstra_map` plus the descent pass is 5.0 ms on a 30x20 grid and
        83.8 ms on 96x96, so an unconditional per-tick call costs 30% of a
        frame budget on the small one and is simply impossible on the
        larger. See `docs/guides/performance.md`.

        The skip is keyed on the goals **and a fingerprint of the graph**,
        so mutating the graph is picked up without the caller saying
        anything; `_key` explains why that is affordable.

        Args:
            goals: Target cells (e.g. the fleeing prey's current cell).
                Forwarded to `dijkstra_map()` as multiple sources. Order
                and duplicates are irrelevant -- each is seeded at cost 0 --
                so they are compared as a set.
            max_cost: Forwarded to `dijkstra_map()`; caps how far the field
                extends.

        Returns:
            True if the field was computed, False if the cached one already
            answers for these arguments. Mostly useful for a caller that
            wants to log or meter its own recompute rate, and for the tests
            that pin this behaviour.
        """
        collected = frozenset(goals)
        key = self._key(collected, max_cost)
        if key == self._computed_for:
            return False

        self._cost_map = dijkstra_map(self._graph, collected, max_cost=max_cost)
        self._field = flow_field(self._graph, self._cost_map)
        self._computed_for = key
        return True

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
