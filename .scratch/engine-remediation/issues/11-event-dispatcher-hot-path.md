# Event dispatcher hot path

Type: grilling
Status: resolved
Blocked by: —
Assignee: Wedeueis Braz
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

## Answer

**History becomes opt-in, backed by a `deque`.** No production or test code anywhere calls
`get_history()` — confirmed by grep, zero callers. Checked the two places a real production
consumer would plausibly live (the replay system, the editor) and neither touches it: `replay/`
records raw `InputFrame` input data directly, never `EventDispatcher`, and the editor has no
timeline/undo feature reading `_event_history`. Telemetry (wants live-subscribe-and-forward, and
a memory-only buffer is the worst shape for exactly the crash data it wants), event-sourced
replay/rollback (a different, heavier architecture this engine hasn't chosen — it already has
input-based replay), and editor undo/redo (events carry no inverse, couldn't back it) were all
considered and ruled out as production use cases. It's a debug/devex/test feature. `enable_history:
bool = False` constructor param, default off; storage becomes `deque(maxlen=self._max_history_size)`
regardless of the flag, so enabling it in a test or a devtool doesn't reintroduce the O(n)
`list.pop(0)` cost.

**`_global_listeners` is deleted, not wired up.** Zero current demand: no code wants "every
event." `EventMonitor` — the obvious "observe everything" consumer — already gets its curated
subset by subscribing to `OnRawKeyEvent`/`OnActionEvent`/`QuitEvent` individually, and works
fine that way. Speculatively building `subscribe_global()` now means guessing its shape with no
real caller; if a future devtool needs it, build it against that caller. Delete the field, Phase
B's `_process_handlers` call, and `clear_subscribers()`'s reference to it.

**Base-class dispatch: supported, via a per-dispatch MRO walk merged into one priority-sorted
list — no subscribe-time cache.** The `CollisionEvent`/`TriggerEvent` hierarchies are shallow
everywhere (2-3 levels: e.g. `OnCollisionBegin → CollisionEvent → Event`), so walking
`type(event).__mro__` and collecting `self._listeners.get(cls, [])` for each ancestor is a
handful of dict lookups — cheaper than a single handler callback, and far cheaper than the
history cost just fixed above. A subscribe-time cache (the `QueryCache` pattern from [ECS
lifecycle contract](06-ecs-lifecycle-contract.md)) would need invalidation-on-subscribe for a
performance benefit that doesn't exist at this depth — added complexity, no payoff. Collect
handlers from every MRO level into one list, sort by priority (existing `HandlerRecord.priority`,
higher first, same as today), and process it as a single pass — priority governs order
regardless of whether a handler subscribed to the exact type or a base class; a handler
returning `False` stops the whole pass at that point, not just its own type-level. This replaces
today's two-phase (specific, then global) `dispatch()` body with one phase.

**Nominal Protocol inheritance: dropped at all 14 sites, not just the 4 the audit named.**
Grepped every class inheriting from a `Protocol`-based interface (`class X(IFoo)` where `IFoo`
extends `Protocol`) and found 14, not 4: `EventDispatcher(IEventDispatcher)`,
`PymunkEngine`/`PymunkBodyAdapter`(physics), `PygameBackend`/`ModernGLRenderer`/
`HeadlessBackend`(IRenderer), `PygameWindow`/`PygameGLWindow`(IWindowBackend),
`JsonLoader`/`PrefabLoader`/`PygameSoundLoader`(IResourceLoader),
`PygameImageLoader`(IMetaAwareLoader), `GLTextureLoader`(IResourceLoader),
`PygameAudioSystem`(IAudioSystem). The defect: a Protocol's methods have a `...` body: a
concrete class that explicitly inherits the Protocol and forgets to override a required method
doesn't error — it silently runs the inherited stub and returns `None`, and mypy doesn't catch
it either, since inheritance already "satisfies" the interface. CLAUDE.md already states this
codebase's own principle — Protocol (structural) over ABC (nominal) "to avoid tight coupling" —
and `class Foo(IFoo)` is nominal subtyping wearing a Protocol's clothes, getting none of
structural typing's safety while adding the stub-swallowing hazard on top. Decision: drop the
explicit `(IFoo)` base at all 14 sites. `@runtime_checkable` Protocols support `isinstance()`
and structural type-checking without inheritance, so nothing observable changes except that a
genuinely missing method now surfaces — as a mypy structural-mismatch error wherever the class
is used as the protocol type (DI registration, function parameter, factory return type), or an
`AttributeError` at the call site — instead of silently no-opping. Decided here rather than
folded into each ticket that already touches these files, since it's one mechanical policy
applied uniformly; lands as its own execution ticket.

**Default `ErrorHandlingStrategy` stays `RAISE`.** This is an engine-library default, not a
per-game one: `RAISE` is correct fail-fast behavior while a game developer is building against
the engine — a silently swallowed handler exception is exactly the bug class you want surfaced
immediately, not discovered as "my collision sound never plays." Whether a game's *shipped*
build should swallow-and-log is each game's own bootstrap decision
(`error_strategy=ErrorHandlingStrategy.LOG`), not the engine's to make for them. The "`LOG` would
currently log nowhere in production" half of the audit's concern is already fixed structurally by
[Logging migration](08-logging-migration.md)'s decision that `EventDispatcher._logger` defaults
via the shared `get_logger()` accessor instead of `None` — not re-litigated here, just confirmed
it now makes either default viable.

Execution: [Execute the event dispatcher hot-path fixes](22-execute-event-dispatcher-hot-path.md),
[Drop nominal Protocol inheritance across the 14 sites](23-drop-nominal-protocol-inheritance.md).
