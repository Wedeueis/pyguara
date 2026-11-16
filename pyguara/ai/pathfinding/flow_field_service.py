"""A cached flow field over a `GridGraph`, queried in world space.

The field is computed and held in Rust: a `GridGraph` is flat integer
state, and nothing outside this class reads a cell, so the cost map and
the descent field never come back to Python and only a query crosses
the boundary. See `docs/adr/0011-one-rust-engine-python-interface.md`.

For a graph that is not a grid, `flow_field.py` has the same two steps
as plain functions over any `Graph[Node]`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from pyguara.ai.pathfinding.grid import GridGraph, GridNode
from pyguara.common.grid import world_to_cell
from pyguara.common.types import Vector2
from pyguara.native import require_extension

# Dimensions, topology and the mutable content: see `_graph_key`.
_GraphKey = tuple[
    int,
    int,
    bool,
    frozenset[GridNode],
    frozenset[tuple[GridNode, float]],
]

# The goals and cutoff, then the graph: see `FlowFieldService._key`.
_FieldKey = tuple[frozenset[GridNode], float | None, _GraphKey]


class FlowFieldService:
    """Caches one flow field over a `GridGraph` and answers world-space queries.

    The field lives in the native extension, which this class needs: it
    has no Python fallback, and `native_acceleration` and
    `PYGUARA_NO_NATIVE` do not apply to it.

    Example:
        >>> service = FlowFieldService(graph)
        >>> service.recompute(goals=[prey_cell])
        >>> direction = service.vector_at(dog_transform.position, cell_size=32.0)
    """

    def __init__(self, graph: GridGraph) -> None:
        """Initialize the service over `graph`.

        No field exists until `recompute()` is called -- `vector_at()`
        returns zero vectors until then.

        Args:
            graph: The grid to navigate. Read on every genuine recompute
                rather than copied, so a runtime mutation (a pressure plate
                opening a gate) is picked up without the caller saying
                anything.

        Raises:
            RuntimeError: If the native extension cannot be imported.
        """
        self._graph = graph
        self._computed_for: _FieldKey | None = None
        self._native: Any = require_extension("FlowFieldService").NativeFlowField()
        self._uploaded: _GraphKey | None = None
        self._reached = 0

    def _graph_key(self) -> _GraphKey:
        """Return the graph's content as one hashable value.

        Separate from `_key` because the two halves are compared apart:
        the goals change almost every tick and the graph almost never, so
        a moved goal re-uploads nothing.
        """
        graph = self._graph
        return (
            graph.width,
            graph.height,
            graph.allow_diagonal,
            frozenset(graph.walls),
            frozenset(graph.weights.items()),
        )

    def _key(self, goals: frozenset[GridNode], max_cost: float | None) -> _FieldKey:
        """Everything the resulting field depends on, as one hashable value.

        The graph is included by content, not by identity. A `GridGraph` is
        mutated at runtime (a gate opening removes cells from `walls`), so a
        key covering only the goals would serve a field for walls that have
        changed. Hashing the walls and weights is O(cells) and a small
        fraction of a recompute.

        Args:
            goals: The target cells, already collected.
            max_cost: The cutoff, if any.

        Returns:
            A hashable key equal between two calls exactly when the field
            they would compute is the same.
        """
        return (goals, max_cost, self._graph_key())

    def _upload(self) -> None:
        """Flatten the graph's walls and weights into the native field.

        Row-major arrays over in-bounds cells only. `GridGraph.walls` and
        `.weights` accept any coordinate, but every read of them is guarded by
        `in_bounds`, so dropping out-of-bounds entries changes no result.
        """
        graph = self._graph
        width, height = graph.width, graph.height
        cells = width * height
        blocked = [False] * cells
        weights = [1.0] * cells
        for x, y in graph.walls:
            if 0 <= x < width and 0 <= y < height:
                blocked[y * width + x] = True
        for (x, y), weight in graph.weights.items():
            if 0 <= x < width and 0 <= y < height:
                weights[y * width + x] = weight
        self._native.set_grid(width, height, graph.allow_diagonal, blocked, weights)

    def recompute(
        self, goals: Iterable[GridNode], max_cost: float | None = None
    ) -> bool:
        """Recompute the field toward `goals`, unless it already holds it.

        Safe to call every tick. The call is skipped when the goals and the
        graph's contents are the same as the last time, so mutating the graph
        is picked up without the caller saying anything.

        Args:
            goals: Target cells (e.g. the fleeing prey's current cell).
                Order and duplicates are irrelevant -- each is seeded at
                cost 0 -- so they are compared as a set.
            max_cost: Caps how far the field extends; a cell that costs
                more is left unreached.

        Returns:
            True if the field was computed, False if the cached one already
            answers for these arguments.
        """
        collected = frozenset(goals)
        graph_key = self._graph_key()
        key: _FieldKey = (collected, max_cost, graph_key)
        if key == self._computed_for:
            return False

        if graph_key != self._uploaded:
            self._upload()
            self._uploaded = graph_key
        self._reached = self._native.recompute(list(collected), max_cost)
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
        # One crossing for the lookup and the cell-centre arithmetic: the
        # `Vector2` operations after the lookup are nearly all of this
        # method's cost, and a steering agent calls it every tick.
        step_x, step_y = self._native.direction_at(
            cell[0], cell[1], cell_size, offset.x, offset.y
        )
        return Vector2(step_x, step_y)

    def cost_at(self, cell: GridNode) -> float:
        """Return `cell`'s cached cost to the nearest goal.

        Returns:
            `math.inf` if `cell` was unreached by the last `recompute()` --
            useful for "has the prey escaped the reachable area" checks.
        """
        return cast(float, self._native.cost_at(cell[0], cell[1]))

    @property
    def is_computed(self) -> bool:
        """Whether `recompute()` has run at least once."""
        return self._reached > 0
