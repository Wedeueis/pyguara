# Entity Component System (ECS)

PyGuara's ECS is built for worlds of thousands of entities. It has three parts:

| Concept | Role |
| --- | --- |
| **Entity** | A unique id plus the components attached to it. No logic. |
| **Component** | Plain data. No logic. |
| **EntityManager** | The world: registration, lifecycle, and queries. |
| **System** | All the logic. Reads components, writes components. |

## Components

Components inherit from `StrictComponent` (preferred) or `BaseComponent`, and
are almost always dataclasses.

```python
from dataclasses import dataclass
from pyguara.ecs import StrictComponent

@dataclass(slots=True)
class Health(StrictComponent):
    current: float = 100.0
    maximum: float = 100.0
```

### Data-only enforcement

Both base classes inspect subclasses at class-definition time and reject logic:

- `StrictComponent` raises `TypeError`.
- `BaseComponent` emits a `UserWarning`, and accepts `_allow_methods = True`
  as an escape hatch for legacy components.

Permitted on a component: lifecycle hooks (`__init__`, `__post_init__`,
`on_attach`, `on_detach`), dunder methods, `@property` accessors, and
underscore-prefixed private helpers. Anything else belongs in a System.

```python
@dataclass(slots=True)
class Velocity(StrictComponent):
    dx: float = 0.0
    dy: float = 0.0

    def apply(self, dt: float) -> None:   # TypeError at import time
        ...
```

Use `@dataclass(slots=True)`. `BaseComponent` declares `__slots__`, and a
subclass without slots reintroduces a per-instance `__dict__`, which is the
dominant memory cost once entity counts get large.

## Entities

An entity is a container. Attach and read components by type:

```python
entity = manager.create_entity()
entity.add_component(Transform(position=Vector2(100, 100)))
entity.add_component(Health(current=50))

transform = entity.get_component(Transform)   # fastest, type-safe
transform = entity.transform                  # attribute access, cached
```

Attribute access resolves the component's class name in snake_case
(`RigidBody` -> `entity.rigid_body`). The mapping is memoised per component
type, so no string work happens in an update loop.

`entity.tags` is a plain `set[str]` for categorisation that does not warrant a
component.

### Copying entities

`Entity` rejects `copy.copy()`, `copy.deepcopy()` and `pickle`: all three would
alias the original's manager callbacks and its physics and audio handles. Use
`clone()`, then register the result:

```python
copy_of = original.clone()
manager.add_entity(copy_of)          # required -- clone() does not register
```

`clone()` deep-copies each component but resets fields whose name starts with
`_` to their dataclass default. Those are system-injected handles (for example
`RigidBody._body_handle`); a clone has not been registered with any backend
yet, so it must not inherit a live one.

For save and load, use `SceneSerializer` rather than pickling entities.

## Querying

The manager keeps an inverted index, `ComponentType -> {EntityID}`. A query
intersects the index sets for the requested types, smallest first, so cost
scales with the number of *matching* entities rather than the size of the
world.

```python
for entity in manager.get_entities_with(Transform, RigidBody):
    ...
```

### Fast-path tuple queries

When a system needs only the components, skip the entity wrapper:

```python
for transform, body in manager.get_components(Transform, RigidBody):
    transform.position += body.velocity * dt
```

`get_components()` is typed through overloads for two to four component types.
Use `get_components_with_entity()` when the loop body also needs the entity —
its id, its tags, or to attach and detach components.

### Cached queries

A query that runs every frame can keep its result set materialised, so the
per-frame read skips the intersection entirely. Register it once, during system
initialisation:

```python
class PhysicsSystem:
    def __init__(self, entity_manager: EntityManager) -> None:
        entity_manager.register_cached_query(Transform, RigidBody)

    def fixed_update(self, dt: float) -> None:
        for entity in self.entity_manager.get_entities_with_cached(
            Transform, RigidBody
        ):
            ...
```

Rules:

- A query is identified by the *set* of its types; argument order is irrelevant.
- `register_cached_query()` backfills from the current world, so registering
  after entities already exist is fine.
- `get_entities_with_cached()` falls back to a full intersection only when the
  combination was never registered. A registered query that currently matches
  nothing correctly yields nothing.
- Register hot-loop queries only. Each registered query adds bookkeeping to
  every component add and remove that touches one of its types.

## Entity lifecycle

Registration and destruction both have rules that systems depend on.

### Registration

```python
entity = manager.create_entity()        # created and registered
manager.add_entity(prebuilt_entity)     # register one built elsewhere
```

`add_entity()` indexes components that were attached *before* registration —
the normal case for clones, prefabs and deserialised scenes — through the same
path as later additions, so cached queries see them too.

### Destruction is two-phase, and terminal

```python
manager.remove_entity(entity.id)   # soft-dead, immediately
...
manager.flush_pending_removals()   # index cleanup, at the frame boundary
```

`remove_entity()` takes effect at once: the entity leaves the registry, its
manager callbacks detach, and it is marked dead. From that instant
`get_entity()` returns `None` and every query skips it.

What is *deferred* is the physical index cleanup. Leaving index sets untouched
for the rest of the frame is what makes every query safe to iterate while other
systems destroy entities mid-loop. `SceneManager` calls
`flush_pending_removals()` at the frame boundary; call it yourself only if you
drive the manager outside a scene.

Removal is terminal. A removed entity cannot be mutated or re-registered:

```python
manager.remove_entity(e.id)
e.add_component(Health())   # RuntimeError
manager.add_entity(e)       # RuntimeError
```

Use `clone()` to produce a fresh, registerable entity instead. The alternative —
allowing resurrection — yields an entity reachable by id but invisible to every
query after the next flush, which is far harder to debug than an exception.

### Reacting to destruction

`EntityManager` knows nothing about the event system. Instead it lets consumers
subscribe directly, and `Scene` uses that to republish removals as
`EntityDestroyed` events:

```python
manager.subscribe_entity_removed(callback)     # callback(entity) -> None
manager.unsubscribe_entity_removed(callback)
```

Subscribers fire synchronously from `remove_entity()`, at the moment of
soft-death and before index cleanup, so they still see the entity's components:

```python
def on_removed(entity: Entity) -> None:
    health = entity.get_component(Health)   # still readable
```

Semantics worth knowing:

- **Every subscriber is notified.** Order follows subscription order.
- **Subscribing the same callback twice notifies once**, so a scene whose
  dependencies are resolved twice does not double-dispatch.
- **Exceptions propagate** to whoever called `remove_entity()`. Removal itself
  has already completed by then, so the world is never left half-removed, but a
  subscriber that can fail should handle its own errors.
- **A subscriber may unsubscribe during notification** — useful for one-shot
  listeners and teardown.

Most game code should not subscribe here at all: prefer the `EntityDestroyed`
event that `Scene` already publishes.

```python
from pyguara.ecs.events import EntityDestroyed

def on_destroyed(event: EntityDestroyed) -> None:
    health = event.entity.get_component(Health)   # still readable
```

Reserve `subscribe_entity_removed()` for engine-level observers that must run
before, or independently of, event dispatch — an editor inspector clearing its
selection, or a backend releasing a handle.

## Rules of thumb

1. Components hold data. Systems hold logic. `StrictComponent` enforces it.
2. Query by type, never by scanning `get_all_entities()`.
3. Register a cached query only for something that runs every frame.
4. Never touch `entity._components` or `manager._component_index` directly —
   that bypasses index maintenance and silently corrupts queries. Observe
   removals with `subscribe_entity_removed()`, not by assigning a private hook.
5. Removal is terminal; clone rather than resurrect.
