"""Tests for behavior tree system."""

from pyguara.ai.behavior_tree import (
    ActionNode,
    BehaviorTree,
    ConditionNode,
    InverterNode,
    NodeStatus,
    ParallelNode,
    RepeaterNode,
    SelectorNode,
    SequenceNode,
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
