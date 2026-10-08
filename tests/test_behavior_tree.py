"""Tests for behavior tree system."""

from typing import Any

import pytest

from pyguara.ai.behavior_tree import (
    ActionNode,
    BehaviorTree,
    BlackboardCondition,
    ConditionNode,
    CooldownNode,
    InverterNode,
    NodeStatus,
    ParallelNode,
    RandomSelector,
    ReactiveSelectorNode,
    ReactiveSequenceNode,
    RepeaterNode,
    SelectorNode,
    SequenceNode,
    SetBlackboard,
    SucceederNode,
    UntilFailNode,
    WaitNode,
)


class MockContext:
    """Mock context for testing."""

    def __init__(self):
        """Initialize mock context."""
        self.dt = 0.016
        self.counter = 0
        self.flag = False
        self.values = []


class TestActionNode:
    """Test ActionNode functionality."""

    def test_action_success(self):
        """Action returning SUCCESS should propagate."""

        def action(context):
            return NodeStatus.SUCCESS

        node = ActionNode(action)
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.SUCCESS
        assert node.status == NodeStatus.SUCCESS

    def test_action_failure(self):
        """Action returning FAILURE should propagate."""

        def action(context):
            return NodeStatus.FAILURE

        node = ActionNode(action)
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.FAILURE
        assert node.status == NodeStatus.FAILURE

    def test_action_running(self):
        """Action returning RUNNING should propagate."""

        def action(context):
            return NodeStatus.RUNNING

        node = ActionNode(action)
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING
        assert node.status == NodeStatus.RUNNING

    def test_action_modifies_context(self):
        """Action should be able to modify context."""

        def increment_counter(context):
            context.counter += 1
            return NodeStatus.SUCCESS

        node = ActionNode(increment_counter)
        context = MockContext()

        node.tick(context)

        assert context.counter == 1

    def test_action_with_custom_name(self):
        """ActionNode should accept custom name."""

        def action(context):
            return NodeStatus.SUCCESS

        node = ActionNode(action, name="CustomAction")

        assert node.name == "CustomAction"


class TestConditionNode:
    """Test ConditionNode functionality."""

    def test_condition_true_returns_success(self):
        """Condition returning True should return SUCCESS."""

        def always_true(context):
            return True

        node = ConditionNode(always_true)
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_condition_false_returns_failure(self):
        """Condition returning False should return FAILURE."""

        def always_false(context):
            return False

        node = ConditionNode(always_false)
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.FAILURE

    def test_condition_checks_context(self):
        """Condition should check context state."""

        def is_flag_set(context):
            return context.flag

        node = ConditionNode(is_flag_set)
        context = MockContext()

        # Flag is False
        status = node.tick(context)
        assert status == NodeStatus.FAILURE

        # Set flag
        context.flag = True
        status = node.tick(context)
        assert status == NodeStatus.SUCCESS


class TestWaitNode:
    """Test WaitNode functionality."""

    def test_wait_returns_running(self):
        """Wait should return RUNNING while waiting."""
        node = WaitNode(duration=1.0)
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING

    def test_wait_completes(self):
        """Wait should return SUCCESS after duration."""
        node = WaitNode(duration=0.05)
        context = MockContext()

        # Tick multiple times (0.016 * 4 = 0.064 > 0.05)
        for _ in range(4):
            status = node.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_wait_reset(self):
        """Reset should restart wait timer."""
        node = WaitNode(duration=0.05)
        context = MockContext()

        # Partially complete
        node.tick(context)
        assert node.status == NodeStatus.RUNNING

        # Reset
        node.reset()

        # Should start over
        status = node.tick(context)
        assert status == NodeStatus.RUNNING

    def test_wait_uses_context_dt_not_a_fixed_step(self):
        """Elapsed time tracks the context's real dt, whatever its value.

        Regression: WaitNode read a hardcoded ~1/60 fallback, so under a
        context that carried a real (larger or smaller) dt the wait drifted.
        """
        node = WaitNode(duration=1.0)
        ctx = MockContext()
        ctx.dt = 0.25  # 4 ticks == 1.0s, regardless of frame rate

        assert node.tick(ctx) == NodeStatus.RUNNING
        assert node.tick(ctx) == NodeStatus.RUNNING
        assert node.tick(ctx) == NodeStatus.RUNNING
        assert node.tick(ctx) == NodeStatus.SUCCESS

    def test_wait_completes_in_one_tick_for_a_large_dt(self):
        """A single long frame satisfies the whole wait."""
        node = WaitNode(duration=0.5)
        ctx = MockContext()
        ctx.dt = 2.0

        assert node.tick(ctx) == NodeStatus.SUCCESS


