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

## Platformer characters: CharacterMover, not RigidBody

A platformer character is the one thing that should **not** be a `RigidBody`.
Assigning it velocity and letting the solver resolve overlap after the fact
is what produces sinking, seam catching, wall creep and tunnelling — a
character pressed into geometry is briefly inside it until the solver pushes
it back out.

Instead, give it a `CharacterBody` (velocity, ground state, knockback) and a
`Collider` used only for its dimensions — no shape is registered with the
physics engine at all. `PlatformerSystem` sweeps it every tick with
`CharacterMover`, which advances one whole pixel at a time and stops flush
the instant a step would overlap something, so penetration cannot occur by
construction.

The same model extends to what the character touches:

- **`MovingSolid`** + **`SolidSystem`** carry or push any `CharacterBody`
  a moving platform touches (riding on top, or shoved from the side).
- **`Pushable`**, added to a `MovingSolid`, lets a character shove it —
  a crate, say — instead of just stopping at it.
- **`apply_knockback()`** overrides a character's velocity for a short,
  decaying window, for hits and explosions.

`RigidBody` is still the right choice for everything else — crates before
they're pushed, ragdolls, projectiles, the level's static geometry. See
`docs/physics/character-movement.md` for why this split exists and the
defects it fixes.
