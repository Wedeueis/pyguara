"""ECS components for AI."""

from dataclasses import dataclass, field
from typing import Optional, List

from pyguara.common.types import Vector2
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.fsm import StateMachine
from pyguara.ecs.component import BaseComponent


@dataclass
class AIComponent(BaseComponent):
    """
    Component that holds the AI brain (FSM or Behavior Tree).

    Attributes:
        blackboard: Shared memory for this agent.
        fsm: Optional Finite State Machine.
        enabled: Whether AI logic should run.
    """

    blackboard: Blackboard = field(default_factory=Blackboard)
    fsm: Optional[StateMachine] = None
    enabled: bool = True

    def __post_init__(self) -> None:
        """Call superclass init after initialization."""
        super().__init__()


@dataclass
class SteeringAgent(BaseComponent):
    """
    Component that defines movement capabilities.

    Attributes:
        max_speed: Maximum movement speed.
        max_force: Maximum steering force (turn speed/acceleration).
        mass: Used to calculate acceleration (Force / Mass).
    """

    max_speed: float = 200.0
    max_force: float = 500.0
    mass: float = 1.0

    def __post_init__(self) -> None:
        """Call superclass init after initialization."""
        super().__init__()


@dataclass
class Navigator(BaseComponent):
    """
    Component that handles pathfollowing.

    Attributes:
        path: Current list of waypoints.
        current_index: Which waypoint we are moving toward.
        reach_threshold: How close to get before switching to next waypoint.
    """

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
