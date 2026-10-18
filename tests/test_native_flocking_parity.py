"""Do the two flocking stores agree, and in what sense?

The third parity suite, and the first that cannot simply assert `==`.
`tests/test_native_flow_field_parity.py` compares 9216 cells exactly;
this one cannot, and the reason is worth stating precisely because it
decides what these tests are allowed to claim.

`SpatialHash._cells` is a `dict[Cell, set[int]]`, and a radius query
yields each cell's members in **CPython set iteration order** -- a
function of the slot numbers, the table size and the insertion history.
`flock_force` then sums over them, and float addition is not
associative, so a different order gives a different last bit. Measured
over 1000 agents: 46% of agents get a different force, worst relative
difference 6.4e-13.

That is not "Python is right and the native store is close". Both sum
the same numbers correctly; the Python answer is not canonical, because
it is whatever CPython's set internals happen to produce. The sharper
version of the same fact: a seeded flock does not even tick the same way
twice *in Python*, because `EntityManager` hands out random uuid4 ids
and `get_entities_with_cached` iterates a set of them, so the
Gauss-Seidel sweep order differs between processes. There is no single
Python answer to be bit-exact to.

So this file asserts three different things, and keeping them apart is
the point:

1. **The neighbourhoods agree exactly.** Order is free; membership is
   not. `query_radius` confirms every candidate against an exact squared
   distance, so who is a flockmate is a property of the positions alone.
   A tolerance on forces could hide a wrong neighbourhood; comparing
   `neighbour_counts()` cannot.
2. **The arithmetic agrees exactly, where ordering cannot intrude.**
   A transcription slip -- `dx * (s / len)` for `(dx / len) * s` -- moves
   a result about one ulp, three orders of magnitude *below* the
   ordering noise, so no tolerance wide enough for the ordering could
   ever catch one. These tests therefore use constructed geometry in
   which no agent has more than one flockmate, where the sum has no
   order to differ in, and assert `==` through every branch: clamping,
   coincident agents, seek, staggering, 40 ticks.
3. **The forces agree within summation noise**, on real flocks, with the
   tolerance stated and one permitted cause.

Note what (2) is *not*: picking the agents with one neighbour out of a
random flock. That leaks, because a lone agent reads its neighbour's
live position, and that neighbour may itself have been perturbed --
measured at 47 of 48 agreeing, with the one exception inheriting a
flockmate's divergence. The geometry has to be built so that nothing in
the world is perturbed at all.

All of it skips when the extension is absent, so a contributor without
Rust sees a green suite having tested none of it.
"""

from __future__ import annotations

import pytest

import pyguara.ai.flocking_system as flocking_module
from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.native import native_module

pytestmark = pytest.mark.skipif(
    native_module() is None,
    reason="native extension not built; `cargo build --release`",
)

DT = 1.0 / 60.0
CELL = 64.0

# Comfortably above the measured 6.4e-13 of summation noise and far
# below anything a flock could express. Tightening it would make the
# suite flaky for no gain; it is not the test that pins the arithmetic
# -- `TestTheArithmeticIsExact` is, with `==`.
TOLERANCE = 1e-9

# Far enough apart that no agent in one group is within any other
# group's `neighbor_radius`, so each group is its own world.
APART = 10_000.0


def _world(
    layout: list[tuple[Vector2, Vector2]], **agent_kwargs: object
) -> tuple[EntityManager, list[FlockingAgent], list[Transform]]:
    """Build a flock from explicit `(position, velocity)` pairs."""
    manager = EntityManager()
    for position, velocity in layout:
        entity = manager.create_entity()
        entity.add_component(Transform(position=position))
        entity.add_component(FlockingAgent(velocity=velocity, **agent_kwargs))  # type: ignore[arg-type]
    # Registering the cached query is the system's job, so build one and
    # read the components back in the order the system will see them.
    FlockingSystem(manager, accelerate=False)
    entities = list(manager.get_entities_with_cached(FlockingAgent, Transform))
    return (
        manager,
        [entity.get_component(FlockingAgent) for entity in entities],
        [entity.get_component(Transform) for entity in entities],
    )


