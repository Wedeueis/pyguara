"""Tests for boid flocking: SteeringBehavior.{cohesion,alignment,separation}
and FlockingSystem.

The GDD this targets (Vinagre: Matilha) calls out a specific failure mode
explicitly: visible jitter when the flow field's pull and neighbor
separation disagree. The stability tests below are a probe for exactly
that, not just "it looks fine" -- run many ticks and assert the flock
neither jitters (bounded velocity oscillation) nor scatters (bounded
spread) once it has had time to settle.
"""

from __future__ import annotations

import pytest

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem, flock_force
from pyguara.ai.steering import SteeringBehavior
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager


def _flock_entity(em: EntityManager, pos: Vector2, **agent_kwargs) -> None:
    entity = em.create_entity()
    entity.add_component(Transform(position=pos))
    entity.add_component(FlockingAgent(**agent_kwargs))
    return entity


def _run(system: FlockingSystem, frames: int = 120, dt: float = 1.0 / 60.0) -> None:
    for _ in range(frames):
        system.update(dt)


# `False` is the Python sweep, `True` the native one; see `_system`.
STORES = [
    pytest.param(False, id="python"),
    pytest.param(True, id="native"),
]


def _system(
    manager: EntityManager, accelerate: bool, **kwargs: object
) -> FlockingSystem:
    """A system over `manager`, skipping an absent extension.

    Every system-level test below runs against both stores. The pure
    `flock_force` tests do not: it is one function with one
    implementation, and the native transcription of it is compared in
    `tests/test_native_flocking_parity.py` instead.
    """
    if accelerate and not FlockingSystem(EntityManager(), accelerate=None).accelerated:
        pytest.skip("native extension not built; `cargo build --release`")
    return FlockingSystem(manager, accelerate=accelerate, **kwargs)  # type: ignore[arg-type]


# ========== SteeringBehavior.cohesion ==========


class TestCohesion:
    def test_no_neighbors_yields_zero_force(self) -> None:
        transform = Transform(position=Vector2(0, 0))
        force = SteeringBehavior.cohesion(transform, [], 100.0, Vector2(0, 0))
        assert force == Vector2(0, 0)

    def test_steers_toward_average_neighbor_position(self) -> None:
        transform = Transform(position=Vector2(0, 0))
        neighbors = [Vector2(100, 0), Vector2(100, 0), Vector2(0, 100)]
        # Average is (66.6, 33.3): force should point into the first quadrant.
        force = SteeringBehavior.cohesion(transform, neighbors, 100.0, Vector2(0, 0))
        assert force.x > 0
        assert force.y > 0


# ========== SteeringBehavior.alignment ==========


class TestAlignment:
    def test_no_neighbors_yields_zero_force(self) -> None:
        force = SteeringBehavior.alignment([], 100.0, Vector2(0, 0))
        assert force == Vector2(0, 0)

    def test_steers_toward_average_neighbor_velocity(self) -> None:
        neighbors = [Vector2(100, 0), Vector2(100, 0)]
        force = SteeringBehavior.alignment(neighbors, 200.0, Vector2(0, 0))
        assert force.x > 0
        assert abs(force.y) < 0.001

    def test_average_velocity_is_clamped_to_max_speed(self) -> None:
        neighbors = [Vector2(500, 0), Vector2(500, 0)]
        force = SteeringBehavior.alignment(neighbors, 100.0, Vector2(0, 0))
        # desired (clamped to 100) minus current (0) == 100 on the x axis.
        assert force.x == pytest.approx(100.0, abs=0.5)


# ========== SteeringBehavior.separation ==========


class TestSeparation:
    def test_no_neighbors_yields_zero_force(self) -> None:
        transform = Transform(position=Vector2(0, 0))
        force = SteeringBehavior.separation(transform, [], 50.0, 100.0)
        assert force == Vector2(0, 0)

    def test_pushes_away_from_close_neighbor(self) -> None:
        transform = Transform(position=Vector2(0, 0))
        neighbors = [Vector2(10, 0)]  # close, within separation_radius
        force = SteeringBehavior.separation(transform, neighbors, 50.0, 100.0)
        assert force.x < 0  # pushed away, in -x

    def test_ignores_neighbors_outside_separation_radius(self) -> None:
        transform = Transform(position=Vector2(0, 0))
        neighbors = [Vector2(1000, 0)]
        force = SteeringBehavior.separation(transform, neighbors, 50.0, 100.0)
        assert force == Vector2(0, 0)

    def test_coincident_neighbor_does_not_crash(self) -> None:
        transform = Transform(position=Vector2(0, 0))
        neighbors = [Vector2(0, 0)]
        force = SteeringBehavior.separation(transform, neighbors, 50.0, 100.0)
        assert force.length > 0


