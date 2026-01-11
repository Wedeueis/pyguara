"""Behavior tree system for hierarchical AI decision-making.

Behavior trees provide a modular, reusable way to structure AI logic.
Nodes return SUCCESS, FAILURE, or RUNNING status.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable


class NodeStatus(Enum):
    """Status returned by behavior tree nodes."""

    SUCCESS = auto()
    FAILURE = auto()
    RUNNING = auto()


class BehaviorNode(ABC):
    """Base class for all behavior tree nodes."""

    def __init__(self, name: str = ""):
        """Initialize behavior node.

        Args:
            name: Optional name for debugging
        """
        self.name = name or self.__class__.__name__
        self._status: NodeStatus = NodeStatus.FAILURE

    @abstractmethod
    def tick(self, context: Any) -> NodeStatus:
        """Execute the node's behavior.

        Args:
            context: Shared context object (e.g., entity, blackboard)

        Returns:
            NodeStatus indicating result
        """
        pass

    def reset(self) -> None:
        """Reset the node to initial state."""
        self._status = NodeStatus.FAILURE

    @property
    def status(self) -> NodeStatus:
        """Get the last status returned by this node."""
        return self._status


# Leaf Nodes


class ActionNode(BehaviorNode):
    """Executes an action and returns success/failure.

    Example:
        >>> def move_to_target(context):
        ...     context.position += context.velocity
        ...     return NodeStatus.SUCCESS
        >>> action = ActionNode(move_to_target)
    """

    def __init__(self, action: Callable[[Any], NodeStatus], name: str = "Action"):
        """Initialize action node.

        Args:
            action: Callable that takes context and returns NodeStatus
            name: Optional name for debugging
        """
        super().__init__(name)
        self._action = action

    def tick(self, context: Any) -> NodeStatus:
        """Execute the action."""
        self._status = self._action(context)
        return self._status


class ConditionNode(BehaviorNode):
    """Checks a condition and returns success/failure.

    Example:
        >>> def is_health_low(context):
        ...     return context.health < 20
        >>> condition = ConditionNode(is_health_low)
    """

    def __init__(self, condition: Callable[[Any], bool], name: str = "Condition"):
        """Initialize condition node.

        Args:
            condition: Callable that takes context and returns bool
            name: Optional name for debugging
        """
        super().__init__(name)
        self._condition = condition

    def tick(self, context: Any) -> NodeStatus:
        """Check the condition."""
        result = self._condition(context)
        self._status = NodeStatus.SUCCESS if result else NodeStatus.FAILURE
        return self._status


class WaitNode(BehaviorNode):
    """Returns RUNNING for a specified duration, then SUCCESS.

    Example:
        >>> wait = WaitNode(duration=2.0)  # Wait 2 seconds
    """

    def __init__(self, duration: float, name: str = "Wait"):
        """Initialize wait node.

        Args:
            duration: Time to wait in seconds
            name: Optional name for debugging
        """
        super().__init__(name)
        self.duration = duration
        self._elapsed = 0.0

    def tick(self, context: Any) -> NodeStatus:
        """Update wait timer."""
        dt = getattr(context, "dt", 0.016)  # Default to ~60 FPS
        self._elapsed += dt

        if self._elapsed >= self.duration:
            self._status = NodeStatus.SUCCESS
        else:
            self._status = NodeStatus.RUNNING

        return self._status

    def reset(self) -> None:
        """Reset wait timer."""
        super().reset()
        self._elapsed = 0.0


# Composite Nodes


class CompositeNode(BehaviorNode):
    """Base class for nodes with multiple children."""

    def __init__(self, children: list[BehaviorNode], name: str = ""):
        """Initialize composite node.

        Args:
            children: List of child nodes
            name: Optional name for debugging
        """
        super().__init__(name)
        self.children = children
        self._current_child = 0

    def reset(self) -> None:
        """Reset this node and all children."""
        super().reset()
        self._current_child = 0
        for child in self.children:
            child.reset()


class SequenceNode(CompositeNode):
    """Executes children in order until one fails.

    Returns SUCCESS if all children succeed.
    Returns FAILURE if any child fails.
    Returns RUNNING if a child returns RUNNING.

    Example:
        >>> sequence = SequenceNode([
        ...     ConditionNode(is_enemy_visible),
        ...     ActionNode(aim_at_enemy),
        ...     ActionNode(shoot)
        ... ])
    """

    def __init__(self, children: list[BehaviorNode], name: str = "Sequence"):
        """Initialize sequence node.

        Args:
            children: List of child nodes to execute in order
            name: Optional name for debugging
        """
        super().__init__(children, name)

    def tick(self, context: Any) -> NodeStatus:
        """Execute children sequentially."""
        while self._current_child < len(self.children):
            status = self.children[self._current_child].tick(context)

            if status == NodeStatus.FAILURE:
                self._status = NodeStatus.FAILURE
                self._current_child = 0
                return self._status

            if status == NodeStatus.RUNNING:
                self._status = NodeStatus.RUNNING
                return self._status

            # Success - move to next child
            self._current_child += 1

        # All children succeeded
        self._status = NodeStatus.SUCCESS
        self._current_child = 0
        return self._status


class SelectorNode(CompositeNode):
    """Executes children in order until one succeeds.

    Returns SUCCESS if any child succeeds.
    Returns FAILURE if all children fail.
    Returns RUNNING if a child returns RUNNING.

    Example:
        >>> selector = SelectorNode([
        ...     SequenceNode([is_health_low, flee]),
        ...     SequenceNode([is_enemy_close, attack]),
        ...     ActionNode(patrol)
        ... ])
    """

    def __init__(self, children: list[BehaviorNode], name: str = "Selector"):
        """Initialize selector node.

        Args:
            children: List of child nodes to try in order
            name: Optional name for debugging
        """
        super().__init__(children, name)

    def tick(self, context: Any) -> NodeStatus:
        """Try children until one succeeds."""
        while self._current_child < len(self.children):
            status = self.children[self._current_child].tick(context)

            if status == NodeStatus.SUCCESS:
                self._status = NodeStatus.SUCCESS
                self._current_child = 0
                return self._status

            if status == NodeStatus.RUNNING:
                self._status = NodeStatus.RUNNING
                return self._status

            # Failure - move to next child
            self._current_child += 1

        # All children failed
        self._status = NodeStatus.FAILURE
        self._current_child = 0
        return self._status


class ParallelNode(CompositeNode):
    """Executes all children simultaneously.

    Returns SUCCESS if success_threshold children succeed.
    Returns FAILURE if failure_threshold children fail.
    Returns RUNNING otherwise.

    Example:
        >>> parallel = ParallelNode(
        ...     children=[move_to_target, scan_for_enemies, play_animation],
        ...     success_threshold=2,
        ...     failure_threshold=2
        ... )
    """

    def __init__(
        self,
        children: list[BehaviorNode],
        success_threshold: int = 1,
        failure_threshold: int = 1,
        name: str = "Parallel",
    ):
        """Initialize parallel node.

        Args:
            children: List of child nodes to execute in parallel
            success_threshold: Number of successes needed to succeed
            failure_threshold: Number of failures needed to fail
            name: Optional name for debugging
        """
        super().__init__(children, name)
        self.success_threshold = success_threshold
        self.failure_threshold = failure_threshold

    def tick(self, context: Any) -> NodeStatus:
        """Execute all children in parallel."""
        success_count = 0
        failure_count = 0

        for child in self.children:
            status = child.tick(context)

            if status == NodeStatus.SUCCESS:
                success_count += 1
            elif status == NodeStatus.FAILURE:
                failure_count += 1

        # Check thresholds
        if success_count >= self.success_threshold:
            self._status = NodeStatus.SUCCESS
            for child in self.children:
                child.reset()
            return self._status

        if failure_count >= self.failure_threshold:
            self._status = NodeStatus.FAILURE
            for child in self.children:
                child.reset()
            return self._status

        # Still running
        self._status = NodeStatus.RUNNING
        return self._status


# Decorator Nodes


class DecoratorNode(BehaviorNode):
    """Base class for nodes that modify a single child's behavior."""

    def __init__(self, child: BehaviorNode, name: str = ""):
        """Initialize decorator node.

        Args:
            child: Child node to decorate
            name: Optional name for debugging
        """
        super().__init__(name)
        self.child = child

    def reset(self) -> None:
        """Reset this node and child."""
        super().reset()
        self.child.reset()


