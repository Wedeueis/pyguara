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
from pyguara.ai import AIComponent
from pyguara.ai.behavior_tree import BehaviorTree, SequenceNode, ActionNode, NodeStatus

def move_to_player(context):
    # context.entity, context.dt, context.blackboard are available
    return NodeStatus.SUCCESS

def attack_player(context):
    return NodeStatus.SUCCESS

# Define structure -- leaves are wrapped in ActionNode/ConditionNode
root = SequenceNode([
    ActionNode(move_to_player),
    ActionNode(attack_player),
])

# Attach to an entity; AISystem ticks the tree once per frame
ai_component = AIComponent(behavior_tree=BehaviorTree(root))
```

### The tick context

`AISystem` passes each tree an **`AIContext`** (`pyguara.ai.AIContext`) with
`entity`, `dt`, and `blackboard` fields. Timing nodes such as `WaitNode` read
`context.dt`; ticking a tree with a bare object that has no `dt` falls back to a
fixed step and drifts with the real frame rate.

## 🔄 Finite State Machines (FSM)

For simpler logic, use the FSM system.

*   **State**: Abstract base class with `on_enter`, `update`, `on_exit`.
*   **StateMachine**: Manages current state and transitions. `add_state(name,
    state)` registers a state; `set_initial_state(name)` and a state's
    `update()` return value drive transitions by name. An unknown name is
    logged as a warning and ignored -- the machine is not left in a half-
    transitioned state.

## 🧭 Pathfinding & Steering

*   **AStarPathfinder**: A generic A* solver over any `Graph` (a `get_neighbors`
    / `cost` protocol). Graph nodes only need to be hashable, not orderable.
*   **GridGraph**: A concrete 4/8-directional grid with pluggable heuristics
    (`ManhattanDistance`, `EuclideanDistance`, `DiagonalDistance`,
    `OctileDistance`), `smooth_path`, and `world_to_grid_coords` /
    `path_to_world_coords` (both floor toward negative infinity, so a non-zero
    grid `offset` works).
*   **Steering**: `SteeringSystem` runs an entity's `SteeringAgent` each frame.
    `SteeringAgent.behavior` is a `SteeringBehaviorType`: `SEEK`, `ARRIVE`,
    `FLEE`, `WANDER`, `PURSUIT`, `EVADE`. `PURSUIT` and `EVADE` intercept or
    dodge a *moving* target -- set `SteeringAgent.target_velocity` alongside
    `target`. An unknown behavior string is rejected when the component is
    built.
*   **Navmesh**: `NavMesh` holds convex polygons you supply and connects those
    that share a full edge; `NavMeshPathfinder.find_path` runs A* over the
    polygon graph and returns polygon-center waypoints. Funnel string-pulling
    and partial-edge portals are not yet implemented.

## 📝 Blackboard

The **Blackboard** pattern allows different AI systems (or nodes in a BT) to share data (e.g., "TargetPosition", "AlertLevel") without tight coupling.
