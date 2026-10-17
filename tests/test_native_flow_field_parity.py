"""The two flow-field stores must agree **exactly**, not approximately.

The third parity file, and the first one that can assert `==`. Its
siblings -- `test_native_particle_parity.py` and
`test_native_spark_parity.py` -- compare with a tolerance, because the
native pools hold f32 where Python holds f64 and a spark half a pixel to
the left is a spark. A flow field is not cosmetic: it is what an enemy
steers along, so one cell whose descent neighbour differs is a pack that
goes the other way round a wall, and "close" is not a property worth
having.

Three things make exactness reachable, and all three are load-bearing
rather than lucky:

1. **The arithmetic is f64 on both sides.** No conversion, no rounding.
2. **`GridGraph.get_neighbors`' order is replicated**, corner-cut refusal
   included, because `flow_field` keeps the *first* strictly-cheaper
   neighbour and the order is therefore the tie-break. Reorder
   `_NEIGHBORS_8` in either implementation and the diagonals disagree.
3. **A Dijkstra cost map is order-independent** given non-negative
   weights: a node is popped with its final cost, so every node's value is
   a `min` over its predecessors of a sum of the same floats added in the
   same order. The frontier carries the same `(cost, insertion)` total
   order as `heapq` anyway, so the pop sequence is identical too -- but it
   is point 3 that means the test may demand equality instead of hoping
   for it.

Skipped wholesale when the extension is not built, which is the normal
state for a contributor without a Rust toolchain. A green suite therefore
proves nothing about the accelerator; `cargo build --release` makes these
run.
"""

from __future__ import annotations

import math
import random

import pytest

from pyguara.ai.pathfinding.flow_field import dijkstra_map, flow_field
from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.ai.pathfinding.grid import GridGraph
from pyguara.common.types import Vector2

CELL_SIZE = 32.0


def _available() -> bool:
    """Whether the native extension is present."""
    return FlowFieldService(GridGraph(1, 1)).accelerated


pytestmark = pytest.mark.skipif(
    not _available(), reason="native extension not built; `cargo build --release`"
)


def _both(graph: GridGraph) -> tuple[FlowFieldService, FlowFieldService]:
    """A Python-backed and a native-backed service over the same graph."""
    return (
        FlowFieldService(graph, accelerate=False),
        FlowFieldService(graph, accelerate=True),
    )


def _assert_fields_agree(
    graph: GridGraph,
    goals: list[tuple[int, int]],
    max_cost: float | None = None,
) -> None:
    """Assert both stores produce the same cost and the same direction.

    Compares the cost of every cell and the steering vector at every cell
    centre, since those are the two things a caller can observe. The
    direction rather than the descent neighbour on purpose: it is what
    `vector_at` returns, so it covers the native `cell_to_world` arithmetic
    as well as the field itself.
    """
    python, native = _both(graph)
    python.recompute(goals, max_cost=max_cost)
    native.recompute(goals, max_cost=max_cost)

    assert python.is_computed == native.is_computed

    costs: list[str] = []
    directions: list[str] = []
    for y in range(graph.height):
        for x in range(graph.width):
            want, got = python.cost_at((x, y)), native.cost_at((x, y))
            if want != got:
                costs.append(f"({x},{y}) python {want!r} native {got!r}")

            centre = Vector2(x * CELL_SIZE + 1.0, y * CELL_SIZE + 1.0)
            wanted = python.vector_at(centre, CELL_SIZE)
            gotten = native.vector_at(centre, CELL_SIZE)
            if (wanted.x, wanted.y) != (gotten.x, gotten.y):
                directions.append(f"({x},{y}) python {wanted} native {gotten}")

    assert not costs, f"{len(costs)} cells cost differently: {costs[:5]}"
    assert not directions, (
        f"{len(directions)} cells steer differently: {directions[:5]}"
    )


