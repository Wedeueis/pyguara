"""Tests for the FSM, blackboard, and the ECS-facing AISystem/AIContext."""

import logging

from pyguara.ai import AIContext, AISystem
from pyguara.ai.behavior_tree import (
    ActionNode,
    BehaviorTree,
    NodeStatus,
    SequenceNode,
    WaitNode,
)
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.components import AIComponent
from pyguara.ai.fsm import State, StateMachine
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager


# Mocks
class MockState(State):
    def __init__(self, ent, bb, name):
        super().__init__(ent, bb)
        self.name = name
        self.entered = False
        self.exited = False
        self.enter_count = 0
        self.exit_count = 0
        self.next_state: str | None = None

    def on_enter(self):
        self.entered = True
        self.enter_count += 1

    def on_exit(self):
        self.exited = True
        self.exit_count += 1

    def update(self, dt):
        return self.next_state


def _make_fsm() -> tuple[StateMachine, MockState, MockState]:
    entity = Entity()
    bb = Blackboard()
    fsm = StateMachine(entity, bb)
    idle = MockState(entity, bb, "idle")
    walk = MockState(entity, bb, "walk")
    fsm.add_state("idle", idle)
    fsm.add_state("walk", walk)
    return fsm, idle, walk


def test_blackboard():
    bb = Blackboard()
    bb.set("hp", 100)
    assert bb.get("hp") == 100
    assert bb.has("hp")
    assert bb.get("missing", 5) == 5


def test_fsm_transitions():
    fsm, s1, s2 = _make_fsm()

    fsm.set_initial_state("idle")
    assert fsm._current_state is s1
    assert s1.entered

    # Trigger transition
    s1.next_state = "walk"
    fsm.update(0.1)

    assert fsm._current_state is s2
    assert s1.exited
    assert s2.entered


def test_set_initial_state_unknown_name_warns_and_stays_inert(caplog):
    """An unknown initial state name is a mistake worth a warning, not silence."""
    fsm, _idle, _walk = _make_fsm()

    with caplog.at_level(logging.WARNING):
        fsm.set_initial_state("Idle")  # wrong case

    assert fsm._current_state is None
    assert any("Idle" in r.message for r in caplog.records)
    # And the inert machine no-ops rather than raising.
    fsm.update(0.1)


def test_set_initial_state_twice_exits_the_first_state():
    """Re-seeding the machine must not leak the previous state's on_enter."""
    fsm, idle, walk = _make_fsm()

    fsm.set_initial_state("idle")
    fsm.set_initial_state("walk")

    assert idle.exit_count == 1
    assert walk.enter_count == 1
    assert fsm._current_state is walk


def test_transition_to_unknown_target_warns_and_holds(caplog):
    fsm, idle, _walk = _make_fsm()
    fsm.set_initial_state("idle")
    idle.next_state = "nowhere"

    with caplog.at_level(logging.WARNING):
        fsm.update(0.1)

    assert fsm._current_state_name == "idle"
    assert idle.exit_count == 0  # never left
    assert any("nowhere" in r.message for r in caplog.records)


class TestAISystemContext:
    """AISystem must hand behavior trees a context that carries dt."""

    def test_wait_node_completes_in_real_time_regardless_of_frame_rate(self):
        """Regression: the tree got the bare Entity, so WaitNode ran on a
        fixed ~1/60 step and a 1s wait took ~2s at 30fps, ~3.5s at 144fps."""
        for fps in (30, 60, 144):
            em = EntityManager()
            entity = em.create_entity()
            done = {"hit": False}

            def _mark(_ctx, flag=done):
                flag["hit"] = True
                return NodeStatus.SUCCESS

            tree = BehaviorTree(
                root=SequenceNode([WaitNode(duration=1.0), ActionNode(_mark)])
            )
            entity.add_component(AIComponent(behavior_tree=tree))
            system = AISystem(em)

            frames = 0
            while not done["hit"] and frames < fps * 3:
                system.update(1.0 / fps)
                frames += 1

            elapsed = frames / fps
            assert done["hit"], f"wait never completed at {fps}fps"
            assert 0.9 <= elapsed <= 1.2, f"{fps}fps: waited {elapsed:.2f}s"

    def test_context_exposes_entity_and_blackboard(self):
        em = EntityManager()
        entity = em.create_entity()
        seen: dict[str, object] = {}

        def _probe(ctx: AIContext):
            seen["entity"] = ctx.entity
            seen["dt"] = ctx.dt
            seen["blackboard"] = ctx.blackboard
            return NodeStatus.SUCCESS

        ai = AIComponent(behavior_tree=BehaviorTree(root=ActionNode(_probe)))
        entity.add_component(ai)

        AISystem(em).update(0.033)

        assert seen["entity"] is entity
        assert seen["dt"] == 0.033
        assert seen["blackboard"] is ai.blackboard

    def test_disabled_component_is_skipped(self):
        em = EntityManager()
        entity = em.create_entity()
        ticks = {"n": 0}

        def _count(_ctx):
            ticks["n"] += 1
            return NodeStatus.SUCCESS

        ai = AIComponent(behavior_tree=BehaviorTree(root=ActionNode(_count)))
        ai.enabled = False
        entity.add_component(ai)

        AISystem(em).update(0.016)

        assert ticks["n"] == 0