# ========== FlockingSystem ==========


@pytest.mark.parametrize("accelerate", STORES)
class TestFlockingSystemStability:
    def test_flock_converges_toward_a_shared_seek_target_without_scattering(
        self, accelerate: bool
    ) -> None:
        em = EntityManager()
        target = Vector2(500, 0)
        entities = [
            _flock_entity(
                em,
                Vector2(i * 10, 0),
                seek_target=target,
                max_speed=150.0,
                neighbor_radius=80.0,
                separation_radius=20.0,
            )
            for i in range(8)
        ]
        system = _system(em, accelerate)
        _run(system, frames=300)

        positions = [e.get_component(Transform).position for e in entities]
        # The flock has moved substantially toward the target.
        assert all(p.x > 200 for p in positions)
        # It stayed together: max pairwise spread on x is bounded, not
        # scattered across the whole traversed distance.
        spread = max(p.x for p in positions) - min(p.x for p in positions)
        assert spread < 150

    def test_flock_does_not_jitter_once_settled(self, accelerate: bool) -> None:
        em = EntityManager()
        target = Vector2(300, 0)
        entities = [
            _flock_entity(em, Vector2(i * 15, 0), seek_target=target, max_speed=120.0)
            for i in range(6)
        ]
        system = _system(em, accelerate)
        _run(system, frames=600)  # let it settle near the target

        # Sample velocity magnitude over the next 60 frames: should not be
        # wildly oscillating (the jitter failure mode) even though small
        # steady-state motion around a moving average is expected.
        max_speed_samples = []
        for _ in range(60):
            system.update(1.0 / 60.0)
            max_speed_samples.append(
                max(e.get_component(FlockingAgent).velocity.length for e in entities)
            )
        assert max(max_speed_samples) < 200.0

    def test_close_agents_separate_instead_of_overlapping(
        self, accelerate: bool
    ) -> None:
        em = EntityManager()
        e1 = _flock_entity(em, Vector2(0, 0), separation_radius=40.0, seek_weight=0.0)
        e2 = _flock_entity(em, Vector2(5, 0), separation_radius=40.0, seek_weight=0.0)
        system = _system(em, accelerate)
        _run(system, frames=60)

        p1 = e1.get_component(Transform).position
        p2 = e2.get_component(Transform).position
        assert (p1 - p2).length > 5.0

    def test_disabled_agent_is_not_moved(self, accelerate: bool) -> None:
        em = EntityManager()
        e = _flock_entity(em, Vector2(0, 0), seek_target=Vector2(500, 0), enabled=False)
        system = _system(em, accelerate)
        _run(system, frames=60)
        assert e.get_component(Transform).position == Vector2(0, 0)