class InverterNode(DecoratorNode):
    """Inverts child's result (SUCCESS <-> FAILURE).

    RUNNING is unchanged.

    Example:
        >>> inverter = InverterNode(ConditionNode(is_enemy_visible))
        >>> # Returns SUCCESS when enemy is NOT visible
    """

    def __init__(self, child: BehaviorNode, name: str = "Inverter"):
        """Initialize inverter node.

        Args:
            child: Child node to invert
            name: Optional name for debugging
        """
        super().__init__(child, name)

    def tick(self, context: Any) -> NodeStatus:
        """Invert child's result."""
        status = self.child.tick(context)

        if status == NodeStatus.SUCCESS:
            self._status = NodeStatus.FAILURE
        elif status == NodeStatus.FAILURE:
            self._status = NodeStatus.SUCCESS
        else:
            self._status = NodeStatus.RUNNING

        return self._status


class RepeaterNode(DecoratorNode):
    """Repeats child N times or infinitely.

    Example:
        >>> repeater = RepeaterNode(ActionNode(patrol), count=5)
        >>> # OR infinite:
        >>> repeater = RepeaterNode(ActionNode(patrol), count=-1)
    """

    def __init__(self, child: BehaviorNode, count: int = -1, name: str = "Repeater"):
        """Initialize repeater node.

        Args:
            child: Child node to repeat
            count: Number of repetitions (-1 = infinite)
            name: Optional name for debugging
        """
        super().__init__(child, name)
        self.count = count
        self._current_count = 0

    def tick(self, context: Any) -> NodeStatus:
        """Repeat child execution."""
        if self.count != -1 and self._current_count >= self.count:
            self._status = NodeStatus.SUCCESS
            self._current_count = 0
            return self._status

        status = self.child.tick(context)

        if status == NodeStatus.RUNNING:
            self._status = NodeStatus.RUNNING
            return self._status

        # Child completed (success or failure)
        self.child.reset()
        self._current_count += 1

        if self.count == -1 or self._current_count < self.count:
            self._status = NodeStatus.RUNNING
        else:
            self._status = NodeStatus.SUCCESS
            self._current_count = 0

        return self._status

    def reset(self) -> None:
        """Reset repeater and count."""
        super().reset()
        self._current_count = 0


