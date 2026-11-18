# Physics System

PyGuara simulates physics with **Rapier**, in the native extension, behind
the `IPhysicsEngine` protocol. It replaced **pymunk** (Chipmunk2D); see
[Coming from pymunk](#coming-from-pymunk).

## Components

### RigidBody
Represents a physical object the physics engine simulates.
- **Dynamic**: Affected by forces and gravity.
- **Static**: Immovable (walls, ground).
- **Kinematic**: Moved by code but affects dynamic bodies (platforms).

A **player character is the exception** — it should carry a `CharacterBody`,
not a `RigidBody`. See [Platformer characters](#platformer-characters-charactermover-not-rigidbody)
below.

### Collider
Defines the collision shape and properties.
- **Shapes**: `BOX`, `CIRCLE`.
- **Properties**: Friction, Restitution (bounciness), Density.
- **Trigger**: `is_sensor=True` makes it a non-solid trigger volume.

## PhysicsSystem

The `PhysicsSystem` synchronizes the ECS `Transform` component with the physics engine's bodies.
- **Pre-Step**: Updates the engine's bodies if ECS transforms changed (Kinematic/Manual).
- **Step**: Advances simulation (`dt`).
- **Post-Step**: Updates ECS transforms from the engine's bodies (Dynamic).

### Substepping

The world runs no continuous collision detection, so in principle a body
moving `velocity × dt` in one solver step can pass through anything thinner
than that jump. `physics.substeps` (default **4**) splits each tick into
that many solver steps to shorten it.

In practice Rapier keeps thin walls solid without them. Measured with
`tests/integration/test_collision_robustness.py`'s `fire_at_wall` and **one**
substep, an 8px box stops at a 10px wall at 20,000 px/s (333px a step), and
a 1px box at a 1px wall. Only a circle of 1 or 2px fired into a wall as
thin, at 20,000 px/s, came out just past it. Chipmunk tunnelled at 1,200
px/s through that 10px wall with one substep. Fast projectiles should still
use `raycast` rather than lean on the solver.

### The engine

`physics.backend` names the engine, and `rapier` is the only one.
Bootstrap logs it with the substep count (`physics: rapier, 4 substeps`).
It covers bodies, circle and box colliders, materials, collision layers
and groups, sensors, collision events, forces and impulses, every query,
every joint type, one-way platforms and the native swept mover
(`sweep_box`, `step_bodies`).

A game that builds a physics world of its own -- a room's walls kept
apart from the main world, say -- should make it with
`pyguara.physics.create_physics_engine(config.physics)`, so it is
configured as the main one is.

Refused rather than ignored: segment and polygon colliders, and a
`max_force` on any joint but a motor, which Rapier can cap only on a
motor. Both raise `NotImplementedError`.

### Coming from pymunk

pymunk was the engine until 0.8. `physics.backend = "pymunk"`, in a config
file or as `PYGUARA_PHYSICS_BACKEND`, now stops the game at startup with
`RetiredBackendError`. `PymunkEngine` is gone; `RapierEngine` or
`create_physics_engine` replaces it. Chipmunk's two tunings,
`physics.penetration_recovery` and `physics.sleep_time_threshold`, are gone
with it, and a config file that still sets them loads with a warning naming
each key. The `pymunk` package is no longer a dependency: `Vector2` is the
engine's own, in the native extension.

What a game notices:

- **Collision events are reported after each solver step**, not during
  it. A pair whose `on_collision_begin` returns False is resolved for one
  solver step before it stops being; Chipmunk stopped at once.
- **A ray is a line**, where Chipmunk's had a radius of one pixel.
- **Results differ**: Rapier settles a stack differently, so a replay or a
  golden frame with rigid bodies in it changed with the switch.
- With a collision system attached, which every game started through
  `create_application` has, Rapier steps a pile of falling boxes in about a
  fifth of pymunk's time, and its swept mover keeps its speed with moving
  bodies in the world; see [performance](../guides/performance.md).

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

The engine reports a contact pair in its own order and tells
`CollisionSystem` which side owns the sensor; the trigger events always come
out with `trigger_entity` set to the sensor's entity and `other_entity` the
body that entered it, regardless of that order.

## Spatial queries

Collision *events* tell you what is touching what. To ask the world a
question directly — what did the player click, who is in the blast radius,
does this space fit — use the read-only queries on `IPhysicsEngine`
(`raycast`, `raycast_all`, `point_query`, `overlap_box`, `overlap_box_all`,
`overlap_circle`, `region_query`). They are documented on their own page:
[Spatial Queries](queries.md).

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
