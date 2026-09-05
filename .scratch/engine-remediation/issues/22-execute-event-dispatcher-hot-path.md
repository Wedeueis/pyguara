# Execute the event dispatcher hot-path fixes

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: coherence, follows from Event dispatcher hot path, ticket 11

## Question

Nothing to decide — execute the decisions recorded in
[Event dispatcher hot path](11-event-dispatcher-hot-path.md).

**`pyguara/events/dispatcher.py`:**
- Add `enable_history: bool = False` to `EventDispatcher.__init__()`. Change
  `self._event_history: List[Event] = []` to `self._event_history: Deque[Event] =
  deque(maxlen=self._max_history_size)` (set `self._max_history_size` before constructing the
  deque). `_record_history()` becomes a no-op (or isn't called at all from `dispatch()`) when
  `enable_history` is `False`; when `True`, it's just `self._event_history.append(event)` — the
  `maxlen` deque handles eviction, drop the manual `len(...) > ...: pop(0)` check entirely.
- Delete `self._global_listeners` and its `List[HandlerRecord]` type import if now unused.
  Delete the "Phase B: Global Listeners" block in `dispatch()`. Delete the
  `self._global_listeners.clear()` line in `clear_subscribers()`.
- Rewrite `dispatch()`: replace the two-phase (specific, then global) body with a single pass —
  walk `type(event).__mro__`, collect `self._listeners.get(cls, [])` for each ancestor class
  into one list, sort the merged list by `record.priority` (descending, matching `subscribe()`'s
  existing sort direction), then call `self._process_handlers()` once on the merged, sorted
  list. `_record_history(event)` still runs first, unconditionally gated by `enable_history`.
- Confirm `get_history()`'s `isinstance(e, event_type)` filtering still works unchanged against
  the deque (convert to `list(...)` for the return type, as it already does).

**Tests (`tests/test_events.py`):**
- Update any test relying on `_event_history`/`get_history()` default-on behavior to pass
  `enable_history=True` explicitly.
- Add a regression test: subscribe a handler to `CollisionEvent` (or another base class),
  dispatch an `OnCollisionBegin` instance, assert the base-class handler fires.
- Add a regression test: subscribe handlers to both a base class and its concrete leaf with
  different priorities, dispatch a leaf-type event, assert call order follows priority (not
  which level each handler subscribed to).
- Add a regression test: a handler returning `False` at a lower-priority level after a
  higher-priority base-class handler still stops a same-pass handler at an even lower priority
  (proves the merged single-pass short-circuit, not per-type-level).
- Delete or update any test asserting `_global_listeners`/global-subscription behavior existed.
- Confirm no test still relies on the removed two-phase (specific-then-global) `dispatch()`
  structure.

**`tests/test_collision_events.py`:** no expected changes — all subscriptions there are already
concrete-leaf, and should keep passing unchanged; run to confirm.

## Done when

- `EventDispatcher()` (no args) no longer records history; `EventDispatcher(enable_history=True)`
  does, backed by a `deque(maxlen=1000)`.
- `_global_listeners` and the Phase B dispatch pass are gone from the codebase.
- A handler subscribed to `CollisionEvent` fires when an `OnCollisionBegin` is dispatched, proven
  by a regression test.
- Handler call order across mixed base/leaf subscriptions follows priority alone, proven by a
  regression test.
- Full suite green, `ruff check .` and `mypy pyguara` clean.

## Resolution

Executed exactly as specified, no surprises or scope adjustments. Commit `1b4c796`.

`enable_history: bool = False` added, backed by `deque(maxlen=1000)` regardless of the
flag; confirmed zero current callers of `get_history()` before touching it. `_global_listeners`
and the Phase B dispatch block deleted outright. `dispatch()` rewritten to walk
`type(event).__mro__`, merge listeners from every ancestor class into one priority-sorted
list, and process it in a single pass — base-class subscription now actually receives
dispatched subclass instances, and priority governs order/short-circuit across mixed
base/leaf subscribers regardless of which level they subscribed at.

Five new regression tests added to `tests/test_events.py`: history off by default and on
when requested (with `get_history()` covering both no-filter and type-filtered calls);
a `CollisionEvent` subscriber firing on an `OnCollisionBegin` dispatch; priority ordering
across a base-class and two leaf-type subscribers; and a base-class handler's `False`
return short-circuiting a lower-priority leaf-type handler in the same merged pass.
`tests/test_collision_events.py` needed no changes — ran it to confirm, all its
subscriptions were already concrete-leaf.

Full suite green (1059 passed), `ruff check .` and `mypy pyguara` clean.
