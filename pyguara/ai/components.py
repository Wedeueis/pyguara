"""ECS components for AI."""

from dataclasses import dataclass, field
from typing import Optional, List, TYPE_CHECKING

from pyguara.common.types import Vector2
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.fsm import StateMachine
from pyguara.ecs.component import BaseComponent

if TYPE_CHECKING:
    from pyguara.ai.behavior_tree import BehaviorTree


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
    fsm: Optional[StateMachine] = None
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
        slowing_radius: Distance at which to start slowing for arrive behavior.
        behavior: Active steering behavior type.
    """

    max_speed: float = 200.0
    max_force: float = 500.0
    mass: float = 1.0
    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    target: Optional[Vector2] = None
    slowing_radius: float = 100.0
    behavior: str = "seek"  # "seek", "arrive", "flee", "wander"
    enabled: bool = True

    def __post_init__(self) -> None:
        """Call superclass init after initialization."""
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

    path: List[Vector2] = field(default_factory=list)
    current_index: int = 0
    reach_threshold: float = 5.0

    def set_path(self, path: List[Vector2]) -> None:
        """Set the path defined by a list of vectors."""
        self.path = path
        self.current_index = 0

    def get_current_target(self) -> Optional[Vector2]:
        """Return the current imediate destination."""
        if 0 <= self.current_index < len(self.path):
            return self.path[self.current_index]
        return None
