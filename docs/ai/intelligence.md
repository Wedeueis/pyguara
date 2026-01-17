# AI System

The AI module (`pyguara.ai`) provides a robust suite of tools for creating intelligent agents, from simple state machines to complex behavior trees.

## 🧠 Behavior Trees

PyGuara features a professional-grade Behavior Tree (BT) implementation, perfect for complex decision-making.

### Core Components

*   **BehaviorTree**: The runner that executes the tree.
*   **Nodes**:
    *   **ActionNode**: Executes a function (Leaf). Returns `SUCCESS`, `FAILURE`, or `RUNNING`.
    *   **ConditionNode**: Checks a boolean predicate (Leaf).
    *   **SequenceNode**: Runs children in order until one fails (AND logic).
    *   **SelectorNode**: Runs children in order until one succeeds (OR logic).
    *   **ParallelNode**: Runs children simultaneously.
*   **Decorators**:
    *   `InverterNode`, `RepeaterNode`, `SucceederNode`, `UntilFailNode`.

### Usage Example

```python
from pyguara.ai.behavior_tree import BehaviorTree, SequenceNode, ActionNode, NodeStatus

def move_to_player(context):
    # Logic...
    return NodeStatus.SUCCESS

def attack_player(context):
    # Logic...
    return NodeStatus.SUCCESS

# Define structure
root = SequenceNode([
    ActionNode(move_to_player),
    ActionNode(attack_player)
])

# Create component
ai_component = AIComponent()
ai_component.behavior_tree = BehaviorTree(root)
```

## 🔄 Finite State Machines (FSM)

For simpler logic, use the FSM system.

*   **State**: Abstract base class with `on_enter`, `update`, `on_exit`.
*   **StateMachine**: Manages current state and transitions.

## 🧭 Pathfinding & Steering

*   **AStarPathfinder**: Grid and Graph based pathfinding.
*   **Steering**: Common behaviors like `Seek`, `Flee`, and `Arrive` for natural movement.
*   **Navmesh**: Tools for generating and navigating walkable surfaces.

## 📝 Blackboard

The **Blackboard** pattern allows different AI systems (or nodes in a BT) to share data (e.g., "TargetPosition", "AlertLevel") without tight coupling.
