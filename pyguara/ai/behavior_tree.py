"""Behavior tree system for hierarchical AI decision-making.

Behavior trees provide a modular, reusable way to structure AI logic.
Nodes return SUCCESS, FAILURE, or RUNNING status.
"""

import operator
import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, ClassVar

from pyguara.log import get_logger

logger = get_logger(__name__)


class NodeStatus(Enum):
    """Status returned by behavior tree nodes."""

    SUCCESS = auto()
    FAILURE = auto()
    RUNNING = auto()


# Fallback frame delta for WaitNode when the tick context carries no `dt`.
# AISystem passes an AIContext with a real dt; this only bites a tree ticked
# with a bare object, and is deliberately visible rather than a bare literal.
_WAIT_FALLBACK_DT = 1.0 / 60.0


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
        dt = getattr(context, "dt", _WAIT_FALLBACK_DT)
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

    def __init__(
        self,
        children: list[BehaviorNode],
        name: str = "",
        *,
        memory: bool = True,
    ):
        """Initialize composite node.

        Args:
            children: List of child nodes
            name: Optional name for debugging
            memory: Whether to resume at the child that was RUNNING instead
                of re-ticking from the first one. True keeps the historical
                behaviour; see the subclasses for why False is usually what
                an author meant.
        """
        super().__init__(name)
        self.children = children
        self.memory = memory
        self._current_child = 0
        # Which child was RUNNING on the previous tick, so a reactive
        # composite can abort it when a different branch takes over.
        self._running_child: int | None = None

    def reset(self) -> None:
        """Reset this node and all children."""
        super().reset()
        self._current_child = 0
        self._running_child = None
        for child in self.children:
            child.reset()

    def _start_index(self) -> int:
        """Return the child index this tick should begin at.

        Returns:
            The remembered child with memory, or 0 without it -- which is
            what makes a guard at the front of the list keep being checked.
        """
        return self._current_child if self.memory else 0

    def _abort_running(self) -> None:
        """Reset a child left mid-flight because this composite finished.

        A composite that returns SUCCESS or FAILURE while one of its
        children was RUNNING has pre-empted that child, exactly as a
        higher-priority branch does. Clearing the bookkeeping without
        resetting the child would leave it holding a part-elapsed
        `WaitNode` or a half-finished action, which then resumes from the
        middle the next time the branch is reached.
        """
        if self._running_child is not None:
            self.children[self._running_child].reset()
            self._running_child = None

    def _note_running(self, index: int) -> None:
        """Record which child is RUNNING, aborting a pre-empted one.

        A child that was RUNNING and is no longer the one being ticked has
        been pre-empted by a higher-priority branch. Resetting it is what
        "abort" means for a behaviour tree: without it the child keeps its
        internal state -- a half-elapsed `WaitNode`, a part-finished action
        -- and resumes mid-way if it is reached again later.

        Args:
            index: The child that returned RUNNING this tick.
        """
        if self._running_child is not None and self._running_child != index:
            self.children[self._running_child].reset()
        self._running_child = index
        self._current_child = index


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

    def __init__(
        self,
        children: list[BehaviorNode],
        name: str = "Sequence",
        *,
        memory: bool = True,
    ):
        """Initialize sequence node.

        Args:
            children: List of child nodes to execute in order
            name: Optional name for debugging
            memory: Resume at the RUNNING child (True, the historical
                behaviour) or re-tick from the first child every tick
                (False). See `ReactiveSequenceNode` for why False is
                usually what a guarded sequence meant.
        """
        super().__init__(children, name, memory=memory)

    def tick(self, context: Any) -> NodeStatus:
        """Execute children sequentially."""
        index = self._start_index()
        while index < len(self.children):
            status = self.children[index].tick(context)

            if status == NodeStatus.FAILURE:
                self._status = NodeStatus.FAILURE
                self._current_child = 0
                self._abort_running()
                return self._status

            if status == NodeStatus.RUNNING:
                self._status = NodeStatus.RUNNING
                self._note_running(index)
                return self._status

            # Success - move to next child
            index += 1
            self._current_child = index

        # All children succeeded
        self._status = NodeStatus.SUCCESS
        self._current_child = 0
        self._abort_running()
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

    def __init__(
        self,
        children: list[BehaviorNode],
        name: str = "Selector",
        *,
        memory: bool = True,
    ):
        """Initialize selector node.

        Args:
            children: List of child nodes to try in order
            name: Optional name for debugging
            memory: Resume at the RUNNING child (True, the historical
                behaviour) or re-tick from the first child every tick
                (False). See `ReactiveSelectorNode`.
        """
        super().__init__(children, name, memory=memory)

    def tick(self, context: Any) -> NodeStatus:
        """Try children until one succeeds."""
        index = self._start_index()
        while index < len(self.children):
            status = self.children[index].tick(context)

            if status == NodeStatus.SUCCESS:
                self._status = NodeStatus.SUCCESS
                self._current_child = 0
                self._abort_running()
                return self._status

            if status == NodeStatus.RUNNING:
                self._status = NodeStatus.RUNNING
                self._note_running(index)
                return self._status

            # Failure - move to next child
            index += 1
            self._current_child = index

        # All children failed
        self._status = NodeStatus.FAILURE
        self._current_child = 0
        self._abort_running()
        return self._status