class TestTheCostMapAndFieldAreIdentical:
    """Equality, cell by cell, over every grid shape worth distinguishing."""

    @pytest.mark.parametrize("allow_diagonal", [True, False])
    def test_an_open_grid_agrees(self, allow_diagonal: bool) -> None:
        """Both neighbourhoods, since one is a prefix of the other."""
        graph = GridGraph(20, 20, allow_diagonal=allow_diagonal)

        _assert_fields_agree(graph, [(10, 10)])

    @pytest.mark.parametrize("seed", range(6))
    def test_a_random_maze_agrees(self, seed: int) -> None:
        """The case that exercises the corner rule thousands of times.

        A quarter of the cells walled leaves plenty of diagonals with one
        flanking cell solid, which is where an implementation that merely
        checked the destination would diverge.
        """
        rng = random.Random(seed)
        graph = GridGraph(40, 40, allow_diagonal=True)
        for y in range(40):
            for x in range(40):
                if rng.random() < 0.25:
                    graph.walls.add((x, y))
        graph.walls.discard((20, 20))

        _assert_fields_agree(graph, [(20, 20)])

    def test_terrain_weights_agree(self) -> None:
        """Weights are the only place a cost stops being a sum of 1s.

        With multipliers like 3.7 the accumulated costs stop being exactly
        representable, so this is the test that would catch an `f32`
        column or a reassociated sum.
        """
        rng = random.Random(11)
        graph = GridGraph(30, 30)
        for y in range(30):
            for x in range(30):
                if rng.random() < 0.3:
                    graph.weights[(x, y)] = rng.choice([0.5, 2.0, 3.7, 9.0])

        _assert_fields_agree(graph, [(0, 0), (29, 29)])

    def test_the_diagonal_step_is_the_same_rounded_constant(self) -> None:
        """`GridGraph.cost` uses 1.414, and agreeing beats being accurate.

        Pinned as its own test because `math.sqrt(2)` is the obvious thing
        for a Rust port to reach for, it is *more* correct, and it would
        make every diagonal cost disagree in the fourth decimal -- which
        this asserts loudly rather than leaving to a maze test's output.
        """
        graph = GridGraph(3, 3, allow_diagonal=True)
        python, native = _both(graph)
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        assert python.cost_at((1, 1)) == 1.414
        assert native.cost_at((1, 1)) == 1.414

    @pytest.mark.parametrize("max_cost", [0.0, 2.0, 5.0, 1000.0])
    def test_a_cutoff_agrees(self, max_cost: float) -> None:
        """Including 0.0, where only the goals survive."""
        _assert_fields_agree(GridGraph(25, 25), [(12, 12)], max_cost=max_cost)

    def test_an_infinite_terrain_weight_agrees(self) -> None:
        """A cell nothing can afford to enter, which is still *in* the map.

        `dijkstra_map` returns a dict, so a cell behind an infinite weight
        is present at `inf` while an unreachable one is absent -- a
        distinction a flat `Vec<f64>` initialised to infinity cannot make
        on its own. `TestTheMembershipOfTheCostMap` is where that
        distinction is asserted; this is the simpler claim that the costs
        and the steering agree at all when a weight is not finite.
        """
        graph = GridGraph(6, 6, allow_diagonal=False)
        graph.weights[(3, 3)] = math.inf

        _assert_fields_agree(graph, [(0, 0)])

    def test_a_goal_on_a_wall_agrees(self) -> None:
        """`dijkstra_map` seeds a goal at 0 without asking if it is passable."""
        graph = GridGraph(12, 12)
        graph.walls.add((6, 6))

        _assert_fields_agree(graph, [(6, 6)])

    def test_a_fully_walled_grid_agrees(self) -> None:
        graph = GridGraph(8, 8)
        for y in range(8):
            for x in range(8):
                graph.walls.add((x, y))

        _assert_fields_agree(graph, [(4, 4)])

    def test_no_goals_agrees(self) -> None:
        """Nothing reached, and `is_computed` false on both."""
        _assert_fields_agree(GridGraph(8, 8), [])

    def test_a_corner_the_pack_may_not_cut_agrees(self) -> None:
        """Two walls meeting at a diagonal, which must not be passed."""
        graph = GridGraph(10, 10)
        graph.walls.update({(5, 4), (4, 5)})

        _assert_fields_agree(graph, [(0, 0)])


