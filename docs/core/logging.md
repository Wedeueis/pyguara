# Logging System

`pyguara.log` wraps Python's `logging` with three additions: a **category** on
every record, arbitrary **structured fields**, and optional republishing of
records as engine **events**.

## Getting a logger

```python
from pyguara.log import get_logger

logger = get_logger(__name__)

logger.info("Scene loaded")
logger.warning("Texture missing, using fallback")
logger.error("Failed to load '%s': %s", path, reason)
```

`get_logger()` is backed by a shared `default_log_manager`, so a module can
take a logger at import time and still pick up configuration applied later.

## Configuring

```python
from pathlib import Path
from pyguara.log import LogLevel, default_log_manager

default_log_manager.configure(
    level=LogLevel.DEBUG,
    log_file=Path("logs/game.log"),
    console=True,
)
```

`configure()` rebuilds the handlers of every logger already handed out — not
just their levels. Most engine modules build a logger at import time, long
before configuration runs, so without that rebuild file and event output would
silently never reach them.

`dispatcher` is the one parameter that distinguishes "unspecified" from
"None": omit it to keep the current dispatcher, pass `None` explicitly to
detach it.

## Categories and structured fields

Every record carries a `LogCategory` saying which subsystem it came from.
Categories are orthogonal to levels — a category says *where*, a level says
*how severe*.

```python
from pyguara.log import LogCategory

logger.warning("Body count high", category=LogCategory.PHYSICS)
```

Any other keyword becomes a structured field on the record, reachable by
handlers and carried into `OnLogEvent`:

```python
logger.info("Loading asset", asset="hero.png", retries=2)
```

A field whose name collides with a real `LogRecord` attribute is renamed with a
trailing underscore rather than dropped — `module="mine"` arrives as
`module_`.

`exc_info`, `stack_info` and `stacklevel` are passed through to the standard
library instead of being treated as fields.

## Exceptions

```python
try:
    load(path)
except OSError as error:
    logger.exception(error, "Could not load level")
```

Unlike `logging.Logger.exception`, this takes the exception object rather than
reading the ambient one, so it works outside an `except` block. It also
dispatches `OnExceptionEvent` when a dispatcher is configured.

## Event integration

With a dispatcher configured, every record is also republished as `OnLogEvent`
— which is how an in-game console or the editor's log panel subscribes to
engine output:

```python
default_log_manager.configure(dispatcher=event_dispatcher)

event_dispatcher.subscribe(OnLogEvent, console_panel.append)
```

`OnLogEvent.context` carries the structured fields plus the record's origin:
logger name, module, line and thread.

!!! note "`log` depends on `events`, never the reverse"
    `OnLogEvent` and `OnExceptionEvent` implement the `Event` protocol at
    runtime. `pyguara.events` therefore must not import `pyguara.log` at
    module scope — see [Event System](events.md).

## Propagation

Engine loggers install their own handlers **and** propagate to ancestor
loggers by default. Propagation is what lets an application capture engine
output through its own `logging` configuration.

The cost is that if that configuration *also* prints, every record appears
twice. Two ways out:

```python
# Let the application own all output
default_log_manager.configure(console=False)

# Or keep the engine's console output and stop propagating
default_log_manager.configure(console=True, propagate=False)
```

## Shutdown

```python
default_log_manager.shutdown()
```

Closes **and detaches** every handler the manager installed. Detaching is the
part that matters: a closed `FileHandler` that is still attached silently
reopens its file on the next record, so closing alone would leave logging
running.

Handlers installed by anyone else — the application, a test — are left alone,
by `shutdown()` and by `configure()` alike.

## A note on shared state

`EngineLogger` wraps `logging.getLogger(name)`, which is process-global. Two
`LogManager` instances using the same name share one underlying logger. Each
removes only the handlers it installed, so they no longer tear down each
other's, but level and propagation are shared and the last writer wins.

Prefer the single `default_log_manager`. Construct a second `LogManager` only
in tests, with distinct logger names.

## Levels

| Level | Use for |
| --- | --- |
| `DEBUG` | High-frequency detail: resource loads, per-frame events |
| `INFO` | Lifecycle: startup, scene switches, shutdown |
| `WARNING` | Recoverable problems: a missing texture falling back |
| `ERROR` | Failures and exceptions |
| `CRITICAL` | Unrecoverable failures |

## Rules of thumb

1. `get_logger(__name__)` at module scope; configure once at bootstrap.
2. Never `print()`.
3. Pass printf-style arguments rather than pre-formatting, so a filtered-out
   record costs nothing to build.
4. Put facts in structured fields, not in the message string — they survive
   into `OnLogEvent` where the message text does not parse.
5. Categorise anything a subsystem emits; the default `SYSTEM` is for the
   engine core.
