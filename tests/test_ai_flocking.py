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


class TestFlockingSystemStability:
    def test_flock_converges_toward_a_shared_seek_target_without_scattering(
        self,
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
        system = FlockingSystem(em)
        _run(system, frames=300)

        positions = [e.get_component(Transform).position for e in entities]
        # The flock has moved substantially toward the target.
        assert all(p.x > 200 for p in positions)
        # It stayed together: max pairwise spread on x is bounded, not
        # scattered across the whole traversed distance.
        spread = max(p.x for p in positions) - min(p.x for p in positions)
        assert spread < 150

    def test_flock_does_not_jitter_once_settled(self) -> None:
        em = EntityManager()
        target = Vector2(300, 0)
        entities = [
            _flock_entity(em, Vector2(i * 15, 0), seek_target=target, max_speed=120.0)
            for i in range(6)
        ]
        system = FlockingSystem(em)
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

    def test_close_agents_separate_instead_of_overlapping(self) -> None:
        em = EntityManager()
        e1 = _flock_entity(em, Vector2(0, 0), separation_radius=40.0, seek_weight=0.0)
        e2 = _flock_entity(em, Vector2(5, 0), separation_radius=40.0, seek_weight=0.0)
        system = FlockingSystem(em)
        _run(system, frames=60)

        p1 = e1.get_component(Transform).position
        p2 = e2.get_component(Transform).position
        assert (p1 - p2).length > 5.0

    def test_disabled_agent_is_not_moved(self) -> None:
        em = EntityManager()
        e = _flock_entity(em, Vector2(0, 0), seek_target=Vector2(500, 0), enabled=False)
        system = FlockingSystem(em)
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
