# Spatial Queries

Every question a game asks the physics world that is *not* "step the
simulation" is a spatial query: what did the player click, which enemies are
in the blast radius, does this doorway fit the crate, what does the laser
pass through. They are read-only — nothing moves — and they run against the
same broadphase the solver uses, so they are cheap.

All of them live on `IPhysicsEngine`, which `bootstrap.py` registers as a
singleton; resolve it from the DI container (`container.get(IPhysicsEngine)`)
or take it in a system constructor.

## The queries

| Method | Shape asked | Returns | Reach for it when |
| --- | --- | --- | --- |
| `raycast(start, end, ...)` | a line segment | nearest `RaycastHit` or `None` | line of sight, ground probe, a single hitscan shot |
| `raycast_all(start, end, ...)` | a line segment | `list[RaycastHit]`, near→far | a piercing shot or laser that passes through several targets |
| `point_query(point, ...)` | one point | `list[entity id]`, most-enclosed first | click-picking — "what is under the cursor?" |
| `overlap_box(centre, half_extents, ...)` | an axis-aligned box | first `entity id` or `None` | a mover's per-step "is this space blocked, and by what?" |
| `overlap_box_all(centre, half_extents, ...)` | an axis-aligned box | `list[entity id]` | a box-shaped melee swing, a marquee selection |
| `overlap_circle(centre, radius, ...)` | a circle | `list[entity id]` | explosion radius, aggro range, a radial melee arc |
| `region_query(bounds, ...)` | a `Rect`'s bounding box | `list[entity id]` | a fast first cut of a large world before a precise test |

Common parameters, on every query:

- **`mask`** — a collision bitmask. A shape whose category is outside the
  mask is ignored, exactly as for `raycast`. Defaults to "hit everything".
- **`ignore_entity_id`** — one entity to leave out of the results, normally
  the querier itself (a character probing for ground would otherwise find its
  own collider).

Shared behaviour:

- **Sensors are never returned.** A sensor (`Collider(is_sensor=True)`,
  or a `TriggerVolume`) is meant to be passed through; use the trigger
  events for those.
- **An entity is reported once**, even if it carries several colliders.
- The list queries return `[]` when nothing matches; `raycast` /
  `overlap_box` return `None`.

## Precise vs. broad-phase

`region_query` is the odd one out: it tests **bounding boxes, not shapes**. A
circle or a rotated polygon whose bounding box pokes into the rectangle is
reported even though the shape itself does not touch it. That is the point —
it is the cheapest possible "roughly what is around here", meant to narrow a
big world down to a handful of candidates that you then confirm with
`overlap_circle`, `overlap_box_all`, or your own maths. Every other query on
this page tests the real shape.

## Examples

```python
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.common.types import Rect, Vector2

engine = container.get(IPhysicsEngine)

# Click-picking: topmost entity under the mouse in world space.
picked = engine.point_query(world_mouse)
if picked:
    select(picked[0])

# Explosion: everything within 120px, minus the bomb itself.
for entity_id in engine.overlap_circle(blast_centre, 120.0, ignore_entity_id=bomb.id):
    apply_damage(entity_id, falloff(blast_centre, entity_id))

# Piercing shot: hit every body along the line, nearest first.
for hit in engine.raycast_all(muzzle, muzzle + aim * 800):
    damage(hit.entity_id)
    if not pierces(hit.entity_id):
        break

# "Can the crate fit through here?" — a solid in the doorway means no.
blocked = engine.overlap_box(doorway_centre, Vector2(16, 24), ignore_entity_id=crate.id)
```

## Determinism

The queries read the world; they do not advance it, and they take no random
input, so they are safe to call from anywhere in a frame and do not affect
deterministic replay. `raycast` / `raycast_all` use a 1px-radius swept circle
(Chipmunk has no zero-width ray), so a hit can register a pixel early against
a shape the mathematical line would just miss.