class TestAGoalOffTheGrid:
    """The behaviour most likely to be dropped by a flat-array port.

    `dijkstra_map` seeds every goal at cost 0 whether or not the graph
    contains it, so a goal off the edge really is in the cost map and
    really does expand into its in-bounds neighbours. It is not a
    hypothetical: the goal is usually `world_to_cell(quarry.position)`, and
    a quarry that runs off the level produces exactly this.

    A native field indexed by `y * width + x` has nowhere to put such a
    goal, so it keeps a side map for them. Without it the cells *next to*
    the goal would lose their seed and the whole field would shift.
    """

    @pytest.mark.parametrize(
        "goal",
        [(-1, 5), (-1, -1), (12, 5), (5, -1), (5, 12), (100, 100)],
        ids=["left", "corner", "right", "above", "below", "far"],
    )
    def test_an_off_grid_goal_agrees(self, goal: tuple[int, int]) -> None:
        _assert_fields_agree(GridGraph(12, 12), [goal])

    def test_one_goal_on_and_one_off_the_grid_agrees(self) -> None:
        _assert_fields_agree(GridGraph(12, 12), [(-1, 5), (6, 6)])

    def test_an_off_grid_goal_still_counts_as_computed(self) -> None:
        """`is_computed` asks whether the cost map is non-empty.

        An off-grid goal with nothing walkable beside it reaches no cell at
        all, and the Python cost map still holds one entry -- the goal. So
        the native reached-count has to include the off-grid goals, which
        is the one place that number is not simply the array's popcount.
        """
        graph = GridGraph(12, 12)
        for y in range(12):
            graph.walls.add((0, y))  # seal the column the goal borders
        python, native = _both(graph)

        python.recompute([(-1, 5)])
        native.recompute([(-1, 5)])

        assert python.is_computed is True
        assert native.is_computed is True

    def test_an_off_grid_goal_has_zero_cost_in_both(self) -> None:
        """`cost_at` is answerable for a cell the array cannot index."""
        python, native = _both(GridGraph(12, 12))
        python.recompute([(-1, 5)])
        native.recompute([(-1, 5)])

        assert python.cost_at((-1, 5)) == 0.0
        assert native.cost_at((-1, 5)) == 0.0
        assert python.cost_at((-9, -9)) == math.inf
        assert native.cost_at((-9, -9)) == math.inf


class TestTheWorldSpaceArithmetic:
    """`vector_at`'s conversion is native too, so it is compared too.

    The native `direction_at` takes `cell_size` and `offset` rather than
    returning a neighbour for Python to subtract, because the four
    `Vector2` operations after the lookup are 97% of the method's cost.
    That means the cell-centre arithmetic is duplicated in Rust, and the
    duplication has to be exact -- including doing it the long way round,
    both centres in world space and then subtract, rather than the
    algebraically equal `(nx - x) * cell_size`.
    """

    @pytest.mark.parametrize(
        ("cell_size", "offset"),
        [
            (32.0, Vector2(0.0, 0.0)),
            (33.3, Vector2(7.7, -11.1)),
            (0.1, Vector2(-1e5, 1e5)),
            (1024.0, Vector2(0.5, 0.5)),
        ],
        ids=["round", "awkward", "tiny-far", "huge"],
    )
    def test_the_direction_agrees_at_every_cell(
        self, cell_size: float, offset: Vector2
    ) -> None:
        """An odd cell size and a negative offset is where the two diverge.

        With `cell_size=32` and no offset every intermediate is exactly
        representable and a wrong formula still agrees, so the awkward
        cases are the ones doing the work.
        """
        graph = GridGraph(16, 16, allow_diagonal=True)
        graph.walls.update({(8, 7), (7, 8), (3, 3)})
        python, native = _both(graph)
        python.recompute([(8, 8)])
        native.recompute([(8, 8)])

        differing: list[str] = []
        for y in range(16):
            for x in range(16):
                centre = Vector2(
                    x * cell_size + cell_size / 2 + offset.x,
                    y * cell_size + cell_size / 2 + offset.y,
                )
                want = python.vector_at(centre, cell_size, offset)
                got = native.vector_at(centre, cell_size, offset)
                if (want.x, want.y) != (got.x, got.y):
                    differing.append(f"({x},{y}) {want} vs {got}")

        assert not differing, f"{len(differing)} differ: {differing[:5]}"

    def test_a_position_off_the_grid_is_zero_in_both(self) -> None:
        python, native = _both(GridGraph(8, 8))
        python.recompute([(4, 4)])
        native.recompute([(4, 4)])

        for position in (Vector2(-5.0, 100.0), Vector2(1e6, 1e6), Vector2(-1.0, -1.0)):
            assert python.vector_at(position, CELL_SIZE) == Vector2(0, 0)
            assert native.vector_at(position, CELL_SIZE) == Vector2(0, 0)

    def test_both_return_a_real_vector2(self) -> None:
        """Not a tuple: the native path builds the `Vector2` itself."""
        python, native = _both(GridGraph(8, 8))
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        centre = Vector2(4 * CELL_SIZE + 1, 4 * CELL_SIZE + 1)
        assert isinstance(python.vector_at(centre, CELL_SIZE), Vector2)
        assert isinstance(native.vector_at(centre, CELL_SIZE), Vector2)