def _scattered(
    count: int, spread: float, seed: int = 1234
) -> list[tuple[Vector2, Vector2]]:
    """A pseudo-random flock, as the perf suite builds one."""
    rng = RandomStream(seed)
    return [
        (
            Vector2(rng.uniform(0.0, spread), rng.uniform(0.0, spread)),
            Vector2(rng.uniform(-40.0, 40.0), rng.uniform(-40.0, 40.0)),
        )
        for _ in range(count)
    ]


def _pairs(
    count: int, separation: float, *, moving: bool = True
) -> list[tuple[Vector2, Vector2]]:
    """`count` isolated pairs, each agent with exactly one flockmate.

    Args:
        count: How many pairs.
        separation: How far apart the two agents of a pair are.
        moving: Whether the agents start with a velocity. `False`
            matters more than it looks: a one-ulp error in the force
            becomes `acceleration * steering_dt`, which at 1/60 of a
            second is some four orders of magnitude smaller than a
            typical velocity -- small enough to round away entirely in
            `velocity + acceleration * dt`. Starting from rest makes the
            acceleration term the whole of the new velocity, so the ulp
            survives to be compared. See `test_a_heavier_agent`.
    """
    first = Vector2(7.0, 3.0) if moving else Vector2(0.0, 0.0)
    second = Vector2(-2.0, 9.0) if moving else Vector2(0.0, 0.0)
    layout = []
    for index in range(count):
        base = index * APART
        layout.append((Vector2(base, 0.0), first))
        layout.append((Vector2(base + separation, 10.0), second))
    return layout


def _singles(count: int) -> list[tuple[Vector2, Vector2]]:
    """`count` agents with no flockmate at all."""
    return [
        (Vector2(index * APART, 0.0), Vector2(10.0, -5.0)) for index in range(count)
    ]


def _state(
    agents: list[FlockingAgent], transforms: list[Transform]
) -> list[tuple[float, float, float, float]]:
    """Everything a tick is allowed to change, by slot."""
    return [
        (
            transform.position.x,
            transform.position.y,
            agent.velocity.x,
            agent.velocity.y,
        )
        for agent, transform in zip(agents, transforms, strict=True)
    ]


def _restore(
    state: list[tuple[float, float, float, float]],
    agents: list[FlockingAgent],
    transforms: list[Transform],
) -> None:
    """Put a world back exactly as it was."""
    for (x, y, vx, vy), agent, transform in zip(state, agents, transforms, strict=True):
        transform.position = Vector2(x, y)
        agent.velocity = Vector2(vx, vy)


def _both(
    layout: list[tuple[Vector2, Vector2]],
    *,
    ticks: int = 1,
    groups: int = 1,
    **agent_kwargs: object,
) -> tuple[
    list[tuple[float, float, float, float]], list[tuple[float, float, float, float]]
]:
    """Tick **one** world each way, and return the two end states.

    One world, not two built from the same seed. Two managers hand out
    different uuid4 ids, so `get_entities_with_cached` enumerates them in
    a different order, and slot `n` is then a different agent in each --
    which makes a slot-by-slot comparison meaningless and, because the
    sweep is Gauss-Seidel, actually simulates something different.
    """
    manager, agents, transforms = _world(layout, **agent_kwargs)
    start = _state(agents, transforms)

    python = FlockingSystem(manager, cell_size=CELL, groups=groups, accelerate=False)
    for _ in range(ticks):
        python.update(DT)
    after_python = _state(agents, transforms)

    _restore(start, agents, transforms)
    native = FlockingSystem(manager, cell_size=CELL, groups=groups, accelerate=True)
    for _ in range(ticks):
        native.update(DT)
    return after_python, _state(agents, transforms)