class TestFusedForceMatchesTheSeparateBehaviours:
    """`flock_force` replaced three `SteeringBehavior` calls with one pass.

    That is a pure performance change, so the contract is equivalence:
    whatever the three behaviours summed to before, the fused version must
    still produce. These tests are the only thing standing between that
    claim and a silent behaviour change, so they compare against the
    original composition directly rather than against hand-written
    expected vectors.
    """

    @staticmethod
    def _separate(
        position: Vector2,
        agent: FlockingAgent,
        neighbors: list[tuple[Vector2, Vector2]],
    ) -> Vector2:
        """The original four-call composition, preserved here as the oracle."""
        transform = Transform(position=position)
        positions = [p for p, _ in neighbors]
        velocities = [v for _, v in neighbors]

        force = Vector2(0, 0)
        if agent.cohesion_weight:
            force = (
                force
                + SteeringBehavior.cohesion(
                    transform, positions, agent.max_speed, agent.velocity
                )
                * agent.cohesion_weight
            )
        if agent.alignment_weight:
            force = (
                force
                + SteeringBehavior.alignment(
                    velocities, agent.max_speed, agent.velocity
                )
                * agent.alignment_weight
            )
        if agent.separation_weight:
            force = (
                force
                + SteeringBehavior.separation(
                    transform, positions, agent.separation_radius, agent.max_speed
                )
                * agent.separation_weight
            )
        return force

    def _assert_matches(
        self,
        position: Vector2,
        agent: FlockingAgent,
        neighbors: list[tuple[Vector2, Vector2]],
    ) -> None:
        expected = self._separate(position, agent, neighbors)
        actual = flock_force(position, agent, iter(neighbors))

        assert actual.x == pytest.approx(expected.x, abs=1e-6)
        assert actual.y == pytest.approx(expected.y, abs=1e-6)

    def test_no_neighbours(self) -> None:
        self._assert_matches(Vector2(0, 0), FlockingAgent(), [])

    def test_a_spread_flock(self) -> None:
        agent = FlockingAgent(velocity=Vector2(10, -5))
        neighbors = [
            (Vector2(40, 0), Vector2(5, 5)),
            (Vector2(-30, 20), Vector2(-2, 8)),
            (Vector2(10, 60), Vector2(0, -3)),
        ]
        self._assert_matches(Vector2(0, 0), agent, neighbors)

    def test_neighbours_inside_the_separation_radius(self) -> None:
        """The branch that actually contributes a push."""
        agent = FlockingAgent(separation_radius=30.0, velocity=Vector2(1, 1))
        neighbors = [
            (Vector2(5, 0), Vector2(1, 0)),
            (Vector2(0, 12), Vector2(0, 1)),
            (Vector2(200, 200), Vector2(3, 3)),  # far: cohesion/alignment only
        ]
        self._assert_matches(Vector2(0, 0), agent, neighbors)

    def test_a_coincident_neighbour(self) -> None:
        """Distance zero takes the fixed-direction branch in both versions."""
        agent = FlockingAgent(separation_radius=25.0)
        self._assert_matches(Vector2(50, 50), agent, [(Vector2(50, 50), Vector2(0, 0))])

    def test_a_dense_cluster_clamps_separation(self) -> None:
        """Enough close neighbours to trip the `push.length > max_speed` clamp."""
        agent = FlockingAgent(separation_radius=40.0, max_speed=20.0)
        neighbors = [(Vector2(float(i), 1.0), Vector2(0, 0)) for i in range(1, 9)]
        self._assert_matches(Vector2(0, 0), agent, neighbors)

    def test_alignment_clamps_a_fast_flock(self) -> None:
        """Average neighbour velocity above `max_speed` is clamped in both."""
        agent = FlockingAgent(max_speed=10.0, velocity=Vector2(0, 0))
        neighbors = [
            (Vector2(100, 0), Vector2(400, 0)),
            (Vector2(0, 100), Vector2(0, 400)),
        ]
        self._assert_matches(Vector2(0, 0), agent, neighbors)

    def test_a_neighbour_at_the_agents_own_centre_of_mass(self) -> None:
        """Cohesion's `direction.length < 0.001` early-out, in both versions."""
        agent = FlockingAgent(separation_radius=1.0)
        neighbors = [
            (Vector2(10, 0), Vector2(1, 1)),
            (Vector2(-10, 0), Vector2(1, 1)),
        ]
        self._assert_matches(Vector2(0, 0), agent, neighbors)

    @pytest.mark.parametrize(
        ("cohesion", "alignment", "separation"),
        [(0.0, 1.0, 1.5), (1.0, 0.0, 1.5), (1.0, 1.0, 0.0), (0.0, 0.0, 0.0)],
    )
    def test_each_weight_can_be_switched_off(
        self, cohesion: float, alignment: float, separation: float
    ) -> None:
        """A zero weight skips work in the fused loop; it must still agree."""
        agent = FlockingAgent(
            cohesion_weight=cohesion,
            alignment_weight=alignment,
            separation_weight=separation,
            separation_radius=30.0,
            velocity=Vector2(2, 3),
        )
        neighbors = [
            (Vector2(8, 4), Vector2(1, 2)),
            (Vector2(-50, 20), Vector2(-1, 0)),
        ]
        self._assert_matches(Vector2(0, 0), agent, neighbors)