class TestTheGraphIsRereadWhenItChanges:
    """The native store caches the uploaded grid; the cache must be sound.

    `recompute` re-uploads only when the graph fingerprint changed, which
    is the right optimisation -- a goal moves every tick and a wall almost
    never -- and is also exactly the shape that serves a stale answer if
    the fingerprint misses something. So each component of the fingerprint
    gets a test that changing it alone changes the field.
    """

    def test_a_wall_appearing_is_picked_up(self) -> None:
        graph = GridGraph(8, 8)
        python, native = _both(graph)
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        for y in range(8):
            graph.walls.add((4, y))

        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        assert python.cost_at((6, 6)) == math.inf  # sanity: sealed off
        assert native.cost_at((6, 6)) == math.inf

    def test_a_wall_disappearing_is_picked_up(self) -> None:
        """`PressurePlateSystem`'s case: a log opens mid-level."""
        graph = GridGraph(8, 8)
        for y in range(8):
            graph.walls.add((4, y))
        python, native = _both(graph)
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        graph.walls.discard((4, 4))

        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        assert python.cost_at((6, 6)) != math.inf
        assert native.cost_at((6, 6)) == python.cost_at((6, 6))

    def test_a_weight_changing_is_picked_up(self) -> None:
        graph = GridGraph(8, 1, allow_diagonal=False)
        python, native = _both(graph)
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        graph.weights[(4, 0)] = 7.0

        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        assert python.cost_at((5, 0)) == 11.0
        assert native.cost_at((5, 0)) == 11.0

    def test_the_diagonal_setting_changing_is_picked_up(self) -> None:
        graph = GridGraph(8, 8, allow_diagonal=True)
        python, native = _both(graph)
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        graph.allow_diagonal = False

        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        assert python.cost_at((3, 3)) == 6.0  # six orthogonal steps
        assert native.cost_at((3, 3)) == 6.0

    def test_the_grid_growing_is_picked_up(self) -> None:
        """A resized graph re-uploads rather than indexing out of range.

        The native field is a flat array sized by the last upload, so a
        grid that grew is the case where a missed re-upload is not a stale
        answer but an index error -- or, worse, a silently wrapped row.
        """
        graph = GridGraph(4, 4)
        python, native = _both(graph)
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        graph.width = 8
        graph.height = 8

        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        assert python.cost_at((7, 7)) != math.inf
        assert native.cost_at((7, 7)) == python.cost_at((7, 7))

    def test_the_grid_shrinking_is_picked_up(self) -> None:
        graph = GridGraph(8, 8)
        python, native = _both(graph)
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        graph.width = 4
        graph.height = 4

        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        assert python.cost_at((7, 7)) == math.inf
        assert native.cost_at((7, 7)) == math.inf


