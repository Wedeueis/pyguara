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

The event system (`pyguara.events`) decouples subsystems: publishers do not
know their subscribers, and subscription is by event type.

- **Structural events.** `Event` is a Protocol, so any dataclass with
  `timestamp` and `source` qualifies — no base class required.
- **Subclass matching.** Dispatch walks the event's MRO, so subscribing to
  `KeyboardEvent` receives both `KeyDownEvent` and `KeyUpEvent`. Handlers
  across the hierarchy merge into one priority-ordered pass.
- **Consumption.** A handler returning `False` stops lower-priority handlers,
  and `dispatch()` reports it — how a UI layer claims input before the game.
- **Threading.** `queue_event()` is the only thread-safe entry point;
  `process_queue()` drains on the main loop, under optional time and count
  budgets.

```python
@dataclass
class PlayerDied:
    player_id: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None
```

See **[Event System](events.md)** for the full reference.
