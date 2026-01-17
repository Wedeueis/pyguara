# Physics System

PyGuara integrates **Pymunk** (Chipmunk2D) for physics simulation, abstracted behind the `IPhysicsEngine` protocol.

## Components

### RigidBody
Represents a physical object.
- **Dynamic**: Affected by forces and gravity.
- **Static**: Immovable (walls, ground).
- **Kinematic**: Moved by code but affects dynamic bodies (platforms).

### Collider
Defines the collision shape and properties.
- **Shapes**: `BOX`, `CIRCLE`.
- **Properties**: Friction, Restitution (bounciness), Density.
- **Trigger**: `is_sensor=True` makes it a non-solid trigger volume.

## PhysicsSystem

The `PhysicsSystem` synchronizes the ECS `Transform` component with the Pymunk body simulation.
- **Pre-Step**: Updates Pymunk bodies if ECS transforms changed (Kinematic/Manual).
- **Step**: Advances simulation (`dt`).
- **Post-Step**: Updates ECS transforms from Pymunk bodies (Dynamic).

## Collision Handling

Collisions generate events via the `CollisionSystem`.

*   **`OnCollisionBegin`**: Physical contact started.
*   **`OnCollisionEnd`**: Physical contact ended.
*   **`OnTriggerEnter`**: Entered a trigger volume.

```python
def on_collision(self, event: OnCollisionBegin):
    print(f"Entities {event.entity_a} and {event.entity_b} collided!")
```
