# Entity Component System (ECS)

PyGuara uses a performance-optimized ECS implementation designed to handle thousands of entities with minimal overhead.

## Architecture

The ECS is built around three main concepts:

1.  **Entity**: A unique ID acting as a container.
2.  **Component**: Pure data classes attached to entities.
3.  **EntityManager**: The database managing queries and lifecycles.

### EntityManager

The `EntityManager` (`pyguara.ecs.manager`) is the heart of the system. It employs an **Inverted Index** strategy for $O(1)$ component lookups, avoiding the common performance pitfall of iterating through all entities.

**Key Features:**
- **Inverted Indexing**: Maps `ComponentType -> Set[EntityID]`.
- **Set Intersection Queries**: Queries like "Get all entities with `Transform` AND `RigidBody`" are solved via fast set intersection.

```python
# O(K) complexity where K is the number of matching entities
for entity in manager.get_entities_with(Transform, RigidBody):
    ...
```

### Entity

The `Entity` class (`pyguara.ecs.entity`) is a lightweight container.

- **Dynamic Attribute Access**: Components are cached, allowing pythonic access (e.g., `entity.rigid_body`) via `__getattr__` optimization.
- **Tagging**: Supports string-based tags for non-component filtering.

### Component

Components (`pyguara.ecs.component`) are defined as `dataclasses` or standard classes inheriting from `BaseComponent`.

```python
@dataclass
class Health(BaseComponent):
    current: float = 100.0
    max: float = 100.0
```

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
