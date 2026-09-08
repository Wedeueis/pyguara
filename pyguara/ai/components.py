"""ECS components for AI."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

from pyguara.ai.blackboard import Blackboard
from pyguara.ai.fsm import StateMachine
from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent

if TYPE_CHECKING:
    from pyguara.ai.behavior_tree import BehaviorTree


class SteeringBehaviorType(str, Enum):
    """Steering behavior a ``SteeringAgent`` runs each frame.

    Subclasses ``str`` so an agent constructed with a plain string
    (``SteeringAgent(behavior="seek")``) and serialized forms keep working;
    ``SteeringAgent.__post_init__`` coerces the field to this enum and raises
    ``ValueError`` on an unknown name rather than silently producing no force.
    """

    SEEK = "seek"
    ARRIVE = "arrive"
    FLEE = "flee"
    WANDER = "wander"
    PURSUIT = "pursuit"
    EVADE = "evade"


@dataclass
class AIComponent(BaseComponent):
    """
    Component that holds the AI brain (FSM or Behavior Tree).

    Attributes:
        blackboard: Shared memory for this agent.
        fsm: Optional Finite State Machine.
        behavior_tree: Optional Behavior Tree for hierarchical decision-making.
        enabled: Whether AI logic should run.
    """

    blackboard: Blackboard = field(default_factory=Blackboard)
    fsm: StateMachine | None = None
    behavior_tree: Optional["BehaviorTree"] = None
    enabled: bool = True

    def __post_init__(self) -> None:
        """Call superclass init after initialization."""
        super().__init__()


@dataclass
class SteeringAgent(BaseComponent):
    """
    Component that defines movement capabilities for autonomous agents.

    Attributes:
        max_speed: Maximum movement speed.
        max_force: Maximum steering force (turn speed/acceleration).
        mass: Used to calculate acceleration (Force / Mass).
        velocity: Current velocity of the agent.
        target: Target position for steering (if None, uses Navigator path).
        target_velocity: Velocity of the target, used by ``pursuit``/``evade``
            to lead a moving target. The caller refreshes it each frame
            alongside ``target``; ignored by the other behaviors.
        slowing_radius: Distance at which to start slowing for arrive behavior.
        behavior: Active steering behavior. Accepts a ``SteeringBehaviorType``
            or its string value; coerced in ``__post_init__``.
    """

    max_speed: float = 200.0
    max_force: float = 500.0
    mass: float = 1.0
    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    target: Vector2 | None = None
    target_velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    slowing_radius: float = 100.0
    behavior: SteeringBehaviorType = SteeringBehaviorType.SEEK
    enabled: bool = True

    def __post_init__(self) -> None:
        """Coerce ``behavior`` to the enum, then call superclass init."""
        # Raises ValueError on an unknown name -- fail at construction rather
        # than run every frame producing a zero force with no diagnostic.
        self.behavior = SteeringBehaviorType(self.behavior)
        super().__init__()


@dataclass
class Navigator(BaseComponent):
    """Component that handles pathfollowing.

    Attributes:
        path: Current list of waypoints.
        current_index: Which waypoint we are moving toward.
        reach_threshold: How close to get before switching to next waypoint.

    Note:
        This is a legacy component with path management methods. Ideally,
        path logic would be in a NavigationSystem.
    """

    _allow_methods: bool = field(default=True, repr=False, init=False)

    path: list[Vector2] = field(default_factory=list)
    current_index: int = 0
    reach_threshold: float = 5.0

    def set_path(self, path: list[Vector2]) -> None:
        """Set the path defined by a list of vectors."""
        self.path = path
        self.current_index = 0

    def get_current_target(self) -> Vector2 | None:
        """Return the current imediate destination."""
        if 0 <= self.current_index < len(self.path):
            return self.path[self.current_index]
        return None