def _assert_close(
    python: list[tuple[float, float, float, float]],
    native: list[tuple[float, float, float, float]],
) -> None:
    """Agree to `TOLERANCE`, relative where the value is big enough."""
    assert len(python) == len(native)
    for slot, (left, right) in enumerate(zip(python, native, strict=True)):
        for index, (expected, actual) in enumerate(zip(left, right, strict=True)):
            scale = max(abs(expected), 1.0)
            assert abs(expected - actual) <= TOLERANCE * scale, (
                f"slot {slot}, component {index}: {expected!r} vs {actual!r}"
            )


class TestThePythonPathIsPythonAllTheWayDown:
    """`accelerate=False` has to mean it in what the system builds too.

    `FlockingSystem`'s Python path constructs its own `SpatialHash` every
    tick. That hash grew a native store, so unless the system passes
    `accelerate=False` down, `FlockingSystem(accelerate=False)` indexes
    natively -- which is not the Python path, measures 9.8 ms where the
    Python tick is 16.4 ms, and puts native code inside the reference
    `_python_counts` builds for this very file.

    It happened, and nothing caught it: of 23 sabotages run against this
    increment, removing that one argument was the only survivor. This is
    the test that was missing.
    """

    def test_the_index_the_python_path_builds_is_python(self) -> None:
        """Spy on the construction, because the hash is a local."""
        constructed: list[SpatialHash[int]] = []
        original = flocking_module.SpatialHash

        def recording(*args: object, **kwargs: object) -> SpatialHash[int]:
            index = original(*args, **kwargs)  # type: ignore[arg-type]
            constructed.append(index)
            return index

        manager, agents, transforms = _world(
            [
                (Vector2(0.0, 0.0), Vector2(1.0, 0.0)),
                (Vector2(10.0, 0.0), Vector2(0.0, 0.0)),
            ]
        )
        system = FlockingSystem(manager, accelerate=False)
        flocking_module.SpatialHash = recording  # type: ignore[assignment]
        try:
            system.update(DT)
        finally:
            flocking_module.SpatialHash = original  # type: ignore[assignment]

        assert constructed, "the Python path built no index at all"
        assert all(not index.accelerated for index in constructed), (
            "FlockingSystem(accelerate=False) built a native index. The "
            "Python path has to be Python all the way down -- see this "
            "class's docstring."
        )

    def test_the_spy_would_notice_a_native_index(self) -> None:
        """Guards the guard: the assertion above can actually fail.

        If `accelerated` ever stopped reporting the truth, the test above
        would pass against a native index and prove nothing.
        """
        assert SpatialHash[int](accelerate=True).accelerated is True
        assert SpatialHash[int](accelerate=False).accelerated is False


