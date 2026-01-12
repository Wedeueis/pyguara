"""AI systems for PyGuara.

Provides behavior trees, finite state machines, steering behaviors,
and other AI utilities.
"""

from pyguara.ai.behavior_tree import (
    ActionNode,
    BehaviorNode,
    BehaviorTree,
    CompositeNode,
    ConditionNode,
    DecoratorNode,
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
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.components import AIComponent
from pyguara.ai.fsm import State, StateMachine
from pyguara.ai.pathfinding import (
    AStar,
    GridMap,
    Heuristic,
    diagonal_distance,
    euclidean_distance,
    manhattan_distance,
    octile_distance,
    path_to_world_coords,
    smooth_path,
    world_to_grid_coords,
)

__all__ = [
    # Behavior Trees
    "BehaviorNode",
    "ActionNode",
    "ConditionNode",
    "WaitNode",
    "CompositeNode",
    "SequenceNode",
    "SelectorNode",
    "ParallelNode",
    "DecoratorNode",
    "InverterNode",
    "RepeaterNode",
    "SucceederNode",
    "UntilFailNode",
    "NodeStatus",
    "BehaviorTree",
    # FSM
    "State",
    "StateMachine",
    # Components
    "AIComponent",
    # Blackboard
    "Blackboard",
    # Pathfinding
    "AStar",
    "GridMap",
    "Heuristic",
    "manhattan_distance",
    "euclidean_distance",
    "diagonal_distance",
    "octile_distance",
    "smooth_path",
    "path_to_world_coords",
    "world_to_grid_coords",
]