@pytest.mark.parametrize("accelerate", STORES)
class TestStaggeredSteering:
    """`groups` spreads steering across ticks without stopping motion.

    The trade is decision *rate*, not movement: every agent integrates its
    position every tick regardless, so a staggered flock looks the same
    and simply commits to a heading for a few frames longer.

    Every assertion here is deliberately order-independent -- "how many
    agents steered", never "which ones". `get_entities_with_cached` yields
    from a set of uuid4 ids, so processing order varies between runs, and
    flocking is Gauss-Seidel: an agent steering later in a tick sees the
    already-moved positions of those ahead of it. A test that named
    particular agents would pass or fail on the hash of a uuid.
    """

    @staticmethod
    def _flock(manager: EntityManager, count: int) -> list:
        """Build a deliberately asymmetric flock.

        Even spacing with identical velocities makes the middle agent's
        forces cancel exactly, so it steers to a zero force and its
        velocity does not change -- correct behaviour that would read as
        "this agent did not steer". Distinct positions and velocities give
        every agent a non-zero alignment term whatever the order.
        """
        offsets = [(0.0, 0.0), (17.0, 3.0), (31.0, -11.0), (44.0, 8.0)]
        velocities = [(5.0, 0.0), (0.0, 5.0), (-3.0, 2.0), (2.0, -4.0)]
        entities = []
        for index in range(count):
            x, y = offsets[index % len(offsets)]
            vx, vy = velocities[index % len(velocities)]
            entity = manager.create_entity()
            entity.add_component(Transform(position=Vector2(x, y)))
            entity.add_component(
                FlockingAgent(velocity=Vector2(vx, vy), seek_weight=0.0)
            )
            entities.append(entity)
        return entities

    @staticmethod
    def _steered_count(entities: list, before: list) -> int:
        """How many agents' velocities changed."""
        return sum(
            entity.get_component(FlockingAgent).velocity != previous
            for entity, previous in zip(entities, before, strict=True)
        )

    def test_the_default_steers_every_agent_every_tick(self, accelerate: bool) -> None:
        manager = EntityManager()
        entities = self._flock(manager, 4)
        before = [e.get_component(FlockingAgent).velocity for e in entities]

        _system(manager, accelerate).update(1 / 60)

        assert self._steered_count(entities, before) == 4

    def test_every_agent_still_moves_on_a_tick_it_does_not_steer(
        self, accelerate: bool
    ) -> None:
        """The property that makes staggering invisible."""
        manager = EntityManager()
        entities = self._flock(manager, 4)
        before = [e.get_component(Transform).position for e in entities]

        _system(manager, accelerate, groups=4).update(1 / 60)

        after = [e.get_component(Transform).position for e in entities]
        assert all(a != b for a, b in zip(after, before, strict=True))

    def test_only_one_group_steers_per_tick(self, accelerate: bool) -> None:
        manager = EntityManager()
        entities = self._flock(manager, 4)
        before = [e.get_component(FlockingAgent).velocity for e in entities]

        _system(manager, accelerate, groups=4).update(1 / 60)

        assert self._steered_count(entities, before) == 1

    def test_every_agent_steers_within_one_full_round(self, accelerate: bool) -> None:
        manager = EntityManager()
        entities = self._flock(manager, 4)
        system = _system(manager, accelerate, groups=4)
        before = [e.get_component(FlockingAgent).velocity for e in entities]

        for _ in range(4):
            system.update(1 / 60)

        assert self._steered_count(entities, before) == 4

    @pytest.mark.parametrize("groups", [0, -3])
    def test_a_nonsense_group_count_is_clamped_to_one(
        self, groups: int, accelerate: bool
    ) -> None:
        """Zero would make `slot % groups` raise; negatives are meaningless."""
        manager = EntityManager()
        entities = self._flock(manager, 4)
        before = [e.get_component(FlockingAgent).velocity for e in entities]

        _system(manager, accelerate, groups=groups).update(1 / 60)

        assert self._steered_count(entities, before) == 4

    def test_a_disabled_agent_neither_steers_nor_moves(self, accelerate: bool) -> None:
        manager = EntityManager()
        entities = self._flock(manager, 3)
        entities[0].get_component(FlockingAgent).enabled = False
        before = entities[0].get_component(Transform).position

        _system(manager, accelerate, groups=2).update(1 / 60)

        assert entities[0].get_component(Transform).position == before


class TestTheStoreIsOneEngineWideChoice:
    """`accelerate=` overrides the switch, and that is all it is for.

    The same contract the pools, the flow field and the spark batch have,
    and the same reason: the parity suite needs both stores side by side
    in one process, so there has to be a per-object override -- and it is
    not a second place to configure the engine.
    `PerformanceConfig.native_acceleration` is. See
    `docs/adr/0004-the-native-boundary.md`, Decision 4.
    """

    def test_the_default_defers_to_the_engine_wide_setting(self) -> None:
        """Fails rather than skips when the loader breaks.

        Deliberately not guarded by a skip. Every other native test in
        this file skips when the extension is absent, which means a
        broken loader -- the failure mode `pyguara/native.py` documents,
        where a wrong path finds no library and everything quietly falls
        back -- would show up as a green suite. This one notices.
        """
        from pyguara import native

        system = FlockingSystem(EntityManager())

        assert system.accelerated is native.in_use()

    def test_forcing_the_python_store_always_works(self) -> None:
        """No toolchain needed, which is the point of keeping both."""
        assert FlockingSystem(EntityManager(), accelerate=False).accelerated is False

    def test_demanding_a_missing_extension_raises_rather_than_falling_back(
        self,
    ) -> None:
        """`accelerate=True` is a demand, not a preference.

        Silently falling back is what `None` is for. A caller that said
        True wants to know, because the alternative is discovering it
        from a frame time.
        """
        from pyguara import native

        if native.in_use():
            pytest.skip("the extension is built, so the demand is satisfiable")

        with pytest.raises(RuntimeError, match="not available"):
            FlockingSystem(EntityManager(), accelerate=True)