class TestTheNeighbourhoodsAgreeExactly:
    """Who counts as a flockmate is order-independent, so `==` applies.

    This is the structural half of parity, and the half a force
    comparison cannot do. Two stores finding *different* neighbours would
    still produce similar forces on a dense flock -- one extra flockmate
    out of six moves a mean a little -- and a 1e-9 tolerance would wave
    it through. These compare the counts instead.
    """

    @staticmethod
    def _python_counts(
        agents: list[FlockingAgent], transforms: list[Transform], cell_size: float
    ) -> list[int]:
        """What `FlockingSystem._neighbors_of` would yield per agent.

        Rebuilt here from `SpatialHash` directly rather than instrumented
        out of the system, so the comparison is against the Python
        implementation's own definition of a neighbourhood.

        `accelerate=False` is what makes that true, and it is load-bearing
        rather than tidy: `SpatialHash` grew a native store of its own, so
        an unpinned one here would compare the native grid against itself
        and this file's first tier would assert nothing.
        """
        spatial_hash: SpatialHash[int] = SpatialHash(
            cell_size=cell_size, accelerate=False
        )
        for slot, transform in enumerate(transforms):
            spatial_hash.insert(slot, transform.position)
        return [
            sum(
                1
                for found in spatial_hash.query_radius(
                    transforms[slot].position, agent.neighbor_radius
                )
                if found != slot
            )
            for slot, agent in enumerate(agents)
        ]

    def _assert_counts_agree(
        self,
        layout: list[tuple[Vector2, Vector2]],
        *,
        cell_size: float = CELL,
        **agent_kwargs: object,
    ) -> None:
        manager, agents, transforms = _world(layout, **agent_kwargs)
        expected = self._python_counts(agents, transforms, cell_size)

        system = FlockingSystem(manager, cell_size=cell_size, accelerate=True)
        system.update(DT)

        assert list(system._native.neighbour_counts()) == expected  # noqa: SLF001

    @pytest.mark.parametrize("count", [1, 2, 7, 60, 400])
    def test_a_scattered_flock(self, count: int) -> None:
        self._assert_counts_agree(_scattered(count, spread=max(count, 2) * 18.0))

    def test_a_clumped_flock(self) -> None:
        """Every agent inside everyone else's radius, so k is n."""
        self._assert_counts_agree(_scattered(80, spread=40.0))

    @pytest.mark.parametrize("cell_size", [4.0, 17.0, 64.0, 80.0, 512.0])
    def test_a_cell_size_unrelated_to_the_radius(self, cell_size: float) -> None:
        """The grid's bucketing must not change who is a flockmate.

        The native grid buckets cells by a hash and resolves collisions
        by not resolving them -- two cells sharing a bucket only means a
        query sees agents it did not ask about, which the exact distance
        test then rejects. A cell size far from the radius is what makes
        collisions and multi-cell queries common, so this is the test
        that argument has to survive.
        """
        self._assert_counts_agree(_scattered(120, spread=600.0), cell_size=cell_size)

    @pytest.mark.parametrize("radius", [0.0, 1.0, 63.9, 64.0, 64.1, 1000.0])
    def test_a_radius_on_and_around_a_cell_boundary(self, radius: float) -> None:
        self._assert_counts_agree(_scattered(120, spread=600.0), neighbor_radius=radius)

    def test_negative_coordinates(self) -> None:
        """`floor` of a negative quotient, which truncation would get wrong."""
        layout = [
            (Vector2(x, y), Vector2(1.0, 1.0))
            for x in (-300.0, -64.1, -64.0, -63.9, -0.1, 0.0, 0.1, 64.0, 300.0)
            for y in (-128.0, -1.0, 0.0, 1.0, 128.0)
        ]
        self._assert_counts_agree(layout)

    def test_a_flockmate_exactly_on_the_radius(self) -> None:
        """`<=`, not `<`, and the one boundary that is observable.

        Chosen so "exactly" means it: 64 and 80 are exact in binary, and
        so are 64*64 and 80*80, so the squared comparison is against
        equal values rather than nearly-equal ones.

        Most boundary slips in this algorithm turn out not to be
        observable at all -- a flockmate exactly on the *separation*
        radius contributes `(1 - d/r) * max_speed`, which is exactly
        zero, and a clamp triggered exactly at its threshold scales by
        exactly 1.0. This one is different, because including or
        excluding a flockmate changes `count`, and `count` divides the
        cohesion and alignment means.
        """
        layout = [
            (Vector2(0.0, 0.0), Vector2(1.0, 2.0)),
            (Vector2(64.0, 0.0), Vector2(3.0, -1.0)),  # exactly on it
            (Vector2(0.0, 80.0), Vector2(-2.0, 4.0)),  # exactly on a bigger one
        ]
        self._assert_counts_agree(layout, neighbor_radius=64.0)
        self._assert_counts_agree(layout, neighbor_radius=80.0)

    def test_a_flockmate_a_hair_either_side_of_the_radius(self) -> None:
        """The same boundary approached from both directions."""
        for offset in (-1e-9, 0.0, 1e-9):
            self._assert_counts_agree(
                [
                    (Vector2(0.0, 0.0), Vector2(1.0, 2.0)),
                    (Vector2(64.0 + offset, 0.0), Vector2(3.0, -1.0)),
                ],
                neighbor_radius=64.0,
            )

    def test_coincident_agents(self) -> None:
        self._assert_counts_agree(
            [(Vector2(50.0, 50.0), Vector2(3.0, 0.0)) for _ in range(6)]
        )

    def test_a_disabled_agent_is_still_a_flockmate(self) -> None:
        """It does not steer, but others steer by it.

        `FlockingSystem` indexes every transform into the hash before
        checking `enabled`, so a disabled agent contributes to its
        neighbours' forces. Easy to lose in a port, and invisible until a
        flock drifts past a frozen one.
        """
        manager, agents, transforms = _world(_scattered(40, spread=200.0))
        for agent in agents[::3]:
            agent.enabled = False
        expected = self._python_counts(agents, transforms, CELL)

        system = FlockingSystem(manager, cell_size=CELL, accelerate=True)
        system.update(DT)

        counts = list(system._native.neighbour_counts())  # noqa: SLF001
        for slot, agent in enumerate(agents):
            if agent.enabled:
                assert counts[slot] == expected[slot]
            else:
                assert counts[slot] == 0


