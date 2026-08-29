# Fix the EngineLogger kwargs collision

Type: task
Status: resolved
Blocked by: —
Audit ref: LOG-1 (critical)

## Question

Nothing to decide — execute. `EngineLogger._log` funnels every caller kwarg into `extra=`,
and `logging` forbids `extra` shadowing reserved `LogRecord` attributes. Every one of these
raises today:

```
lg.exception(ValueError('x'))    KeyError: "Attempt to overwrite 'exc_info' in LogRecord"
lg.critical('m', exc_info=True)  KeyError: "Attempt to overwrite 'exc_info' in LogRecord"
lg.info('m', module='a')         KeyError: "Attempt to overwrite 'module' in LogRecord"
```

`pyguara/log/logger.py:100-106`.

This is first in the map because `Application.run` (`application.py:163`) uses
`self.logger.critical(..., exc_info=True)` as the game loop's last-resort handler. Every
uncaught exception is therefore replaced by a `KeyError` from the logging machinery. During
the audit this masked the BOOT-1 crash entirely. Until it is fixed, every subsequent ticket
debugs through a broken lens.

## Done when

- `_log` separates reserved `LogRecord` attribute names out of `**kwargs` and forwards them
  as real `logging` arguments rather than as `extra` keys.
- `exc_info`, `stack_info` and `stacklevel` behave as they do on a stdlib logger.
- `EngineLogger.exception()` works.
- A regression test covers all three failing calls above.
- `Application.shutdown()` calls `LogManager.shutdown()` — file handlers are currently left
  open, which is the same subsystem and cheap to fix here.

## Answer

Fixed in `pyguara/log/logger.py`. `EngineLogger._log` now:

1. Pops `exc_info`, `stack_info`, `stacklevel` out of `**kwargs` *before* building `extra`,
   and forwards them as real positional/keyword args to `self._logger.log(...)` — they now
   behave exactly as they do on a stdlib logger (verified: `exc_info=True` outside an active
   exception prints `NoneType: None`, matching stdlib).
2. For any remaining kwarg whose name collides with a real `LogRecord` attribute (the set
   `logging.Logger.makeRecord` checks against, plus `message`/`asctime`), renames the key by
   appending `_` before merging into `extra`, instead of raising `KeyError`. No caller data is
   silently dropped.

`Application.shutdown()` (`pyguara/application/application.py`) now calls
`self._log_manager.shutdown()` as its last step, closing file handlers.

Regression tests added in `tests/test_log_manager.py` (5 tests), covering all three calls
from the ticket plus stack_info/stacklevel forwarding and file-handler closure on shutdown.
`ruff check`, `mypy pyguara`, and the full suite (1027 tests) are clean.
