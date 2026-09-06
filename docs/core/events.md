# Event System

`pyguara.events` is the decoupled communication channel between subsystems.
Publishers do not know their subscribers, and subscription is by event type.

## Defining an event

An event is any object with `timestamp` and `source`. `Event` is a
**Protocol**, not a required base class, so a plain dataclass qualifies:

```python
from dataclasses import dataclass, field
import time
from typing import Any

@dataclass
class PlayerDied:
    player_id: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None
```

!!! warning "Use `field(default_factory=time.time)`"
    Not `timestamp: float = 0.0` with a `__post_init__` that overwrites zero.
    That sentinel pattern makes a genuine timestamp of `0.0` impossible to
    express — passing it silently yields the current time instead.

## Subscribing

```python
dispatcher.subscribe(PlayerDied, on_player_died)
dispatcher.subscribe(PlayerDied, on_player_died, priority=100)
dispatcher.subscribe(PlayerDied, on_boss_died, filter_func=lambda e: e.is_boss)
dispatcher.unsubscribe(PlayerDied, on_player_died)
```

- **Higher priority runs first.** Ties keep subscription order.
- **`filter_func`** gates the handler. It is user code, and its exceptions
  follow the same error strategy as a handler's.
- **`unsubscribe` removes every registration** of that callable for the type,
  and must name the same class used to subscribe — not a subclass.
- **The same callable may be subscribed more than once**, at different
  priorities or with different filters. Each registration runs.

### Subscribing to a base class

Dispatch walks the event's MRO, so a handler on a base class receives every
subclass:

```python
dispatcher.subscribe(KeyboardEvent, on_key)   # KeyDownEvent and KeyUpEvent
dispatcher.subscribe(object, log_everything)  # every event, a catch-all
```

Handlers from the whole hierarchy merge into **one** priority-ordered pass, so
priority decides call order whether a handler subscribed to the exact type or
to a base. Ties break in MRO order, subclass handlers first.

## Dispatching

```python
delivered = dispatcher.dispatch(PlayerDied(player_id="p1"))
```

`dispatch()` returns **`True`** if every applicable handler ran, and **`False`**
if one consumed the event by returning `False`, stopping lower-priority
handlers. That is how a UI layer claims an input event before the game sees it:

```python
def on_click(event) -> bool | None:
    if not self.rect.contains_point(event.position):
        return None          # not mine; let it through
    self.activate()
    return False             # consumed
```

The handler list is **snapshotted** before the pass begins. A handler that
subscribes or unsubscribes affects the *next* dispatch, not the one in flight.

## Threading

Only `queue_event()` is thread-safe. `dispatch()`, `subscribe()`,
`unsubscribe()` and `clear_subscribers()` must run on the main thread.

Background work — resource loaders, network callbacks — queues, and the main
loop drains:

```python
dispatcher.queue_event(TextureLoaded(path=path))   # any thread

dispatcher.process_queue()                          # main loop, once per frame
dispatcher.process_queue(max_events=100)            # count budget
dispatcher.process_queue(max_time_ms=2.0)           # time budget
```

`process_queue()` only considers events already queued when the call began.
Anything a handler queues waits for the next frame, as does anything left over
when a budget runs out — that is what stops a self-feeding event storm from
locking up a frame. It logs a warning past `queue_warning_threshold` (10 000 by
default) as an early signal of exactly that spiral.

## Error strategy

Handler and filter exceptions are governed by one policy, chosen at
construction:

| Strategy | Behaviour |
| --- | --- |
| `RAISE` *(default)* | Log, then re-raise. Fail fast in development. |
| `LOG` | Log and continue with the next handler. Graceful in production. |
| `IGNORE` | Swallow silently. Tests and narrow edge cases only. |

```python
EventDispatcher(error_strategy=ErrorHandlingStrategy.LOG)
```

## History

A debug and test aid, off by default so the dispatch path never pays for it:

```python
dispatcher = EventDispatcher(enable_history=True, max_history_size=500)
dispatcher.get_history()             # everything retained, oldest first
dispatcher.get_history(PlayerDied)   # that type and its subclasses
```

Backed by a bounded deque, so enabling it cannot grow without bound.

## Performance

`dispatch()` memoises the resolved handler list per concrete event type, so a
dispatch is a lookup plus a walk rather than an MRO scan and a re-sort every
time. The cache is dropped whenever the subscription set changes, which is why
`subscribe`/`unsubscribe`/`clear_subscribers` belong in setup rather than in a
per-frame loop.

## Dependency direction

`log` depends on `events` — `OnLogEvent` and `OnExceptionEvent` implement the
`Event` protocol — so **`events` must never import `log` at module scope**. The
dispatcher's default logger is resolved lazily inside `__init__` and
`EngineLogger` is a type-only import. Reintroducing a module-level
`from pyguara.log import ...` here deadlocks both packages on first import.

## Rules of thumb

1. `field(default_factory=time.time)`, never a `0.0` sentinel.
2. `queue_event()` off the main thread; everything else on it.
3. Return `False` to consume an event, and check `dispatch()`'s result if you
   care whether someone did.
4. Subscribe in setup, not per frame — it invalidates the handler cache.
5. `RAISE` in development. Reach for `IGNORE` only in tests.
