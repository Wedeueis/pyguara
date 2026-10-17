"""World-space query wrapper around the bare flow-field functions.

The primitives in `flow_field.py` are graph-space (a `dict[Node, ...]`) and
stateless -- exactly right as building blocks, but every caller wanting "the
direction to steer at this world position, toward whatever I last targeted"
would otherwise re-derive the same grid<->world plumbing. This is that
plumbing, kept as a thin wrapper rather than folded into `flow_field.py`
itself so the pure graph-space functions stay reusable for non-`GridGraph`
callers too.

This is also the engine's *native boundary* for pathfinding, and the two
facts are related: the wrapper is where the grid stops being generic. A
`GridGraph` is flat integer state with a wall mask and a weight per cell,
which is exactly what a native implementation can hold, while
`Graph[Node]` is a Python protocol whose `get_neighbors` could be anything.
So `dijkstra_map` and `flow_field` stay generic and stay in Python, and the
accelerator lives here. See `docs/adr/0004-the-native-boundary.md`.
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

    Backed by the optional native extension when it is available, which is
    **63x** on a 96x96 recompute -- 85 ms down to 1.36 ms, or 516% of a
    frame budget down to 8%. That is the largest single margin in the
    engine, and the reason is that the field is *opaque*: nothing outside
    reads an individual cell, so the cost map and the descent field both
    stay native and only a query crosses. The native path is bit-exact
    with the Python one rather than merely close, because this field steers
    gameplay; `tests/test_native_flow_field_parity.py` asserts that cell by
    cell.

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
        return (goals, max_cost, self._graph_key())

    def _upload(self) -> None:
        """Flatten the graph's walls and weights into the native field.

        Row-major arrays over in-bounds cells only. Dropping out-of-bounds
        entries is safe rather than lossy: `GridGraph.walls` and `.weights`
        are plain dicts and sets that accept any coordinate, but every read
        of them in `get_neighbors` and `cost` is guarded by `in_bounds`, so
        an off-grid wall has never affected a result.

        Measured at 0.18 ms for 96x96, against the 1.36 ms recompute it
        precedes -- and it is skipped entirely when the graph has not
        changed since the last one.
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

        Safe and cheap to call every tick, which is what callers do: a
        system steering toward a moving target has no way to know whether
        the target crossed a cell boundary this frame, so it asks for a
        recompute and this decides.

        That is a change of behaviour from "always recompute", and the
        reason is that a recompute is expensive enough to matter -- in
        Python, `dijkstra_map` plus the descent pass is 5.0 ms on a 30x20
        grid and 85 ms on 96x96, so an unconditional per-tick call costs
        30% of a frame budget on the small one and is simply impossible on
        the larger. The native path brings 96x96 to 1.36 ms, which changes
        how bad a genuine recompute is without making the skip pointless.
        See `docs/guides/performance.md`.

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