class TestTheMembershipOfTheCostMap:
    """`cell in cost_map` is not the same question as `cost_at(cell) < inf`.

    `dijkstra_map` returns a dict and the native field is a flat array, so
    the array needs a separate `reached` flag to answer the membership
    question. The tempting shortcut is to infer it -- a cell is in the map
    if its cost is finite -- and the shortcut is *almost* right: every
    reachable cell has a finite cost unless a terrain weight is infinite,
    and a goal is seeded at 0.0, so nothing above distinguishes the two.

    Which is exactly why this class exists and compares the field's own
    membership rather than only what the service exposes. Without it the
    shortcut would be untested rather than merely unobserved, and a later
    change that seeds a goal at a non-zero cost, or adds an infinite wall
    weight instead of a wall, would turn an unobservable difference into a
    wrong field with nothing to catch it.
    """

    def test_a_cell_reached_at_infinity_is_in_the_map(self) -> None:
        graph = GridGraph(6, 6, allow_diagonal=False)
        graph.weights[(3, 3)] = math.inf
        native = FlowFieldService(graph, accelerate=True)
        native.recompute([(0, 0)])

        cost_map = dijkstra_map(graph, [(0, 0)])

        assert (3, 3) in cost_map
        assert cost_map[(3, 3)] == math.inf
        assert native._native.is_reached(3, 3) is True

    def test_an_unreachable_cell_is_not_in_the_map(self) -> None:
        graph = GridGraph(6, 6, allow_diagonal=False)
        for y in range(6):
            graph.walls.add((3, y))
        native = FlowFieldService(graph, accelerate=True)
        native.recompute([(0, 0)])

        assert (5, 5) not in dijkstra_map(graph, [(0, 0)])
        assert native._native.is_reached(5, 5) is False

    @pytest.mark.parametrize("seed", range(4))
    def test_the_membership_and_the_descent_neighbour_match_cell_for_cell(
        self, seed: int
    ) -> None:
        """The tightest statement available: the two fields are one field.

        `_assert_fields_agree` goes through `vector_at`, which is what a
        caller sees; this compares the descent *neighbour* against
        `flow_field`'s dict directly, so a difference shows up as the cell
        it is rather than as a direction.
        """
        rng = random.Random(seed)
        graph = GridGraph(24, 24, allow_diagonal=True)
        for y in range(24):
            for x in range(24):
                if rng.random() < 0.2:
                    graph.walls.add((x, y))
                elif rng.random() < 0.2:
                    graph.weights[(x, y)] = rng.choice([0.5, 2.0, 3.7])
        graph.walls.discard((12, 12))
        native = FlowFieldService(graph, accelerate=True)
        native.recompute([(12, 12)])

        cost_map = dijkstra_map(graph, [(12, 12)])
        field = flow_field(graph, cost_map)

        differing: list[str] = []
        for y in range(24):
            for x in range(24):
                reached = native._native.is_reached(x, y)
                if reached != ((x, y) in cost_map):
                    differing.append(f"({x},{y}) membership {reached}")
                if native._native.next_cell(x, y) != field.get((x, y)):
                    differing.append(
                        f"({x},{y}) next {native._native.next_cell(x, y)} "
                        f"vs {field.get((x, y))}"
                    )

        assert not differing, f"{len(differing)} differ: {differing[:5]}"


class TestTheStoreIsOptional:
    def test_the_python_service_keeps_its_dicts_and_the_native_one_does_not(
        self,
    ) -> None:
        """Opacity, asserted rather than described.

        The whole reason this port is cheap is that nothing outside reads a
        cell: the native field never materialises `_cost_map` or `_field`,
        so a consumer that reached past `cost_at`/`vector_at` would be
        silently reading an empty dict. Nothing does today, and this is
        what notices when something starts.
        """
        graph = GridGraph(8, 8)
        python, native = _both(graph)
        python.recompute([(0, 0)])
        native.recompute([(0, 0)])

        assert python._cost_map and python._field
        assert not native._cost_map and not native._field

    def test_forcing_the_python_store_is_honoured_even_with_the_extension(
        self,
    ) -> None:
        """`accelerate=False` is what the whole file depends on."""
        service = FlowFieldService(GridGraph(4, 4), accelerate=False)

        assert service.accelerated is False