class ReactiveSequenceNode(SequenceNode):
    """A sequence that re-checks its guards every tick.

    The ordinary `SequenceNode` has *memory*: once it advances past a child
    it resumes at the one that was RUNNING and never re-ticks the earlier
    ones. That quietly breaks the most common way a behaviour tree is
    written:

        >>> SequenceNode([
        ...     ConditionNode(is_player_visible),
        ...     ActionNode(chase),
        ...     ActionNode(attack),
        ... ])

    The condition is checked once. The moment the sequence moves on to
    `chase`, `is_player_visible` stops being evaluated -- so the enemy keeps
    chasing and attacking after the player breaks line of sight, and
    nothing anywhere reports a problem. The tree reads correctly; it just
    does not do what it says.

    A reactive sequence starts from the first child on every tick, so a
    guard at the front is a guard for as long as the branch runs. When a
    failing guard pre-empts a child that was RUNNING, that child is
    `reset()` -- the abort -- so it does not resume half-finished later.

    This is what most authors mean by a sequence; the memory variant is the
    specialised one. The default is unchanged only because changing it would
    silently alter every tree already written against it.
    """

    def __init__(self, children: list[BehaviorNode], name: str = "ReactiveSequence"):
        """Initialize a memoryless sequence.

        Args:
            children: List of child nodes to execute in order
            name: Optional name for debugging
        """
        super().__init__(children, name, memory=False)


class ReactiveSelectorNode(SelectorNode):
    """A selector that re-checks higher-priority branches every tick.

    The ordinary `SelectorNode` resumes at the child that was RUNNING, so a
    higher-priority branch that becomes viable mid-action never gets a
    chance to take over:

        >>> SelectorNode([
        ...     SequenceNode([is_health_low, flee]),
        ...     SequenceNode([is_enemy_close, attack]),
        ...     ActionNode(patrol),
        ... ])

    Once `patrol` is RUNNING, dropping to low health does not interrupt it.
    A reactive selector re-ticks from the top, so the first viable branch
    wins on every tick -- which is the entire point of ordering a selector
    by priority.

    The pre-empted child is `reset()` when a higher branch takes over, so
    `patrol` does not resume mid-stride once the danger passes.
    """

    def __init__(self, children: list[BehaviorNode], name: str = "ReactiveSelector"):
        """Initialize a memoryless selector.

        Args:
            children: List of child nodes to try in priority order
            name: Optional name for debugging
        """
        super().__init__(children, name, memory=False)