class TestTheArithmeticIsExact:
    """`==`, on geometry where the summation has no order to differ in.

    Every test here builds a world in which no agent has more than one
    flockmate. That removes the only permitted source of divergence, so
    anything left is a transcription error -- and a transcription error
    is about one ulp, which the tolerance tests could never see.
    """

    def _assert_identical(
        self,
        layout: list[tuple[Vector2, Vector2]],
        *,
        ticks: int = 1,
        groups: int = 1,
        **agent_kwargs: object,
    ) -> None:
        python, native = _both(layout, ticks=ticks, groups=groups, **agent_kwargs)
        assert python == native

    def test_an_agent_with_no_flockmates(self) -> None:
        self._assert_identical(_singles(3))

    def test_an_agent_with_no_flockmates_seeking(self) -> None:
        """Pins `SteeringBehavior.seek` and the force clamp.

        It does *not* pin which spelling of `length` the normalisation
        divides by -- an earlier version of this docstring claimed it
        did, and the sabotage round disproved it: the three spellings
        agree for these values.
        `test_a_seek_direction_that_distinguishes_the_length_spellings`
        is the one that holds that, with a target chosen to make them
        disagree.
        """
        self._assert_identical(
            _singles(3), seek_weight=1.0, seek_target=Vector2(50.0, 70.0)
        )

    def test_a_seek_direction_that_distinguishes_the_length_spellings(self) -> None:
        """Pins `length` as `sqrt(x * x + y * y)` inside the native solver.

        The three spellings of a length -- `x * x + y * y`, `x**2 +
        y**2` and `math.hypot` -- disagree by an ulp for about 0.03% of
        inputs, so a solver that reached for `hypot` would pass every
        other test in this class. It did, until this one existed.

        The seek target is the one input that reaches `length` directly
        and unmodified, so it is aimed at a vector where all three
        spellings are known to differ, measured rather than guessed. The
        tiny mass is also deliberate: it multiplies the force by 100
        before `velocity + acceleration * dt`, so the ulp lands well
        above the ulp of the result instead of rounding away.

        `tests/test_common_types.py::TestVector2LengthIsSpelledExactly`
        pins the Python half of the same contract.
        """
        divergent = Vector2(263.9070523968903, -295.2001492494054)
        self._assert_identical(
            [(Vector2(0.0, 0.0), Vector2(0.0, 0.0))],
            seek_weight=1.0,
            seek_target=divergent,
            mass=0.01,
        )

    def test_a_pair_steering_by_each_other(self) -> None:
        self._assert_identical(_pairs(4, separation=40.0))

    def test_a_pair_inside_the_separation_radius(self) -> None:
        """The separation branch, which is the one with the `sqrt` in it."""
        self._assert_identical(_pairs(4, separation=12.0))

    def test_a_coincident_pair(self) -> None:
        """The degenerate push, where Python refuses to divide by zero."""
        self._assert_identical(
            [
                value
                for index in range(3)
                for value in (
                    (Vector2(index * APART, 0.0), Vector2(7.0, 3.0)),
                    (Vector2(index * APART, 0.0), Vector2(-2.0, 9.0)),
                )
            ]
        )

    def test_a_pair_whose_force_is_clamped(self) -> None:
        self._assert_identical(_pairs(4, separation=20.0), max_force=3.0)

    def test_a_pair_whose_velocity_is_clamped(self) -> None:
        self._assert_identical(_pairs(4, separation=40.0), max_speed=0.5)

    def test_a_pair_seeking_as_well(self) -> None:
        self._assert_identical(
            _pairs(4, separation=40.0),
            seek_weight=1.2,
            seek_target=Vector2(120.0, -80.0),
        )

    def test_a_seek_target_the_agent_is_standing_on(self) -> None:
        """The `direction.length < 0.001` early return."""
        self._assert_identical(
            [(Vector2(0.0, 0.0), Vector2(5.0, 5.0))],
            seek_weight=1.0,
            seek_target=Vector2(0.0, 0.0),
        )

    @pytest.mark.parametrize(
        "weights",
        [
            {"cohesion_weight": 0.0},
            {"alignment_weight": 0.0},
            {"separation_weight": 0.0},
            {"cohesion_weight": 0.0, "alignment_weight": 0.0},
            {
                "cohesion_weight": 0.0,
                "alignment_weight": 0.0,
                "separation_weight": 0.0,
            },
        ],
    )
    def test_each_weight_can_be_switched_off(self, weights: dict[str, float]) -> None:
        """A zero weight contributes nothing, through either store.

        What this does *not* test, despite an earlier version of this
        docstring claiming it: that the native side branches on the
        weight rather than accumulating and multiplying by zero at the
        end. Those two are indistinguishable for finite inputs -- a
        force term scaled by 0.0 is 0.0, and `+= 0.0` is exact -- so the
        `want_cohesion` flags in both implementations are an
        optimisation with no observable behaviour. The sabotage round
        established that by removing one and watching all 63 tests pass.

        It does catch a port that used a hardcoded 1.0 where the weight
        belongs, which is the likelier slip.
        """
        self._assert_identical(_pairs(4, separation=20.0), **weights)

    @pytest.mark.parametrize("mass", [0.7, 3.0, 7.0, 11.9])
    def test_a_heavier_agent(self, mass: float) -> None:
        """`force * (1.0 / mass)`, not `force / mass`.

        Those differ for a third of forces at these masses, by one ulp.
        The agents start from rest on purpose: with a running velocity
        the difference lands below the ulp of `velocity + acceleration *
        dt` and is rounded away, so the obvious version of this test
        passes against `force / mass` and proves nothing. It was written
        that way first, and the sabotage round caught it.
        """
        self._assert_identical(_pairs(4, separation=40.0, moving=False), mass=mass)

    def test_a_disabled_agent_is_untouched(self) -> None:
        self._assert_identical(_pairs(2, separation=40.0), enabled=False)

    @pytest.mark.parametrize("groups", [2, 3, 4])
    def test_staggered_steering(self, groups: int) -> None:
        """The agents that only integrate must integrate identically."""
        self._assert_identical(_pairs(6, separation=40.0), groups=groups)

    @pytest.mark.parametrize("ticks", [2, 40])
    def test_many_ticks_do_not_drift(self, ticks: int) -> None:
        """Exact on tick 1 is weaker than exact on tick 40.

        A one-tick comparison cannot see an error that only shows up once
        the state it produced is fed back in, which is every error in the
        integration half.
        """
        self._assert_identical(_pairs(4, separation=40.0), ticks=ticks)

    def test_many_ticks_do_not_drift_while_staggered(self) -> None:
        self._assert_identical(_pairs(6, separation=40.0), ticks=40, groups=3)


