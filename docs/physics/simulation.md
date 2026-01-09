# Physics System

PyGuara integrates **Pymunk** (Chipmunk2D) for physics simulation, abstracted behind the `IPhysicsEngine` protocol.

## Components

### RigidBody
Represents a physical object.
- **Dynamic**: Affected by forces and gravity.
- **Static**: Immovable (walls).
- **Kinematic**: Moved by code (platforms).

### Collider
Defines the collision shape (`BOX`, `CIRCLE`). Supports collision layers and masking.

## PhysicsSystem

The `PhysicsSystem` synchronizes the ECS `Transform` component with the Pymunk body simulation.
- **Pre-Step**: Updates Pymunk bodies if ECS transforms changed (Kinematic).
- **Step**: Advances simulation (`dt`).
- **Post-Step**: Updates ECS transforms from Pymunk bodies (Dynamic).

---

# AI System

Located in `pyguara.ai`, the AI module provides tools for building autonomous agents.

## Features

- **Finite State Machines (FSM)**: Class-based states (`State`) with `on_enter`, `update`, and `on_exit` hooks.
- **Steering Behaviors**: `Seek`, `Arrive`, and `Flee` logic for natural movement.
- **Blackboard**: Shared memory pattern for decoupling AI logic from data.
- **Pathfinding**: A* implementation (`AStarPathfinder`) working on generic Graphs/Grids.

---

# Input System

The `InputManager` (`pyguara.input`) acts as a translation layer.

1.  **Raw Input**: Captures low-level events (Key presses, Joystick axis).
2.  **Binding**: Maps raw inputs to Semantic Actions (e.g., "SPACE" -> "Jump").
3.  **Action Dispatch**: Emits `OnActionEvent` for game logic to consume.

This allows rebindable controls and multi-device support (Keyboard, Mouse, Gamepad) transparently to the gameplay code.
