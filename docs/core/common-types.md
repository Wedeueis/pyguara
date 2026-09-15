# Core Types

`pyguara.common` holds the primitives every other subsystem shares: `Vector2`,
`Color`, `Rect`, and the `Transform` component.

## Axis convention

**Y increases downwards.** This matches SDL, pygame, and the engine's own
defaults — `PhysicsConfig.gravity_y` is *positive* for a platformer.

Everything follows from that: "up" is negative Y.

```python
Vector2.up()     # (0, -1)
Vector2.down()   # (0,  1)
Vector2.left()   # (-1, 0)
Vector2.right()  # (1,  0)

Transform().up   # (0, -1), rotated by the transform's world rotation
```

## Vector2

An immutable 2D vector, subclassing `pymunk.Vec2d` for C-optimised math and to
pass straight into the physics backend. Every operation returns a new
`Vector2`; nothing mutates in place.

```python
v = Vector2(3, 4)
v.magnitude        # 5.0
v.sqr_magnitude    # 25.0 -- no square root, use it to compare distances
v.normalize()      # (0.6, 0.8); a zero vector normalises to zero, not an error
v.distance_to(other)
v.lerp(target, 0.5)
v.to_tuple(), v.to_int_tuple()
```

### Angles

Two rotation methods, named so the unit is unmissable:

```python
v.rotated(math.pi / 2)      # radians
v.rotate_degrees(90)        # degrees
```

!!! warning "`Vector2.rotate()` no longer exists"
    It took **degrees** and sat one letter away from `rotated()`, which takes
    **radians** — while `Transform.rotate()` also takes radians. A one-letter
    difference deciding the angle unit cannot be read correctly at a call
    site, so the ambiguous name was removed. Replace `v.rotate(deg)` with
    `v.rotate_degrees(deg)`.

Since `Vector2` is a tuple subclass, note that `Vector2(0, 0)` is **falsy**.
Use `if v is not None`, never `if v`, when a zero vector is a legitimate value.

## Color

An RGBA colour, one byte per channel, with no backend dependency. Channels are
coerced to `int` and **clamped to 0–255** on construction, so arithmetic that
overshoots saturates instead of handing a backend an unrepresentable value:

```python
Color(300, -5, 128)          # Color(255, 0, 128)
Color.from_hsv(0, 5, 5)      # Color(255, 0, 0), not garbage
Color(0, 0, 0).lerp(Color.WHITE, 0.5)
```

```python
Color.from_hex("#FF00AA")    # also "0xFF00AA" and "#FF00AAFF"
color.to_hex()               # "#FF00AA"; to_hex(include_alpha=True) adds the pair
color.normalized             # (r, g, b, a) as floats in 0.0-1.0, for shaders
color.to_hsv()               # (hue 0-360, saturation 0-1, value 0-1)
```

Named constants live on `Color` itself — `Color.WHITE`, `Color.BLACK`,
`Color.RED`, `Color.TRANSPARENT`, and so on. `pyguara.common.palette` re-exports
them as `BasicColors` and adds `DebugColors` for debug drawing; it holds no
independent definitions, so the two spellings cannot drift apart.

## Rect

An axis-aligned rectangle in integer pixel coordinates. Mutable, matching
`pygame.Rect`, because the UI layout engine assigns to `rect.x` in place.
Coordinates are truncated to `int` on construction, so building one straight
from `Vector2` components works without an explicit cast.

```python
r = Rect(10, 20, 30, 40)
r.left, r.top, r.right, r.bottom
r.centerx, r.centery, r.center_vec, r.position, r.size

r.contains_point(Vector2(15, 25))   # right/bottom edges exclusive
r.colliderect(other)                # touching edges do not overlap
r.contains(other)                   # edges inclusive
r.inflate(4, 4)                     # grows around the same centre
```

## Transform

Position, rotation and scale, with optional parenting. Angles are **radians**
everywhere except `rotation_degrees`.

`Transform` is a data-only component, so its behaviour is free functions
beside it in `pyguara.common.components` — the same split
`StatBlock`/`get_stat` and `Health`/`apply_damage` use. Properties
(`position`, `rotation`, every `world_*`) stay on the component.

```python
from pyguara.common.components import Transform, look_at, rotate, translate

t = Transform(position=Vector2(100, 50), rotation=math.pi / 2)
t.position, t.rotation, t.rotation_degrees, t.scale
translate(t, Vector2(5, 0))
rotate(t, math.pi)          # radians
look_at(t, Vector2(0, 0))   # points `forward` at a world position
```

### Hierarchy

A parented transform stores values *local* to its parent; the `world_*`
properties resolve the chain.

```python
set_parent(child, parent)                            # keeps world position
set_parent(child, parent, keep_world_transform=False)  # keeps local values
set_parent(child, None)                              # detach
```

World values are cached and rebuilt lazily: a setter marks the subtree dirty,
and the next `world_*` read recomputes only what it needs. This is transparent
— move a parent and every descendant's world position follows.

Cycles are rejected:

```python
set_parent(t, t)                     # ValueError
set_parent(a, b); set_parent(b, a)   # ValueError
```

A cycle has no world transform, so without this guard every later `world_*`
read recursed until the stack ran out. `is_ancestor_of(t, other)` exposes the
same check.

### Coordinate conversion

```python
local_to_world(t, Vector2(1, 0))
world_to_local(t, Vector2(110, 55))
distance_to(t, other_transform)      # world space
```

A zero world scale is not invertible; `world_to_local` returns the origin
rather than raising mid-frame.

### Why the behaviour is beside Transform, not in a system

`Transform` was the engine's largest exception to the data-only rule, holding
ten methods under `_allow_methods = True`. A `TransformSystem` was the obvious
destination and the wrong one: none of this is per-frame work over a query. It
is ten independent operations a caller invokes at a moment of its choosing, and
a system would have had to expose all ten as methods anyway. So they became
free functions, and the rule got a carve-out (`@pure_query`) for the
side-effect-free reads that genuinely read better as methods.

The lazy `world_*` cache stayed on the component. Its invalidation is driven by
the property setters, which are permitted, and splitting the cache from the
setters that dirty it would have made both harder to reason about.

## Rules of thumb

1. Y is down. "Up" is negative Y, in `Vector2` and `Transform` alike.
2. Never test a `Vector2` for truthiness — `Vector2(0, 0)` is falsy.
3. Radians everywhere, except `rotate_degrees()` and `rotation_degrees`.
4. Let `Color` clamp; do not pre-clamp channels at call sites.
5. Define colours once, on `Color`. `BasicColors` re-exports, never redefines.
