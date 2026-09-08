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

Collisions generate events via the `CollisionSystem`, which `bootstrap.py`
wires to the physics engine. Subscribe on the `EventDispatcher`:

*   **`OnCollisionBegin` / `OnCollisionPersist` / `OnCollisionEnd`**: two
    solid (non-sensor) colliders touching.
*   **`OnTriggerEnter` / `OnTriggerStay` / `OnTriggerExit`**: something
    overlapping a sensor collider.

```python
def on_collision(self, event: OnCollisionBegin):
    print(f"Entities {event.entity_a} and {event.entity_b} collided!")
```

The engine reports a contact pair in Chipmunk's own order and tells
`CollisionSystem` which side owns the sensor; the trigger events always come
out with `trigger_entity` set to the sensor's entity and `other_entity` the
body that entered it, regardless of that order.

## Trigger volumes

A `TriggerVolume` component is the high-level way to use a sensor: it keeps a
live `entities_inside` set and supports tag filtering and one-shot
deactivation. It needs **three** systems running -- `PhysicsSystem`,
`CollisionSystem`, and `TriggerSystem` (the last is opt-in; create one and
tick it each frame). `TriggerSystem` gives the entity the pieces it needs to
enter the simulation:

*   a sensor `Collider` matching the volume's shape, and
*   a static `RigidBody`, if the entity has none -- `PhysicsSystem` only
    registers shapes for entities that have a body. Add your own KINEMATIC
    `RigidBody` instead if the trigger has to move with a platform.

```python
zone = entity_manager.create_entity()
zone.add_component(Transform(position=Vector2(400, 300)))
zone.add_component(TriggerVolume(
    shape_type=ShapeType.BOX, dimensions=[100, 100], tags={"player"},
))
# ...later, any frame:
if zone.get_component(TriggerVolume).contains_entity(player.id):
    ...
```

## Joints

`Joint` connects two entities' `RigidBody` bodies -- pin, distance, spring,
slider. The component is pure data; `pyguara.physics.joint_system.JointSystem`
is what turns it into a real constraint. Like `PhysicsSystem` it is opt-in:
create one and tick it each fixed step, **after** `PhysicsSystem.update()`.

```python
from pyguara.physics.joints import create_pin_joint

bob.add_component(create_pin_joint(target_entity_id=anchor.id))
```

`JointSystem` builds the constraint once both entities have a body in the
engine (retrying on later ticks until then), and destroys it when either
entity is removed or the `Joint` component is taken off its entity. Factory
helpers: `create_pin_joint`, `create_distance_joint`, `create_spring_joint`,
`create_slider_joint`, plus `create_rope_chain` for a segmented rope.

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