class TestSequenceNode:
    """Test SequenceNode functionality."""

    def test_sequence_all_success(self):
        """Sequence should return SUCCESS if all children succeed."""

        def success(context):
            return NodeStatus.SUCCESS

        node = SequenceNode(
            [
                ActionNode(success),
                ActionNode(success),
                ActionNode(success),
            ]
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_sequence_fails_on_first_failure(self):
        """Sequence should return FAILURE on first child failure."""

        def success(context):
            return NodeStatus.SUCCESS

        def failure(context):
            return NodeStatus.FAILURE

        node = SequenceNode(
            [
                ActionNode(success),
                ActionNode(failure),
                ActionNode(success),  # Should not execute
            ]
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.FAILURE

    def test_sequence_running(self):
        """Sequence should return RUNNING if child returns RUNNING."""

        def success(context):
            return NodeStatus.SUCCESS

        def running(context):
            return NodeStatus.RUNNING

        node = SequenceNode(
            [
                ActionNode(success),
                ActionNode(running),
                ActionNode(success),  # Should not execute yet
            ]
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING

    def test_sequence_resumes_after_running(self):
        """Sequence should resume from RUNNING child."""
        counter = {"value": 0}
        running_count = {"value": 0}

        def increment(context):
            counter["value"] += 1
            return NodeStatus.SUCCESS

        def running_then_success(context):
            running_count["value"] += 1
            if running_count["value"] < 3:
                return NodeStatus.RUNNING
            return NodeStatus.SUCCESS

        node = SequenceNode(
            [
                ActionNode(increment),
                ActionNode(running_then_success),
                ActionNode(increment),
            ]
        )
        context = MockContext()

        # First tick: child 0 succeeds, child 1 runs
        status = node.tick(context)
        assert status == NodeStatus.RUNNING
        assert counter["value"] == 1
        assert running_count["value"] == 1

        # Second tick: child 1 still running (doesn't re-execute child 0)
        status = node.tick(context)
        assert status == NodeStatus.RUNNING
        assert counter["value"] == 1  # Should not increment again
        assert running_count["value"] == 2

        # Third tick: child 1 succeeds, child 2 executes
        status = node.tick(context)
        assert status == NodeStatus.SUCCESS
        assert counter["value"] == 2  # Child 2 increments
        assert running_count["value"] == 3


class TestSelectorNode:
    """Test SelectorNode functionality."""

    def test_selector_first_success(self):
        """Selector should return SUCCESS on first success."""

        def success(context):
            return NodeStatus.SUCCESS

        def failure(context):
            return NodeStatus.FAILURE

        node = SelectorNode(
            [
                ActionNode(failure),
                ActionNode(success),
                ActionNode(failure),  # Should not execute
            ]
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_selector_all_fail(self):
        """Selector should return FAILURE if all children fail."""

        def failure(context):
            return NodeStatus.FAILURE

        node = SelectorNode(
            [
                ActionNode(failure),
                ActionNode(failure),
                ActionNode(failure),
            ]
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.FAILURE

    def test_selector_running(self):
        """Selector should return RUNNING if child returns RUNNING."""

        def failure(context):
            return NodeStatus.FAILURE

        def running(context):
            return NodeStatus.RUNNING

        node = SelectorNode(
            [
                ActionNode(failure),
                ActionNode(running),
                ActionNode(failure),  # Should not execute yet
            ]
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING


class TestParallelNode:
    """Test ParallelNode functionality."""

    def test_parallel_success_threshold(self):
        """Parallel should succeed when threshold met."""

        def success(context):
            return NodeStatus.SUCCESS

        def failure(context):
            return NodeStatus.FAILURE

        node = ParallelNode(
            children=[
                ActionNode(success),
                ActionNode(success),
                ActionNode(failure),
            ],
            success_threshold=2,
            failure_threshold=2,
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_parallel_failure_threshold(self):
        """Parallel should fail when threshold met."""

        def success(context):
            return NodeStatus.SUCCESS

        def failure(context):
            return NodeStatus.FAILURE

        node = ParallelNode(
            children=[
                ActionNode(failure),
                ActionNode(failure),
                ActionNode(success),
            ],
            success_threshold=2,
            failure_threshold=2,
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.FAILURE

    def test_parallel_running(self):
        """Parallel should return RUNNING if thresholds not met."""

        def success(context):
            return NodeStatus.SUCCESS

        def failure(context):
            return NodeStatus.FAILURE

        def running(context):
            return NodeStatus.RUNNING

        node = ParallelNode(
            children=[
                ActionNode(success),
                ActionNode(failure),
                ActionNode(running),
            ],
            success_threshold=2,
            failure_threshold=2,
        )
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING


class TestInverterNode:
    """Test InverterNode functionality."""

    def test_inverter_success_to_failure(self):
        """Inverter should convert SUCCESS to FAILURE."""

        def success(context):
            return NodeStatus.SUCCESS

        node = InverterNode(ActionNode(success))
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.FAILURE

    def test_inverter_failure_to_success(self):
        """Inverter should convert FAILURE to SUCCESS."""

        def failure(context):
            return NodeStatus.FAILURE

        node = InverterNode(ActionNode(failure))
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_inverter_preserves_running(self):
        """Inverter should preserve RUNNING status."""

        def running(context):
            return NodeStatus.RUNNING

        node = InverterNode(ActionNode(running))
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING


class TestRepeaterNode:
    """Test RepeaterNode functionality."""

    def test_repeater_finite_count(self):
        """Repeater should repeat N times then succeed."""
        counter = {"value": 0}

        def increment(context):
            counter["value"] += 1
            return NodeStatus.SUCCESS

        node = RepeaterNode(ActionNode(increment), count=3)
        context = MockContext()

        # First 3 ticks should be RUNNING
        for i in range(3):
            status = node.tick(context)
            if i < 2:
                assert status == NodeStatus.RUNNING

        # Final tick should succeed
        assert status == NodeStatus.SUCCESS
        assert counter["value"] == 3

    def test_repeater_infinite(self):
        """Repeater with count=-1 should repeat infinitely."""
        counter = {"value": 0}

        def increment(context):
            counter["value"] += 1
            return NodeStatus.SUCCESS

        node = RepeaterNode(ActionNode(increment), count=-1)
        context = MockContext()

        # Tick many times, should always be RUNNING
        for _ in range(100):
            status = node.tick(context)
            assert status == NodeStatus.RUNNING

        assert counter["value"] == 100

    def test_repeater_running_child(self):
        """Repeater should preserve child RUNNING status."""
        runs = {"count": 0}

        def running(context):
            runs["count"] += 1
            return NodeStatus.RUNNING

        node = RepeaterNode(ActionNode(running), count=3)
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING
        # Should not count as repetition yet
        assert runs["count"] == 1


class TestSucceederNode:
    """Test SucceederNode functionality."""

    def test_succeeder_converts_failure(self):
        """Succeeder should convert FAILURE to SUCCESS."""

        def failure(context):
            return NodeStatus.FAILURE

        node = SucceederNode(ActionNode(failure))
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_succeeder_preserves_success(self):
        """Succeeder should preserve SUCCESS."""

        def success(context):
            return NodeStatus.SUCCESS

        node = SucceederNode(ActionNode(success))
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_succeeder_preserves_running(self):
        """Succeeder should preserve RUNNING."""

        def running(context):
            return NodeStatus.RUNNING

        node = SucceederNode(ActionNode(running))
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING


class TestUntilFailNode:
    """Test UntilFailNode functionality."""

    def test_until_fail_repeats(self):
        """UntilFail should repeat while child succeeds."""
        counter = {"value": 0}

        def increment_until_threshold(context):
            counter["value"] += 1
            if counter["value"] < 5:
                return NodeStatus.SUCCESS
            return NodeStatus.FAILURE

        node = UntilFailNode(ActionNode(increment_until_threshold))
        context = MockContext()

        # Tick until child fails
        for i in range(5):
            status = node.tick(context)
            if i < 4:
                assert status == NodeStatus.RUNNING

        # Final tick should succeed (child failed)
        assert status == NodeStatus.SUCCESS
        assert counter["value"] == 5

    def test_until_fail_running_child(self):
        """UntilFail should preserve child RUNNING status."""

        def running(context):
            return NodeStatus.RUNNING

        node = UntilFailNode(ActionNode(running))
        context = MockContext()

        status = node.tick(context)

        assert status == NodeStatus.RUNNING


class TestBehaviorTree:
    """Test BehaviorTree functionality."""

    def test_tree_creation(self):
        """BehaviorTree should initialize correctly."""

        def success(context):
            return NodeStatus.SUCCESS

        tree = BehaviorTree(root=ActionNode(success), name="TestTree")

        assert tree.name == "TestTree"
        assert not tree.is_running

    def test_tree_tick(self):
        """BehaviorTree should execute root node."""

        def success(context):
            return NodeStatus.SUCCESS

        tree = BehaviorTree(root=ActionNode(success))
        context = MockContext()

        status = tree.tick(context)

        assert status == NodeStatus.SUCCESS

    def test_tree_running_state(self):
        """BehaviorTree should track running state."""

        def running(context):
            return NodeStatus.RUNNING

        tree = BehaviorTree(root=ActionNode(running))
        context = MockContext()

        tree.tick(context)

        assert tree.is_running

    def test_tree_auto_reset_on_completion(self):
        """BehaviorTree should reset after completion."""
        counter = {"value": 0}

        def increment(context):
            counter["value"] += 1
            return NodeStatus.SUCCESS

        tree = BehaviorTree(root=ActionNode(increment))
        context = MockContext()

        # First tick
        tree.tick(context)
        assert counter["value"] == 1

        # Second tick (tree reset, should execute again)
        tree.tick(context)
        assert counter["value"] == 2

    def test_tree_manual_reset(self):
        """BehaviorTree should support manual reset."""

        def running(context):
            return NodeStatus.RUNNING

        tree = BehaviorTree(root=ActionNode(running))
        context = MockContext()

        tree.tick(context)
        assert tree.is_running

        tree.reset()
        assert not tree.is_running


class TestBehaviorTreeIntegration:
    """Test complex behavior tree scenarios."""

    def test_enemy_ai_tree(self):
        """Test realistic enemy AI behavior tree."""
        context = MockContext()
        context.health = 30
        context.enemy_visible = True
        context.enemy_close = False

        def is_health_low(ctx):
            return ctx.health < 50

        def is_enemy_visible(ctx):
            return ctx.enemy_visible

        def is_enemy_close(ctx):
            return ctx.enemy_close

        def flee(ctx):
            ctx.values.append("flee")
            return NodeStatus.SUCCESS

        def attack(ctx):
            ctx.values.append("attack")
            return NodeStatus.SUCCESS

        def patrol(ctx):
            ctx.values.append("patrol")
            return NodeStatus.SUCCESS

        tree = BehaviorTree(
            root=SelectorNode(
                [
                    # Priority 1: Flee if low health
                    SequenceNode([ConditionNode(is_health_low), ActionNode(flee)]),
                    # Priority 2: Attack if enemy close
                    SequenceNode([ConditionNode(is_enemy_close), ActionNode(attack)]),
                    # Priority 3: Default patrol
                    ActionNode(patrol),
                ]
            )
        )

        # Low health - should flee
        tree.tick(context)
        assert context.values == ["flee"]

        # High health, enemy not close - should patrol
        context.values.clear()
        context.health = 100
        tree.tick(context)
        assert context.values == ["patrol"]

        # Enemy close - should attack
        context.values.clear()
        context.enemy_close = True
        tree.tick(context)
        assert context.values == ["attack"]

    def test_complex_sequence_with_wait(self):
        """Test sequence with wait node."""
        context = MockContext()

        def action1(ctx):
            ctx.values.append("action1")
            return NodeStatus.SUCCESS

        def action2(ctx):
            ctx.values.append("action2")
            return NodeStatus.SUCCESS

        tree = BehaviorTree(
            root=SequenceNode(
                [
                    ActionNode(action1),
                    WaitNode(duration=0.05),
                    ActionNode(action2),
                ]
            )
        )

        # First tick: action1 + wait starts
        status = tree.tick(context)
        assert status == NodeStatus.RUNNING
        assert context.values == ["action1"]

        # Continue ticking until wait completes
        for _ in range(3):
            status = tree.tick(context)

        # Wait completes, action2 executes
        assert status == NodeStatus.SUCCESS
        assert "action2" in context.values


class TestReactiveComposites:
    """Guards that keep being checked, and children that get aborted.

    `SequenceNode`/`SelectorNode` have *memory*: once a composite advances
    past a child it resumes at the one that was RUNNING and never re-ticks
    the earlier ones. That silently breaks the commonest way a behaviour
    tree is written -- a guard at the front of a sequence stops being
    evaluated the moment the sequence moves on, so the enemy keeps
    attacking after the player breaks line of sight, and nothing reports a
    problem (#46).

    These tests pin the bug as well as the fix: the memory variants must
    keep behaving exactly as before, because changing their default would
    silently alter every tree already written against them.
    """

    @staticmethod
    def _guarded_sequence(cls, visible: dict, attacks: list):
        """`[is_player_visible, attack]`, the pattern from the issue."""
        return cls(
            [
                ConditionNode(lambda _ctx: visible["v"]),
                ActionNode(lambda _ctx: (attacks.append(1), NodeStatus.RUNNING)[1]),
            ]
        )

    def test_a_memory_sequence_keeps_running_after_its_guard_fails(self):
        """The bug, pinned deliberately. Not aspirational -- this is current
        documented behaviour, and `ReactiveSequenceNode` exists because of
        it. If this ever starts failing, the default changed and every
        existing tree changed with it."""
        visible = {"v": True}
        attacks: list[int] = []
        node = self._guarded_sequence(SequenceNode, visible, attacks)
        context = MockContext()

        node.tick(context)
        visible["v"] = False
        node.tick(context)
        node.tick(context)

        assert len(attacks) == 3  # kept attacking, unseen player

    def test_a_reactive_sequence_stops_when_its_guard_fails(self):
        visible = {"v": True}
        attacks: list[int] = []
        node = self._guarded_sequence(ReactiveSequenceNode, visible, attacks)
        context = MockContext()

        node.tick(context)
        visible["v"] = False
        status = node.tick(context)

        assert status == NodeStatus.FAILURE
        assert len(attacks) == 1  # only the tick where it could see

    def test_the_memory_flag_is_the_same_thing_by_another_name(self):
        visible = {"v": True}
        attacks: list[int] = []
        node = self._guarded_sequence(SequenceNode, visible, attacks)
        node.memory = False
        context = MockContext()

        node.tick(context)
        visible["v"] = False
        node.tick(context)

        assert len(attacks) == 1

    def test_a_reactive_selector_lets_a_higher_branch_take_over(self):
        """The whole point of ordering a selector by priority: with memory,
        dropping to low health never interrupts an already-running patrol."""
        danger = {"on": False}
        log: list[str] = []

        def branch(name: str, gate):
            return SequenceNode(
                [
                    ConditionNode(lambda _ctx: gate()),
                    ActionNode(lambda _ctx: (log.append(name), NodeStatus.RUNNING)[1]),
                ]
            )

        node = ReactiveSelectorNode(
            [
                branch("flee", lambda: danger["on"]),
                branch("patrol", lambda: True),
            ]
        )
        context = MockContext()

        node.tick(context)
        assert log == ["patrol"]

        danger["on"] = True
        node.tick(context)
        assert log == ["patrol", "flee"]  # pre-empted, as priority implies

    def test_a_memory_selector_does_not_let_it_take_over(self):
        """The counterpart, so the difference is pinned from both sides."""
        danger = {"on": False}
        log: list[str] = []

        def branch(name: str, gate):
            return SequenceNode(
                [
                    ConditionNode(lambda _ctx: gate()),
                    ActionNode(lambda _ctx: (log.append(name), NodeStatus.RUNNING)[1]),
                ]
            )

        node = SelectorNode(
            [
                branch("flee", lambda: danger["on"]),
                branch("patrol", lambda: True),
            ]
        )
        context = MockContext()

        node.tick(context)
        danger["on"] = True
        node.tick(context)

        assert log == ["patrol", "patrol"]  # flee never gets a look in


class TestPreemptedChildIsAborted:
    """A pre-empted RUNNING child must be reset, not merely forgotten.

    Otherwise it keeps its internal state -- a part-elapsed `WaitNode`, a
    half-finished action -- and resumes from the middle the next time the
    branch is reached. That is what "abort" means in a behaviour tree, and
    it is the half of reactive composites that is easy to miss: the first
    implementation of this change cleared the bookkeeping without resetting
    the child, and a test like this is what caught it.
    """

    def test_a_failing_guard_resets_the_running_child(self):
        gate = {"ok": True}
        wait = WaitNode(5.0)
        node = ReactiveSequenceNode([ConditionNode(lambda _ctx: gate["ok"]), wait])
        context = MockContext()

        node.tick(context)
        assert wait._elapsed > 0

        gate["ok"] = False
        node.tick(context)

        assert wait._elapsed == 0.0

    def test_a_higher_priority_branch_resets_the_lower_one(self):
        danger = {"on": False}
        patrol_wait = WaitNode(5.0)
        node = ReactiveSelectorNode(
            [
                SequenceNode([ConditionNode(lambda _ctx: danger["on"])]),
                patrol_wait,
            ]
        )
        context = MockContext()

        node.tick(context)
        assert patrol_wait._elapsed > 0

        danger["on"] = True
        node.tick(context)

        assert patrol_wait._elapsed == 0.0

    def test_success_also_aborts_a_running_child(self):
        """A composite finishing has pre-empted whatever was mid-flight,
        exactly as a higher branch does."""
        wait = WaitNode(5.0)
        node = ReactiveSelectorNode([wait, ActionNode(lambda _ctx: NodeStatus.SUCCESS)])
        context = MockContext()

        node.tick(context)  # wait RUNNING
        assert wait._elapsed > 0

        # Make the wait fail so the selector moves on and succeeds.
        wait.duration = -1.0
        node.tick(context)

        assert wait._elapsed == 0.0

    def test_reset_clears_the_running_bookkeeping(self):
        wait = WaitNode(5.0)
        node = ReactiveSequenceNode([wait])
        node.tick(MockContext())

        node.reset()

        assert node._running_child is None
        assert wait._elapsed == 0.0


class TestParallelLatching:
    """A finished child must not be re-ticked (#46, P1).

    `ParallelNode` re-ran every child each tick, including ones that had
    already returned SUCCESS, so `ParallelNode([fire_weapon_once, wait_5s])`
    fired the weapon on every tick of the wait. Reproduced at 60/60 before
    the fix.
    """

    @staticmethod
    def _one_shot_and_wait(latch: bool):
        fired: list[int] = []
        node = ParallelNode(
            [
                ActionNode(lambda _ctx: (fired.append(1), NodeStatus.SUCCESS)[1]),
                WaitNode(5.0),
            ],
            success_threshold=2,
            failure_threshold=1,
            latch=latch,
        )
        return node, fired

    def test_a_finished_child_runs_once(self) -> None:
        node, fired = self._one_shot_and_wait(latch=True)
        context = MockContext()

        for _ in range(60):
            node.tick(context)

        assert len(fired) == 1

    def test_opting_out_restores_the_old_behaviour(self) -> None:
        """Kept as an escape hatch for a node whose children are all
        idempotent polls."""
        node, fired = self._one_shot_and_wait(latch=False)
        context = MockContext()

        for _ in range(60):
            node.tick(context)

        assert len(fired) == 60

    def test_latched_results_still_count_towards_the_threshold(self) -> None:
        """Latching must not lose the result it remembered, or a parallel
        could never reach its success threshold."""
        node = ParallelNode(
            [
                ActionNode(lambda _ctx: NodeStatus.SUCCESS),
                WaitNode(0.05),
            ],
            success_threshold=2,
            failure_threshold=1,
        )
        context = MockContext()

        statuses = [node.tick(context) for _ in range(10)]

        assert NodeStatus.SUCCESS in statuses

    def test_resolving_clears_the_latch(self) -> None:
        """Otherwise the node would resolve immediately on its next use."""
        calls: list[int] = []
        node = ParallelNode(
            [ActionNode(lambda _ctx: (calls.append(1), NodeStatus.SUCCESS)[1])],
            success_threshold=1,
        )
        context = MockContext()

        node.tick(context)
        node.tick(context)

        assert len(calls) == 2

    def test_reset_clears_the_latch(self) -> None:
        node = ParallelNode(
            [ActionNode(lambda _ctx: NodeStatus.SUCCESS)], success_threshold=2
        )
        node.tick(MockContext())
        node.reset()
        assert node._finished == {}


class TestBlackboardNodes:
    """Stock nodes, so a tree can be data rather than closures (#46).

    Every leaf used to be a hand-written lambda, which cannot be serialised
    -- so an editor-authored or data-driven tree was impossible.
    """

    @staticmethod
    def _context() -> Any:
        from dataclasses import dataclass

        from pyguara.ai.blackboard import Blackboard

        @dataclass
        class Ctx:
            blackboard: Blackboard
            dt: float = 0.016

        return Ctx(Blackboard())

    def test_a_comparison_succeeds_and_fails(self) -> None:
        context = self._context()
        context.blackboard.set("health", 15)

        assert BlackboardCondition("health", "<", 20).tick(context) is (
            NodeStatus.SUCCESS
        )
        assert BlackboardCondition("health", ">", 20).tick(context) is (
            NodeStatus.FAILURE
        )

    def test_an_absent_key_fails_rather_than_raising(self) -> None:
        """A tree asking "is the player visible" before anything set that
        key should take the else-branch, not crash the frame."""
        assert BlackboardCondition("nope", "==", 1).tick(self._context()) is (
            NodeStatus.FAILURE
        )

    def test_incomparable_types_fail_rather_than_raising(self) -> None:
        """One mistyped blackboard value should not take the frame down."""
        context = self._context()
        context.blackboard.set("name", "boss")

        assert BlackboardCondition("name", "<", 5).tick(context) is (NodeStatus.FAILURE)

    def test_an_unknown_operator_is_rejected_at_construction(self) -> None:
        """Where the mistake was made, not mid-frame three states later."""
        with pytest.raises(ValueError, match="Unsupported operator"):
            BlackboardCondition("k", "~=", 1)

    def test_every_operator_works(self) -> None:
        context = self._context()
        context.blackboard.set("n", 5)
        expected = {
            "==": True,
            "!=": False,
            "<": False,
            "<=": True,
            ">": False,
            ">=": True,
        }
        for op, want in expected.items():
            status = BlackboardCondition("n", op, 5).tick(context)
            assert (status is NodeStatus.SUCCESS) is want, op

    def test_set_blackboard_writes_and_succeeds(self) -> None:
        context = self._context()

        assert SetBlackboard("alerted", True).tick(context) is NodeStatus.SUCCESS
        assert context.blackboard.get("alerted") is True

    def test_nodes_fail_without_a_blackboard(self) -> None:
        """A tree ticked with a bare entity rather than an `AIContext`."""
        assert BlackboardCondition("k", "==", 1).tick(object()) is NodeStatus.FAILURE
        assert SetBlackboard("k", 1).tick(object()) is NodeStatus.FAILURE


class TestCooldownNode:
    def test_it_rate_limits_its_child(self) -> None:
        """Without this a dash or special attack fires as fast as the frame
        rate allows."""
        casts: list[int] = []
        node = CooldownNode(
            0.5, ActionNode(lambda _ctx: (casts.append(1), NodeStatus.SUCCESS)[1])
        )
        context = MockContext()
        context.dt = 1 / 60

        for _ in range(40):
            node.tick(context)

        assert len(casts) == 2  # once, then again after 30 ticks

    def test_a_cooling_child_reports_failure(self) -> None:
        """FAILURE, not RUNNING: a cooling-down ability is a branch that
        cannot be taken, so a selector should move on. RUNNING would block
        the branch for the whole cooldown."""
        node = CooldownNode(1.0, ActionNode(lambda _ctx: NodeStatus.SUCCESS))
        context = MockContext()

        node.tick(context)

        assert node.tick(context) is NodeStatus.FAILURE

    def test_the_cooldown_starts_when_the_child_finishes(self) -> None:
        """Not when it starts -- a long action is not cut short, and the gap
        is measured from the end of the last use."""
        node = CooldownNode(1.0, WaitNode(0.05))
        context = MockContext()

        assert node.tick(context) is NodeStatus.RUNNING
        assert node._remaining == 0.0  # still running, not yet cooling

    def test_reset_clears_a_pending_cooldown(self) -> None:
        node = CooldownNode(5.0, ActionNode(lambda _ctx: NodeStatus.SUCCESS))
        node.tick(MockContext())

        node.reset()

        assert node._remaining == 0.0


class TestRandomSelector:
    def test_it_tries_every_child_before_failing(self) -> None:
        import random

        log: list[int] = []
        node = RandomSelector(
            [
                ActionNode(lambda _ctx, i=i: (log.append(i), NodeStatus.FAILURE)[1])
                for i in range(3)
            ],
            rng=random.Random(42),
        )

        assert node.tick(MockContext()) is NodeStatus.FAILURE
        assert sorted(log) == [0, 1, 2]

    def test_it_succeeds_on_the_first_success(self) -> None:
        import random

        log: list[int] = []

        def child(index: int, status: NodeStatus):
            return ActionNode(lambda _ctx: (log.append(index), status)[1])

        node = RandomSelector(
            [child(0, NodeStatus.SUCCESS), child(1, NodeStatus.SUCCESS)],
            rng=random.Random(1),
        )

        assert node.tick(MockContext()) is NodeStatus.SUCCESS
        assert len(log) == 1

    def test_the_order_is_reproducible_for_a_seeded_rng(self) -> None:
        """Injectable randomness, so a test -- or a replay -- is
        deterministic."""
        import random

        def run(seed: int) -> list[int]:
            log: list[int] = []
            node = RandomSelector(
                [
                    ActionNode(lambda _ctx, i=i: (log.append(i), NodeStatus.FAILURE)[1])
                    for i in range(4)
                ],
                rng=random.Random(seed),
            )
            node.tick(MockContext())
            return log

        assert run(7) == run(7)

    def test_a_running_child_keeps_its_turn(self) -> None:
        """The order is shuffled when the node starts, not every tick, so a
        child mid-action is not abandoned."""
        import random

        node = RandomSelector([WaitNode(1.0)], rng=random.Random(3))
        context = MockContext()

        assert node.tick(context) is NodeStatus.RUNNING
        assert node.tick(context) is NodeStatus.RUNNING

    def test_an_empty_selector_fails(self) -> None:
        assert RandomSelector([]).tick(MockContext()) is NodeStatus.FAILURE
