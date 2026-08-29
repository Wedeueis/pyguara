# Logging migration

Type: grilling
Status: resolved
Blocked by: 01
Assignee: Wedeueis Braz
Audit ref: coherence

## Question

The charting decision: `EngineLogger` survives and the 32 stdlib modules migrate onto it.
This ticket specifies the migration.

Today 32 modules call `logging.getLogger(__name__)` and three use `LogManager`. The two have
incompatible kwargs semantics, so no function can be written to accept either.
`EventDispatcher.__init__` types its logger as `logging.Logger` and bootstrap passes nothing
at all — meaning `ErrorHandlingStrategy.LOG` logs nothing and the event-queue overflow warning
can never fire.

## To resolve

- How does a leaf module reach a logger? `logging.getLogger(__name__)` needs no wiring;
  `LogManager` is a DI service. Modules like `ecs/component.py`, `prefabs/registry.py` and
  `resources/meta.py` currently import nothing from the container. Module-level accessor,
  constructor injection, or a global default manager?
- What is `EventDispatcher._logger` typed as after the migration, and who supplies it? The
  in-engine `EventMonitor` tool depends on log records reaching the dispatcher, so this is not
  cosmetic.
- Is `LogCategory` per-logger, per-call, or both? Today `get_logger(name, category)` keys the
  logger cache by `name.category`, which means the same module logging under two categories
  gets two logger objects.
- `EngineLogger.context()` adds filters to handlers, which are shared, while `_context_stack`
  is thread-local. A context entered on one thread currently affects records from every other.
  Fix, document, or drop the feature?
- `LogManager.configure()` refreshes levels on existing loggers but not handlers, so changing
  console/file settings after any logger exists silently does nothing. In scope here?
- Migration order and whether it lands as one change or in tranches.

## Answer

**Leaf-module access: hybrid, one shared instance.** A module-level default `LogManager`
singleton lives in `pyguara/log/` (e.g. `log/__init__.py` or `log/manager.py`).
`pyguara.log.get_logger(name)` is a thin accessor onto it — zero wiring, works for
`error/handlers.py`'s `safe_execute` decorator and any other genuinely non-DI leaf.
DI-constructed classes (`ComponentRegistry`, `MetaLoader`, `Application`, `Sandbox`, ...)
get the *same instance* via `LogManager` constructor injection — `bootstrap.py` must
configure that shared default instance in place (`log_manager.configure(...)`) and register
it, rather than constructing an unrelated second `LogManager()`. This is what makes
per-subsystem log separation possible later without the two access patterns drifting apart.

**`EventDispatcher._logger`: retyped `Optional[EngineLogger]`**, defaulting to
`logger or get_logger(__name__)`. No explicit wiring needed from `bootstrap.py` — this
sidesteps the current construction-order bug (`EventDispatcher()` is built before
`LogManager` exists in `bootstrap.py`) entirely, since the accessor always resolves to the
one shared instance regardless of when it's called, and that instance gets configured in
place afterward. Fixes both `ErrorHandlingStrategy.LOG` logging nothing and the dead
queue-overflow warning. Left uncategorized (no `LogCategory.SYSTEM` tag) — `EventDispatcher`
is core infrastructure used by leaf and DI code alike, forcing a categorized logger through
bootstrap would reintroduce the wiring/ordering problem just eliminated for a cosmetic tag.

**`LogCategory`: per-call only.** Drop the `category` parameter and `name.category` key
suffixing from `get_logger()`. Traced the actual consumer: `EventIntegratedHandler.emit()`
reads `record.category`, populated by the **per-call** `category` kwarg already on
`EngineLogger.debug/info/warning/error/critical`. The per-logger suffix only renamed the
underlying stdlib logger (`record.name`) and had zero effect on `record.category` — it was
decorative and disconnected from what anything downstream actually reads, and its only real
effect was the bug this ticket named (same module + two categories = two duplicate logger
objects with duplicate handler sets). `Application`/`Sandbox` drop the `LogCategory` argument
from their `get_logger()` calls.

**`EngineLogger.context()` / `ContextualFilter`: dropped.** Zero call sites in `pyguara/`,
`games/`, or `tests/` — confirmed by search. The bug is real if it were ever used: `context()`
pushes onto a `threading.local()` stack (implying per-thread isolation was intended) but
attaches `ContextualFilter` to `self._logger.handlers`, which is shared across every caller
of that named logger regardless of thread — since PyGuara's event system documents
background-thread logging as a supported pattern (`queue_event()`), two threads sharing a
named logger while one holds a `context()` block would leak that context onto the other's
unrelated records. Not worth fixing something with no call site to validate the fix against;
cheap to reintroduce later against a real use case if one appears.

**`LogManager.configure()`: fixed, in scope, now load-bearing.** Must rebuild each existing
logger's handler set (not just `.setLevel()`) when settings change. This graduated from
"minor bug" to load-bearing because of the leaf-access decision above: after migration, most
of the 31 modules construct their `EngineLogger` eagerly at import time via the accessor,
before `bootstrap.py` ever calls `configure(log_file=..., console=...)` — without this fix,
file logging would silently never reach them.

**Migration order: one task ticket, not tranches.** The core `pyguara/log/` surgery (accessor,
`configure()` fix, dropping category-keying and `context()`) and the leaf-module sweep (31
`logging.getLogger(__name__)` call sites + `error/handlers.py`'s inline one + dropping the
`LogCategory` arg from `Application`/`Sandbox`) are interdependent — a half-migrated state
isn't a coherent place to pause, and the sweep itself is mechanical rather than
intellectually heavy. Execute core-surgery-with-its-own-tests first, then the sweep, within
one ticket. See [Execute the logging migration](16-execute-logging-migration.md) — created as
a `task` ticket to carry out this decision, blocked on nothing (ticket 01, its own blocker,
is already resolved).
