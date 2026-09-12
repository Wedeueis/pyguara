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

## Measured ceiling

`FlockingSystem` has been benchmarked — see
[Measured Limits](../guides/performance.md) for the full table.

**Roughly 1,000 fully-simulated boids fit in a 60 Hz frame**, or about 2,000
with steering staggered to 20 Hz. Three things follow from the measurements:

- **Density is an independent variable.** A flocking tick is O(n·k) — n agents
  each visiting k neighbours — so a flock converging on one point costs far
  more than the same flock spread out: 3,000 agents cost 53 ms scattered and
  162 ms clumped. A horde running at a player is the clumped case.
- **Steering can be spread across ticks.** `FlockingSystem(..., groups=N)`
  re-decides one group's heading per tick while every agent keeps integrating
  its position, so nothing stutters and only the decision rate drops. It does
  not scale as 1/N — the hash rebuild and the integration are paid every tick
  whatever group an agent is in.
- **The spatial hash was never the bottleneck.** Rebuilding it for 3,000 agents
  takes 3.1 ms, which supports the full per-tick rebuild `FlockingSystem`
  deliberately does. The cost that dominated was `Vector2` arithmetic in the
  inner loop, ahead of per-neighbour entity and component re-lookup.