class SucceederNode(DecoratorNode):
    """Always returns SUCCESS regardless of child result.

    Example:
        >>> succeeder = SucceederNode(ActionNode(try_optional_task))
        >>> # Task failure won't stop parent sequence
    """

    def __init__(self, child: BehaviorNode, name: str = "Succeeder"):
        """Initialize succeeder node.

        Args:
            child: Child node to execute
            name: Optional name for debugging
        """
        super().__init__(child, name)

    def tick(self, context: Any) -> NodeStatus:
        """Execute child and return SUCCESS."""
        status = self.child.tick(context)

        if status == NodeStatus.RUNNING:
            self._status = NodeStatus.RUNNING
        else:
            self._status = NodeStatus.SUCCESS

        return self._status


class UntilFailNode(DecoratorNode):
    """Repeats child until it fails.

    Example:
        >>> until_fail = UntilFailNode(ActionNode(collect_resources))
        >>> # Keeps collecting until resources run out
    """

    def __init__(self, child: BehaviorNode, name: str = "UntilFail"):
        """Initialize until-fail node.

        Args:
            child: Child node to repeat
            name: Optional name for debugging
        """
        super().__init__(child, name)

    def tick(self, context: Any) -> NodeStatus:
        """Repeat child until failure."""
        status = self.child.tick(context)

        if status == NodeStatus.FAILURE:
            self._status = NodeStatus.SUCCESS
            self.child.reset()
            return self._status

        if status == NodeStatus.RUNNING:
            self._status = NodeStatus.RUNNING
            return self._status

        # Child succeeded - reset and continue
        self.child.reset()
        self._status = NodeStatus.RUNNING
        return self._status


@dataclass
class BehaviorTree:
    """Manages execution of a behavior tree.

    Example:
        >>> tree = BehaviorTree(
        ...     root=SelectorNode([
        ...         SequenceNode([is_hungry, find_food, eat]),
        ...         SequenceNode([is_tired, find_shelter, sleep]),
        ...         ActionNode(wander)
        ...     ])
        ... )
        >>> # In game loop:
        >>> tree.tick(entity)
    """

    root: BehaviorNode
    name: str = "BehaviorTree"
    _running: bool = field(default=False, init=False)

    def tick(self, context: Any) -> NodeStatus:
        """Execute the behavior tree.

        Args:
            context: Shared context (entity, blackboard, etc.)

        Returns:
            Root node's status
        """
        status = self.root.tick(context)

        if status == NodeStatus.RUNNING:
            self._running = True
        else:
            self._running = False
            self.root.reset()

        return status

    def reset(self) -> None:
        """Reset the entire tree."""
        self.root.reset()
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if tree is currently running."""
        return self._running
