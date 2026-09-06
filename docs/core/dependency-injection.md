# Dependency Injection

`pyguara.di` is a reflection-based container. Services are registered against
an interface type and constructed by reading their constructor's type hints —
no attributes, no registration DSL.

```python
container = DIContainer()
container.register_singleton(IPhysicsEngine, PymunkEngine)
container.register_transient(IProjectile, Bullet)

engine = container.get(IPhysicsEngine)
```

Anything the constructor annotates is resolved recursively:

```python
class PhysicsSystem:
    def __init__(self, engine: IPhysicsEngine, dispatcher: EventDispatcher) -> None:
        ...

container.get(PhysicsSystem)   # both arguments injected
```

## Lifetimes

| Lifetime | Instances | Use for |
| --- | --- | --- |
| `SINGLETON` | One per container | Engine services: renderer, physics, audio |
| `SCOPED` | One per `DIScope` | Per-scene or per-request resources |
| `TRANSIENT` | One per request | Stateless helpers, short-lived objects |

```python
container.register_singleton(IRenderer, PygameBackend)
container.register_scoped(ILevelCache, LevelCache)
container.register_transient(IPathfinder, AStarPathfinder)
container.register_instance(IConfig, loaded_config)   # pre-built object
```

`register_instance()` validates the object against the interface when that
interface is a `@runtime_checkable` Protocol — the only registration that can
check anything up front, since the others have a class and no instance yet.

Re-registering a type replaces it, **including any singleton already handed
out**. A later `get()` returns the new implementation.

### Lifetimes must not be captured downwards

A singleton may depend on singletons and transients. It may **not** depend on
a scoped service:

```python
container.register_scoped(ILevelCache, LevelCache)
container.register_singleton(IWorld, World)   # World(cache: ILevelCache)

with container.create_scope() as scope:
    scope.get(IWorld)     # DIException
```

This is the captive-dependency problem. The singleton outlives the scope, so
it would keep holding a `LevelCache` the scope had already disposed. Singletons
are therefore always constructed **without** a scope, and the attempt fails
loudly rather than producing an object that silently rots.

The safe directions:

| Consumer | May depend on |
| --- | --- |
| Singleton | Singleton, Transient |
| Scoped | Singleton, Scoped, Transient |
| Transient | Singleton, Scoped, Transient |

## Scopes

A scope owns one instance of each scoped service and disposes them when it
closes. Always use it as a context manager:

```python
with container.create_scope() as scope:
    cache = scope.get(ILevelCache)
    assert scope.get(ILevelCache) is cache
# scope disposed
```

On disposal, each scoped instance is torn down newest-first via `dispose()`,
or `close()` if it has no `dispose()`. A teardown that raises is **logged and
skipped**, so one broken object cannot strand the rest.

A disposed scope refuses to resolve — anything created afterwards would never
be cleaned up:

```python
scope.dispose()
scope.get(ILevelCache)     # DIException
```

## Optional dependencies

`Optional[X]` and `X | None` resolve to `X`. A wider union takes its first
non-`None` member.

A dependency that is not registered raises `ServiceNotFoundException` — unless
the parameter declares a default, in which case it is skipped and Python
supplies the default:

```python
class Renderer:
    def __init__(self, profiler: IProfiler | None = None) -> None:
        ...   # profiler is None when IProfiler was never registered
```

`*args` and `**kwargs` are never injection points and are skipped entirely.

## Cycle detection

A dependency cycle raises `CircularDependencyException` naming the chain:

```
Circular dependency detected: ServiceA -> ServiceB -> ServiceA
```

Detection state is **thread-local**, so a resolution on one thread never sees
another's partial chain.

## Threading

Registration and resolution are guarded by a reentrant lock, so a singleton is
constructed at most once even under contention, and resolving through a
`DIScope` takes the same lock as resolving through the container.

The lock is held for the whole resolution, constructors included, so a slow
constructor blocks other threads for its duration. Build the container during
bootstrap rather than resolving on hot paths from several threads.

## Decorators

Classes may carry their own registration metadata:

```python
@singleton(IPhysicsEngine)
class PymunkEngine: ...

@scoped(ILevelCache)
class LevelCache: ...

auto_register(container, PymunkEngine, LevelCache)
```

## Error strategy

Controls what happens when the container cannot read a constructor's hints —
an unresolvable forward reference, say:

| Strategy | Behaviour |
| --- | --- |
| `RAISE` *(default)* | Log, then raise `DIException`. Fail fast. |
| `LOG` | Log and register with no dependencies. |
| `IGNORE` | Register with no dependencies, silently. |

## Rules of thumb

1. Register everything during bootstrap; resolve, don't re-register, later.
2. Singletons never depend on scoped services. Push shared state up, or make
   the consumer scoped too.
3. Scopes belong in `with` blocks.
4. Annotate constructors. An unannotated parameter is invisible to injection.
5. Give a parameter a default when the dependency is genuinely optional; that
   is the only thing that makes a missing registration non-fatal.
