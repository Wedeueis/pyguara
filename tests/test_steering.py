"""Tests for SteeringSystem and the SteeringBehaviorType enum.

The subsystem audit had no steering-system test at all, and every
SteeringAgent was built the same way (``behavior="wander"``), so the
string-dispatch gaps went unseen.
"""

import pytest

from pyguara.ai.components import Navigator, SteeringAgent, SteeringBehaviorType
from pyguara.ai.steering_system import SteeringSystem
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager


def _agent_entity(em: EntityManager, pos: Vector2, **agent_kwargs):
    entity = em.create_entity()
    entity.add_component(Transform(position=pos))
    entity.add_component(SteeringAgent(**agent_kwargs))
    return entity


def _run(system: SteeringSystem, frames: int = 120, dt: float = 1.0 / 60.0) -> None:
    for _ in range(frames):
        system.update(dt)


class TestSteeringBehaviorType:
    """Construction-time coercion and validation."""

    def test_string_is_coerced_to_enum(self):
        agent = SteeringAgent(behavior="arrive")
        assert agent.behavior is SteeringBehaviorType.ARRIVE

    def test_enum_value_passes_through(self):
        agent = SteeringAgent(behavior=SteeringBehaviorType.PURSUIT)
        assert agent.behavior is SteeringBehaviorType.PURSUIT

    def test_default_is_seek(self):
        assert SteeringAgent().behavior is SteeringBehaviorType.SEEK

    def test_unknown_behavior_rejected_at_construction(self):
        with pytest.raises(ValueError, match="chase"):
            SteeringAgent(behavior="chase")


class TestReachableBehaviors:
    """Every enum member must actually drive the agent through the system."""

    def test_seek_moves_toward_target(self):
        em = EntityManager()
        e = _agent_entity(em, Vector2(0, 0), behavior="seek", target=Vector2(500, 0))
        _run(SteeringSystem(em))
        assert e.get_component(Transform).position.x > 50

    def test_flee_moves_away_from_target(self):
        em = EntityManager()
        e = _agent_entity(em, Vector2(0, 0), behavior="flee", target=Vector2(30, 0))
        _run(SteeringSystem(em))
        assert e.get_component(Transform).position.x < -10

    def test_wander_moves_without_a_target(self):
        em = EntityManager()
        e = _agent_entity(em, Vector2(0, 0), behavior="wander")
        _run(SteeringSystem(em))
        assert e.get_component(Transform).position.sqr_magnitude > 1.0

    def test_pursuit_leads_a_moving_target(self):
        em = EntityManager()
        # Target ahead on X, moving fast in +Y: interception must gain Y.
        e = _agent_entity(
            em,
            Vector2(0, 0),
            behavior="pursuit",
            target=Vector2(200, 0),
            target_velocity=Vector2(0, 150),
            max_speed=250,
        )
        _run(SteeringSystem(em))
        pos = e.get_component(Transform).position
        assert pos.x > 20
        assert pos.y > 20  # led the target, not aimed at its old spot

    def test_evade_flees_a_moving_threat(self):
        em = EntityManager()
        e = _agent_entity(
            em,
            Vector2(0, 0),
            behavior="evade",
            target=Vector2(40, 0),
            target_velocity=Vector2(-50, 0),
            max_speed=200,
        )
        _run(SteeringSystem(em))
        assert e.get_component(Transform).position.x < -10


class TestArriveSettles:
    """Regression: arrive overshot the target and orbited it forever."""

    def test_arrive_comes_to_rest_at_the_target(self):
        em = EntityManager()
        e = _agent_entity(
            em,
            Vector2(0, 0),
            behavior="arrive",
            target=Vector2(300, 0),
            max_speed=200,
            slowing_radius=100,
        )
        system = SteeringSystem(em)
        _run(system, frames=1200)

        transform = e.get_component(Transform)
        agent = e.get_component(SteeringAgent)
        assert (Vector2(300, 0) - transform.position).length < 2.0
        assert agent.velocity.length < 1.0

    def test_arrive_does_not_oscillate_once_settled(self):
        em = EntityManager()
        e = _agent_entity(
            em,
            Vector2(0, 0),
            behavior="arrive",
            target=Vector2(150, 0),
            max_speed=180,
            slowing_radius=80,
        )
        system = SteeringSystem(em)
        _run(system, frames=1500)

        transform = e.get_component(Transform)
        settled = transform.position
        _run(system, frames=120)
        assert (transform.position - settled).length < 0.5


class TestWanderState:
    """Per-entity wander target persistence and its cleanup."""

    def test_wander_target_persists_across_frames(self):
        em = EntityManager()
        e = _agent_entity(em, Vector2(0, 0), behavior="wander")
        system = SteeringSystem(em)
        system.update(1 / 60)
        assert e.id in system._wander_targets

    def test_cleanup_clears_wander_targets(self):
        em = EntityManager()
        _agent_entity(em, Vector2(0, 0), behavior="wander")
        system = SteeringSystem(em)
        system.update(1 / 60)
        assert system._wander_targets

        system.cleanup()
        assert system._wander_targets == {}


class TestTargetResolution:
    def test_non_wander_agent_without_a_target_is_skipped(self):
        em = EntityManager()
        e = _agent_entity(em, Vector2(0, 0), behavior="seek")  # no target
        _run(SteeringSystem(em), frames=30)
        # No movement, no crash.
        assert e.get_component(Transform).position == Vector2(0, 0)

    def test_navigator_path_drives_seek_when_no_direct_target(self):
        em = EntityManager()
        e = _agent_entity(em, Vector2(0, 0), behavior="seek", max_speed=200)
        nav = Navigator(reach_threshold=8.0)
        nav.set_path([Vector2(120, 0), Vector2(120, 120)])
        e.add_component(nav)

        _run(SteeringSystem(em), frames=240)

        # Advanced past the first waypoint toward the second.
        assert nav.current_index >= 1
        assert e.get_component(Transform).position.y > 20
