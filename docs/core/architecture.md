# Core Architecture

PyGuara's core is three cooperating pieces: an ECS that stores game state, a
DI container that wires services, and an event system that decouples them.

---

# Entity Component System (ECS)

Entities are ids, components are data, systems are logic. The `EntityManager`
holds an inverted index (`ComponentType -> {EntityID}`) so a query costs work
proportional to the number of *matching* entities, not to the size of the
world.

```python
for entity in manager.get_entities_with(Transform, RigidBody):
    ...
```

Three details are load-bearing and easy to get wrong:

- **Data-only components.** `StrictComponent` rejects logic methods at class
  definition; `BaseComponent` only warns.
- **Terminal removal.** `remove_entity()` is immediate and irreversible;
  index cleanup is deferred to `flush_pending_removals()` at the frame
  boundary, which is what makes queries safe to iterate mid-destruction.
- **Cached queries.** `register_cached_query()` materialises a hot-loop
  query's result set; it is maintained incrementally, not recomputed.

See **[Entity Component System](ecs.md)** for the full reference.

---

# Dependency Injection (DI)

PyGuara features a native, reflection-based Dependency Injection container (`pyguara.di`).

## Features

- **Auto-Wiring**: Uses Python type hints (`typing.get_type_hints`) and `inspect` to automatically resolve constructor dependencies.
- **Cycle Detection**: Detects and reports circular dependencies at runtime.
- **Scopes**:
    - `SINGLETON`: Shared across the entire application.
    - `TRANSIENT`: Created new every time requested.
    - `SCOPED`: Shared within a specific context (e.g., a Scene).

## Usage

```python
container = DIContainer()
container.register_singleton(IPhysicsEngine, PymunkEngine)

# Application is auto-wired with IPhysicsEngine
app = container.get(Application)
```

---

# Event System

The Event System (`pyguara.events`) provides a decoupled communication channel between subsystems.

## EventDispatcher

- **Synchronous Dispatch**: `dispatch(event)` executes handlers immediately on the calling thread.
- **Queued Dispatch**: `queue_event(event)` is thread-safe and processes events at the start of the next frame (useful for Network/Loader threads).
- **Filtering & Priority**: Handlers can define priority levels and filter logic.

## Protocol

Events are defined using the `Event` protocol, typically implemented as Dataclasses.

```python
@dataclass
class PlayerDiedEvent:
    player_id: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None
```