class TestRealFlocksAgreeWithinSummationNoise:
    """Dense flocks, where the neighbour order is free and so is the sum.

    The tolerance here has exactly one permitted cause. That is why
    `TestTheArithmeticIsExact` exists above: without it, this tolerance
    would also be admitting every transcription error, and nobody could
    tell the difference by reading the results.
    """

    @pytest.mark.parametrize("count", [2, 9, 50, 300])
    def test_a_scattered_flock(self, count: int) -> None:
        _assert_close(*_both(_scattered(count, spread=max(count, 2) * 18.0)))

    def test_a_clumped_flock(self) -> None:
        _assert_close(*_both(_scattered(120, spread=50.0)))

    def test_a_flock_with_a_seek_target(self) -> None:
        _assert_close(
            *_both(
                _scattered(120, spread=400.0),
                seek_weight=0.8,
                seek_target=Vector2(200.0, 200.0),
            )
        )

    @pytest.mark.parametrize("groups", [2, 3])
    def test_a_staggered_flock(self, groups: int) -> None:
        _assert_close(*_both(_scattered(90, spread=400.0), groups=groups))

    def test_a_flock_with_mixed_tuning(self) -> None:
        """Agents that disagree about their own radii and weights.

        One `neighbor_radius` for everybody would let a port that reads
        the wrong agent's parameters pass: every row is identical, so
        reading row `n + 1` gives the same answer. These rows differ.
        """
        layout = _scattered(90, spread=400.0)
        manager, agents, transforms = _world(layout)
        for slot, agent in enumerate(agents):
            agent.neighbor_radius = 30.0 + slot % 7 * 14.0
            agent.separation_radius = 8.0 + slot % 5 * 6.0
            agent.max_speed = 60.0 + slot % 3 * 45.0
            agent.max_force = 120.0 + slot % 4 * 90.0
            agent.mass = 0.5 + slot % 6 * 0.4
            agent.cohesion_weight = 0.25 * (slot % 5)
            agent.alignment_weight = 0.3 * (slot % 4)
            agent.separation_weight = 0.5 + 0.25 * (slot % 3)
        start = _state(agents, transforms)

        FlockingSystem(manager, cell_size=CELL, accelerate=False).update(DT)
        after_python = _state(agents, transforms)

        _restore(start, agents, transforms)
        FlockingSystem(manager, cell_size=CELL, accelerate=True).update(DT)

        _assert_close(after_python, _state(agents, transforms))

    def test_a_flock_with_some_agents_disabled(self) -> None:
        layout = _scattered(90, spread=300.0)
        manager, agents, transforms = _world(layout)
        for agent in agents[::4]:
            agent.enabled = False
        start = _state(agents, transforms)

        FlockingSystem(manager, cell_size=CELL, accelerate=False).update(DT)
        after_python = _state(agents, transforms)

        _restore(start, agents, transforms)
        FlockingSystem(manager, cell_size=CELL, accelerate=True).update(DT)

        _assert_close(after_python, _state(agents, transforms))

    def test_an_empty_flock(self) -> None:
        """Both halves, because they are not the same question.

        `FlockingSystem.update` returns before reaching either store when
        there are no entities, so driving it only proves the
        short-circuit. The solver's own empty case is unreachable from
        the engine today and still worth pinning: it is what a flock
        that despawned mid-level looks like to a future caller, and the
        grid sizes its buckets from the agent count.
        """
        manager = EntityManager()
        FlockingSystem(manager, accelerate=True).update(DT)  # must not raise

        solver = native_module().NativeFlockingSolver()
        assert solver.tick(DT, CELL, 1, 0, [], []) == []
        assert list(solver.neighbour_counts()) == []