class ParallelNode(CompositeNode):
    """Executes all children simultaneously.

    Returns SUCCESS if success_threshold children succeed.
    Returns FAILURE if failure_threshold children fail.
    Returns RUNNING otherwise.

    A child that has finished is **latched**: its result is remembered and
    it is not ticked again until this node itself resolves. Without that,
    every tick re-ran children that had already succeeded --
    `ParallelNode([fire_weapon_once, wait_5s])` fired the weapon on all
    ~300 ticks of the wait rather than once (#46, reproduced at 60/60
    before this change).

    Latching is the conventional parallel semantic and is on by default;
    `latch=False` restores the historical re-tick-everything behaviour for
    a node whose children are all idempotent polls.

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
        *,
        latch: bool = True,
    ):
        """Initialize parallel node.

        Args:
            children: List of child nodes to execute in parallel
            success_threshold: Number of successes needed to succeed
            failure_threshold: Number of failures needed to fail
            name: Optional name for debugging
            latch: Stop ticking a child once it has finished, remembering
                its result until this node resolves. True is both the
                conventional semantic and the fix for re-firing one-shot
                actions; False re-ticks everything every tick.
        """
        super().__init__(children, name)
        self.success_threshold = success_threshold
        self.failure_threshold = failure_threshold
        self.latch = latch
        # Latched results by child index, cleared when this node resolves.
        self._finished: dict[int, NodeStatus] = {}

    def reset(self) -> None:
        """Reset this node, its children, and any latched results."""
        super().reset()
        self._finished.clear()

    def tick(self, context: Any) -> NodeStatus:
        """Execute all children in parallel."""
        success_count = 0
        failure_count = 0

        for index, child in enumerate(self.children):
            if self.latch and index in self._finished:
                status = self._finished[index]
            else:
                status = child.tick(context)
                if self.latch and status in (
                    NodeStatus.SUCCESS,
                    NodeStatus.FAILURE,
                ):
                    self._finished[index] = status

            if status == NodeStatus.SUCCESS:
                success_count += 1
            elif status == NodeStatus.FAILURE:
                failure_count += 1

        # Check thresholds
        if success_count >= self.success_threshold:
            self._status = NodeStatus.SUCCESS
            self._finished.clear()
            for child in self.children:
                child.reset()
            return self._status

        if failure_count >= self.failure_threshold:
            self._status = NodeStatus.FAILURE
            self._finished.clear()
            for child in self.children:
                child.reset()
            return self._status

        # Still running
        self._status = NodeStatus.RUNNING
        return self._status


# Decorator Nodes


class BlackboardCondition(BehaviorNode):
    """Compare a blackboard value without writing a closure.

    Every behaviour-tree leaf used to be a hand-written lambda, which makes
    a data-driven or editor-authored tree impossible -- you cannot
    serialise a closure (#46). These stock nodes are the authoring
    vocabulary: a tree built from them is describable as data.

    The operator set is deliberately small and total: equality and ordering
    cover the conditions a game actually asks about, and anything stranger
    is still a `ConditionNode` away.

    Example:
        >>> BlackboardCondition("health", "<", 20)
    """

    OPERATORS: ClassVar[dict[str, Callable[[Any, Any], bool]]] = {
        "==": operator.eq,
        "!=": operator.ne,
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
    }

    def __init__(
        self,
        key: str,
        op: str,
        value: Any,
        name: str = "BlackboardCondition",
    ):
        """Initialize the condition.

        Args:
            key: The blackboard key to read.
            op: One of `==`, `!=`, `<`, `<=`, `>`, `>=`.
            value: The value to compare against.
            name: Optional name for debugging.

        Raises:
            ValueError: If `op` is not a supported operator. Raised at
                construction rather than on the first tick, so a misspelt
                tree fails where it was built instead of mid-frame.
        """
        super().__init__(name)
        if op not in self.OPERATORS:
            raise ValueError(
                f"Unsupported operator {op!r}. Expected one of "
                f"{sorted(self.OPERATORS)}."
            )
        self.key = key
        self.op = op
        self.value = value

    def tick(self, context: Any) -> NodeStatus:
        """Compare the blackboard value, failing if the key is absent."""
        blackboard = getattr(context, "blackboard", None)
        if blackboard is None or not blackboard.has(self.key):
            # An absent key is a failed condition, not an error: a tree
            # that asks "is the player visible" before anything has set
            # that key should take the else-branch, not crash.
            self._status = NodeStatus.FAILURE
            return self._status

        try:
            result = self.OPERATORS[self.op](blackboard.get(self.key), self.value)
        except TypeError:
            # Comparing incomparable types -- a string against an int, say.
            # Failing beats propagating: one mistyped blackboard value
            # should not take the whole frame down.
            logger.warning(
                "BlackboardCondition(%r %s %r): incomparable types, failing",
                self.key,
                self.op,
                self.value,
            )
            self._status = NodeStatus.FAILURE
            return self._status

        self._status = NodeStatus.SUCCESS if result else NodeStatus.FAILURE
        return self._status


class SetBlackboard(BehaviorNode):
    """Write a blackboard value and succeed.

    The write half of the authoring vocabulary -- enough to latch a flag,
    remember a target, or count something without a closure.

    Example:
        >>> SetBlackboard("alerted", True)
    """

    def __init__(self, key: str, value: Any, name: str = "SetBlackboard"):
        """Initialize the write.

        Args:
            key: The blackboard key to set.
            value: The value to store.
            name: Optional name for debugging.
        """
        super().__init__(name)
        self.key = key
        self.value = value

    def tick(self, context: Any) -> NodeStatus:
        """Set the value, failing only if there is no blackboard to set on."""
        blackboard = getattr(context, "blackboard", None)
        if blackboard is None:
            self._status = NodeStatus.FAILURE
            return self._status
        blackboard.set(self.key, self.value)
        self._status = NodeStatus.SUCCESS
        return self._status


class RandomSelector(CompositeNode):
    """Try children in a shuffled order until one succeeds.

    A selector picks by priority, which makes a guard dog predictable. This
    picks by chance, which is what idle variation, attack choice and barks
    want.

    The order is reshuffled when the node starts, not on every tick, so a
    child that returns RUNNING keeps its turn rather than being abandoned
    mid-action.

    Example:
        >>> RandomSelector([bark, sniff, scratch])
    """

    def __init__(
        self,
        children: list[BehaviorNode],
        name: str = "RandomSelector",
        *,
        rng: random.Random | None = None,
    ):
        """Initialize the selector.

        Args:
            children: Children to try in random order.
            name: Optional name for debugging.
            rng: Source of randomness. Injectable so a test -- or a replay
                -- is reproducible; `pyguara.common.random.RandomStream`
                wraps the engine's seeded stream for the same reason.
        """
        super().__init__(children, name)
        self._rng = rng or random.Random()
        self._order: list[int] = []

    def reset(self) -> None:
        """Reset this node, its children, and the shuffled order."""
        super().reset()
        self._order = []

    def tick(self, context: Any) -> NodeStatus:
        """Try children in a shuffled order until one succeeds."""
        if not self.children:
            self._status = NodeStatus.FAILURE
            return self._status

        if not self._order:
            self._order = list(range(len(self.children)))
            self._rng.shuffle(self._order)

        while self._current_child < len(self._order):
            child = self.children[self._order[self._current_child]]
            status = child.tick(context)

            if status == NodeStatus.SUCCESS:
                # Cleared *before* recording the result: `reset()` sets
                # `_status` to FAILURE, so assigning first and resetting
                # second returned FAILURE from a successful tick. Caught by
                # a test that expected SUCCESS from two succeeding children.
                self.reset()
                self._status = NodeStatus.SUCCESS
                return self._status

            if status == NodeStatus.RUNNING:
                self._status = NodeStatus.RUNNING
                return self._status

            self._current_child += 1

        self.reset()
        self._status = NodeStatus.FAILURE
        return self._status


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


class CooldownNode(DecoratorNode):
    """Refuse to run a child again until a delay has elapsed.

    The rate limit every ability needs. Without it a tree re-attempts its
    child on every tick, so a dash, a shout or a special attack fires as
    fast as the frame rate allows.

    The cooldown starts when the child **finishes**, not when it starts, so
    a long-running action is not cut short and the gap is measured from the
    end of the last use. A child that returns RUNNING is left alone.

    Reads `context.dt`, as `WaitNode` does: wall-clock time would make the
    cooldown depend on how long the game spent paused.

    Example:
        >>> CooldownNode(5.0, ActionNode(cast_fireball))
    """

    def __init__(
        self,
        seconds: float,
        child: BehaviorNode,
        name: str = "Cooldown",
    ):
        """Initialize the cooldown.

        Args:
            seconds: How long to refuse after the child finishes.
            child: The node to rate-limit.
            name: Optional name for debugging.
        """
        super().__init__(child, name)
        self.seconds = seconds
        self._remaining = 0.0

    def reset(self) -> None:
        """Reset this node and its child, clearing any pending cooldown."""
        super().reset()
        self._remaining = 0.0

    def tick(self, context: Any) -> NodeStatus:
        """Tick the child unless the cooldown is still running."""
        dt = getattr(context, "dt", 1.0 / 60.0)

        if self._remaining > 0.0:
            self._remaining = max(0.0, self._remaining - dt)
            # FAILURE rather than RUNNING: a cooling-down ability is a
            # branch that cannot be taken, so a selector should move on to
            # the next option. RUNNING would block the whole branch for the
            # length of the cooldown.
            self._status = NodeStatus.FAILURE
            return self._status

        status = self.child.tick(context)
        if status != NodeStatus.RUNNING:
            self._remaining = self.seconds
        self._status = status
        return self._status


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
