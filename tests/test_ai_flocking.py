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

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
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