class TestTheFlockBehavesTheSameOverManyTicks:
    """Output parity: does the divergence stay noise, or become a flock?

    The tier that actually matters for a chaotic system. One tick's last
    bits are uninteresting; the question is whether two stores run for
    ten seconds still describe the same flock. Compared as aggregates --
    centroid, spread, mean speed -- because per-agent equality is not on
    offer here and asserting it would just be a slower way of failing.
    """

    @staticmethod
    def _summary(
        state: list[tuple[float, float, float, float]],
    ) -> tuple[float, float, float, float]:
        count = len(state)
        centre_x = sum(row[0] for row in state) / count
        centre_y = sum(row[1] for row in state) / count
        spread = max(
            ((row[0] - centre_x) ** 2 + (row[1] - centre_y) ** 2) ** 0.5
            for row in state
        )
        speed = sum((row[2] ** 2 + row[3] ** 2) ** 0.5 for row in state) / count
        return centre_x, centre_y, spread, speed

    @pytest.mark.parametrize("ticks", [60, 600])
    def test_a_flock_converging_on_a_target(self, ticks: int) -> None:
        python, native = _both(
            _scattered(60, spread=300.0),
            ticks=ticks,
            seek_weight=1.0,
            seek_target=Vector2(900.0, 120.0),
            neighbor_radius=80.0,
            separation_radius=20.0,
        )

        left = self._summary(python)
        right = self._summary(native)
        # Ten seconds of a chaotic system: individual agents may have
        # swapped places, so this bounds the flock, not the agents. The
        # travelled distance is ~600 units, so 5 units is under 1%.
        for expected, actual in zip(left, right, strict=True):
            assert abs(expected - actual) < 5.0, f"{left} vs {right}"

    def test_a_settled_flock_does_not_drift_apart(
        self,
    ) -> None:
        """No seek target, so the flock's own forces are all there is."""
        python, native = _both(_scattered(40, spread=150.0), ticks=600)

        left = self._summary(python)
        right = self._summary(native)
        for expected, actual in zip(left, right, strict=True):
            assert abs(expected - actual) < 5.0, f"{left} vs {right}"


