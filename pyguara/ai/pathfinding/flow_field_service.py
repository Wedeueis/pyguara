"""World-space query wrapper around the bare flow-field functions.

The functions in `flow_field.py` work on any `Graph[Node]` and hold no
state. This wraps them for a `GridGraph`: it caches one field and
converts between world positions and cells.

It is also where the native accelerator lives, because a `GridGraph`
is flat integer state a native implementation can hold. See
`docs/adr/0004-the-native-boundary.md`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, cast

from pyguara.ai.pathfinding.flow_field import dijkstra_map, flow_field
from pyguara.ai.pathfinding.grid import GridGraph, GridNode
from pyguara.common.grid import cell_to_world, world_to_cell
from pyguara.common.types import Vector2
from pyguara.native import native_module

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

    Uses the native extension when it is available. The cost map and the
    descent field stay native and only a query crosses the boundary. The
    native field is bit-exact with the Python one.

    Example:
        >>> service = FlowFieldService(graph)
        >>> service.recompute(goals=[prey_cell])
        >>> direction = service.vector_at(dog_transform.position, cell_size=32.0)
    """

    def __init__(self, graph: GridGraph, *, accelerate: bool | None = None) -> None:
        """Initialize the service over `graph`.

        No field exists until `recompute()` is called -- `vector_at()`
        returns zero vectors until then.

        Args:
            graph: The grid to navigate. Read on every genuine recompute
                rather than copied, so a runtime mutation (a pressure plate
                opening a gate) is picked up without the caller saying
                anything.
            accelerate: Whether to compute the field natively. None, the
                default, defers to the engine-wide setting --
                `PerformanceConfig.native_acceleration`, resolved once at
                bootstrap -- so a game decides this in one place rather
                than per service. True demands the extension and raises if
                it is missing; False forces the Python path. Both are
                overrides for tests and for the parity suite, not a second
                configuration surface.

        Raises:
            RuntimeError: If `accelerate=True` and the extension is absent.
        """
        self._graph = graph
        self._cost_map: dict[GridNode, float] = {}
        self._field: dict[GridNode, GridNode | None] = {}
        self._computed_for: _FieldKey | None = None

        native = native_module() if accelerate is not False else None
        if accelerate and native is None:
            raise RuntimeError(
                "accelerate=True but the native extension is not available. "
                "Build it with `cargo build --release`, or leave "
                "`accelerate` unset to fall back to Python."
            )
        self._native: Any | None = native.NativeFlowField() if native else None
        self._uploaded: _GraphKey | None = None
        self._reached = 0

    @property
    def accelerated(self) -> bool:
        """Whether this service computes its field natively."""
        return self._native is not None

    def _graph_key(self) -> _GraphKey:
        """Return the graph's content as one hashable value.

        Separate from `_key` because the native path needs the two halves
        apart: the goals change almost every tick and the graph almost
        never, so comparing them separately means a moved goal re-uploads
        nothing. On the Python path the split is invisible.
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
        assert self._native is not None
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
                Forwarded to `dijkstra_map()` as multiple sources. Order
                and duplicates are irrelevant -- each is seeded at cost 0 --
                so they are compared as a set.
            max_cost: Forwarded to `dijkstra_map()`; caps how far the field
                extends.

        Returns:
            True if the field was computed, False if the cached one already
            answers for these arguments.
        """
        collected = frozenset(goals)
        graph_key = self._graph_key()
        key: _FieldKey = (collected, max_cost, graph_key)
        if key == self._computed_for:
            return False

        if self._native is not None:
            if graph_key != self._uploaded:
                self._upload()
                self._uploaded = graph_key
            self._reached = self._native.recompute(list(collected), max_cost)
        else:
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
        if self._native is not None:
            # The whole body below, in one crossing. Worth doing natively
            # even though the lookup is a dict access: the four `Vector2`
            # operations after it are 97% of this method's 3.27 us, and
            # a steering agent calls it every tick.
            step_x, step_y = self._native.direction_at(
                cell[0], cell[1], cell_size, offset.x, offset.y
            )
            return Vector2(step_x, step_y)

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
        if self._native is not None:
            return cast(float, self._native.cost_at(cell[0], cell[1]))
        return self._cost_map.get(cell, math.inf)

    @property
    def is_computed(self) -> bool:
        """Whether `recompute()` has run at least once."""
        if self._native is not None:
            return self._reached > 0
        return bool(self._field)
