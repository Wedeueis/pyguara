# Physics System

PyGuara simulates physics with **Rapier**, in the native extension, behind
the `IPhysicsEngine` protocol. **Pymunk** (Chipmunk2D), the engine before
it, can still be chosen; see [Two engines](#two-engines).

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

Neither engine runs continuous collision detection: in one solver step a
body moves `velocity × dt` in a straight line and passes through anything
thinner than that jump. `physics.substeps` (default **4**) splits each tick
into that many solver steps to shorten the jump. Measured on Chipmunk
against a 10px wall, 1/2/4 substeps stop a body up to roughly
200/400/900 px/s. Four is cheap
(~0.65 ms/update at 200 dynamic bodies) and the headroom matters for
knockback and explosion-flung props; drop it to 2 only when simulating many
hundreds of fast bodies, and let fast projectiles use `raycast` rather than
leaning on the solver to catch them.

### Body sleeping (pymunk)

Rapier sleeps bodies by its own rule; this setting is Chipmunk's.

`physics.sleep_time_threshold` (default **0.5 s**) is how long a body must
hold still before Chipmunk lets it *sleep* — drop out of the solver until
something disturbs it. Without it (Chipmunk's own default) a room full of
settled props and debris is simulated forever. A body wakes automatically the
moment anything writes its state: a `position`, `rotation` or `velocity`
assignment, an `apply_force` / `apply_impulse`, or a fresh collision. Set the
threshold to `0` to disable sleeping entirely.

Two consequences worth knowing:

- A body resting on a **kinematic** platform never sleeps — a kinematic body
  is never idle — so a moving-platform ride keeps its rider awake.
- Reading a sleeping body's position is fine and cheap; it still appears in
  every [spatial query](queries.md).

### Two engines

`physics.backend` chooses the engine: `rapier`, the default, a Rapier
world in the native extension, or `pymunk`, which was the default before
it. `PYGUARA_PHYSICS_BACKEND` overrides it, and bootstrap logs the one in
use (`physics: rapier, 4 substeps`). Rapier covers bodies, circle and box
colliders, materials, collision layers and groups, sensors, collision
events, forces and impulses, every query, every joint type, one-way
platforms and the native swept mover (`sweep_box`, `step_bodies`), all
held to the same tests as pymunk
(`tests/test_physics_rapier.py`, `tests/test_physics_rapier_joints.py`,
`tests/test_physics_rapier_sweep.py`, and `tests/test_joint_system.py`
and the platformer feel suite, which run on both).

A game that builds a physics world of its own -- a room's walls kept
apart from the main world, say -- should make it with
`pyguara.physics.create_physics_engine(config.physics)` rather than
naming an engine class, so that world follows `physics.backend` too.

Refused rather than ignored: segment and polygon colliders, which pymunk
refuses too, and a `max_force` on any joint but a motor, which Rapier can
cap only on a motor. Both raise `NotImplementedError`.

Where the two differ on purpose or for now:

- **Collision events are reported after each solver step**, not during
  it. A pair whose `on_collision_begin` returns False is resolved for one
  solver step before it stops being; pymunk stops at once.
- **A ray is a line**, where pymunk's has a radius of one pixel.
- **Results differ**: Rapier settles a stack differently, so a replay or a
  golden frame with rigid bodies in it changes when a game switches.
- `penetration_recovery` and `sleep_time_threshold` are Chipmunk's tuning
  and do not apply.

With a collision system attached, which every game started through
`create_application` has, Rapier steps a pile of falling boxes in about a
fifth of pymunk's time. Its swept mover keeps its speed with moving
bodies in the world, where pymunk's static mirror gives way to Chipmunk;
see [performance](../guides/performance.md).

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