class TestTheSolverRejectsNonsense:
    """The native side validates what Python would have raised on.

    Not symmetry for its own sake: `FlockingSystem` cannot produce any of
    these, so the only caller that can is a future one, and a solver that
    accepted a short row would read past the end of the flock and steer
    by whatever was next in memory.
    """

    def test_a_row_that_is_not_a_whole_agent(self) -> None:
        solver = native_module().NativeFlockingSolver()
        with pytest.raises(ValueError, match="stride"):
            solver.tick(DT, CELL, 1, 0, [0.0] * 14, [True])

    def test_a_flag_count_that_does_not_match(self) -> None:
        solver = native_module().NativeFlockingSolver()
        with pytest.raises(ValueError, match="enabled flags"):
            solver.tick(DT, CELL, 1, 0, [0.0] * 15, [True, True])

    @pytest.mark.parametrize("cell_size", [0.0, -64.0, float("nan")])
    def test_an_impossible_cell_size(self, cell_size: float) -> None:
        """Python raises `ZeroDivisionError` on 0.0; NaN would be silent."""
        solver = native_module().NativeFlockingSolver()
        with pytest.raises(ValueError, match="cell_size"):
            solver.tick(DT, cell_size, 1, 0, [0.0] * 15, [True])

    def test_no_groups_at_all(self) -> None:
        """`FlockingSystem` clamps to 1; `slot % 0` would be a crash."""
        solver = native_module().NativeFlockingSolver()
        with pytest.raises(ValueError, match="at least 1"):
            solver.tick(DT, CELL, 0, 0, [0.0] * 15, [True])

    def test_a_radius_that_would_sweep_the_world(self) -> None:
        """A `cell_size` typo becomes an error rather than a hang.

        Python has no such limit and does not need one -- it just takes
        proportionally longer, which for `cell_size=0.001` means a frame
        that never ends. This is the one place the native store
        deliberately refuses something Python accepts.
        """
        solver = native_module().NativeFlockingSolver()
        row = [0.0, 0.0, 0.0, 0.0, 150.0, 400.0, 1.0, 5.0e6, 30.0, 1.0, 1.0, 1.5]
        with pytest.raises(ValueError, match="cells per axis"):
            solver.tick(DT, 0.001, 1, 0, [*row, 0.0, 0.0, 0.0], [True])
