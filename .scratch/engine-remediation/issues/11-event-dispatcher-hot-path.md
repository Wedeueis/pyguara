# Event dispatcher hot path

Type: grilling
Status: open
Blocked by: —
Audit ref: coherence

## Question

Three issues in `events/dispatcher.py` that compound in exactly the games this engine targets.

**Unconditional history.** `_record_history()` runs on every dispatch with no way to disable
it, and uses `list.pop(0)` — O(n) on a 1,000-element list — once the buffer fills. A bullet-hell
demo dispatching thousands of collision events per second pays this every time.

**Dead global listeners.** `_global_listeners` is iterated on every dispatch but has no
`subscribe` path. Nothing can ever be in it.

**Exact-type dispatch.** Dispatch matches `type(event)` exactly, so the `CollisionEvent` and
`TriggerEvent` base classes in `physics/events.py` can never receive anything. Subscribing to
a base class looks correct and silently receives nothing.

## To resolve

- Is history a debug feature? If so it belongs behind a flag, defaulted off in release, and a
  `deque(maxlen=...)` regardless.
- Does base-class subscription get supported? It is the natural reading of the `physics/events.py`
  hierarchy and the thing a user will try first. Cost is walking the MRO per dispatch or
  precomputing a type→handlers map at subscribe time.
- Do global listeners get a `subscribe_global()` or get deleted? The `EventMonitor` tool would
  be the obvious consumer.
- `EventDispatcher` inherits `IEventDispatcher` nominally, so a missing method would silently
  return `None` rather than raise. Same pattern as `PymunkEngine(IPhysicsEngine)` and
  `HeadlessBackend(IRenderer)`. Is nominal protocol inheritance a policy the engine keeps or
  drops? Whatever is decided here should apply to all four sites.
- Default `ErrorHandlingStrategy` is `RAISE`, so any handler exception kills the game loop —
  and bootstrap supplies no logger, so `LOG` would log nothing. What is the shipped default?

## Why this is unblocked

The audit is sufficient input for the discussion. Implementing the answer wants a booting
engine (Repair the composition root, Bootstrap smoke test), but deciding it does not — so this
sits on the frontier and can run in parallel with the critical fixes.
