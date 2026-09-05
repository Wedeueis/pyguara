# Execute the logging migration

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: coherence (follows from Logging migration, ticket 08)

## Question

Nothing to decide — execute the decisions recorded in
[Logging migration](08-logging-migration.md). Sequence core-surgery-with-tests first, then
the mechanical leaf-module sweep, as one ticket.

**Core surgery in `pyguara/log/`:**
- Add a module-level default `LogManager` singleton and a `get_logger(name)` accessor onto
  it (exposed from `pyguara/log/__init__.py` alongside the existing exports).
- Fix `LogManager.configure()` to rebuild each existing logger's handler set (console/file/
  event), not just call `.setLevel()`.
- Drop the `category` parameter and `name.category` key-suffixing from
  `LogManager.get_logger()` — category stays purely a per-call kwarg on
  `EngineLogger.debug/info/warning/error/critical` (unchanged).
- Delete `EngineLogger.context()`, `_context_stack`, `_get_merged_context()`, and
  `ContextualFilter` (`pyguara/log/handlers.py`) — confirmed zero call sites in `pyguara/`,
  `games/`, `tests/`.

**`EventDispatcher` fix (`pyguara/events/dispatcher.py`):**
- Retype `_logger`/the constructor param from `Optional[logging.Logger]` to
  `Optional[EngineLogger]`.
- Default: `self._logger = logger or get_logger(__name__)`.

**Bootstrap fix (`pyguara/application/bootstrap.py`):**
- Point `_setup_container()` at the shared default `LogManager` instance (`log_manager.
  configure(...)` then `container.register_instance(LogManager, log_manager)`) instead of
  constructing an unrelated second `LogManager()`.
- Drop the `LogCategory` argument from the `Application`/`Sandbox` `get_logger()` calls
  (`"Application"`, `"Sandbox"` — no more `.system`/`.editor` key suffix).

**Leaf-module sweep** — for each of the 31 modules currently doing
`logger = logging.getLogger(__name__)` at module scope, plus the inline
`logging.getLogger("pyguara.error")` in `error/handlers.py`'s `safe_execute`:
replace with `from pyguara.log import get_logger` / `logger = get_logger(__name__)`.
(Full current list, from `grep -rn "logging.getLogger" pyguara`: `resources/meta.py`,
`persistence/migration.py`, `cli/build.py`, `input/manager.py`, `persistence/storage.py`,
`prefabs/loader.py`, `input/gamepad.py`, `input/binding.py`, `ecs/component.py`,
`tools/manager.py`, `resources/manager.py`, `graphics/backends/pygame/loaders.py`,
`di/container.py`, `dev/file_watcher.py`, `audio/backends/pygame/pygame_audio.py`,
`dev/hot_reload.py`, `prefabs/factory.py`, `persistence/manager.py`,
`editor/panels/inspector.py`, `replay/serializer.py`, `prefabs/registry.py`,
`audio/audio_source_system.py`, `error/handlers.py`, `editor/panels/assets.py`,
`replay/player.py`, `audio/manager.py`, `editor/layer.py`,
`graphics/backends/headless_renderer.py`, `replay/recorder.py`, `graphics/window.py`,
`graphics/components/animation.py` — re-grep before starting in case this has drifted.)

## Done when

- `pyguara.log.get_logger(name)` exists, is backed by one shared default `LogManager`
  instance, and that same instance is what `bootstrap.py` configures and registers in DI.
- `LogManager.configure()` rebuilds handlers on loggers that already existed when it's
  called; a regression test constructs a logger via the accessor, calls `configure(log_file=
  ...)` afterward, and asserts the logger's handlers now include a `FileHandler` for that
  path.
- `get_logger()` no longer accepts a `category` argument; a regression test confirms the same
  name always returns the same logger instance regardless of what category is logged
  per-call.
- `EngineLogger.context()`, `_context_stack`, `_get_merged_context()`, and `ContextualFilter`
  are deleted, not merely unused.
- `EventDispatcher` constructed with no logger argument still logs — a regression test
  triggers the queue-overflow warning path (or an `ErrorHandlingStrategy.LOG` handler) and
  asserts a record was emitted, without passing an explicit logger.
- Every one of the 31 (+1) leaf modules uses the accessor; `grep -rn "logging.getLogger"
  pyguara` returns nothing outside `pyguara/log/logger.py` itself (which legitimately wraps
  stdlib `logging.getLogger` inside `EngineLogger.__init__`).
- `Application`'s and `Sandbox`'s `get_logger()` calls no longer pass a `LogCategory`.
- Full suite green, `ruff check .` and `mypy pyguara` clean.

## Resolution

Executed as specified. Commit `b6d9027`.

**Core surgery** landed as designed: `pyguara/log/manager.py` gains a module-level
`default_log_manager = LogManager()` singleton plus `get_logger(name)` accessor, both
re-exported from `pyguara/log/__init__.py`. `LogManager.configure()` now calls a new
`EngineLogger.reconfigure()` on every already-constructed logger (extracted from
`__init__`, which now just calls it once), closing old handlers before rebuilding —
covered by a new regression test that calls `configure(log_file=...)` after a logger
already exists and asserts a `FileHandler` shows up on it. `get_logger()` dropped its
`category` param and key-suffixing entirely (regression test: same name → same instance).
`EngineLogger.context()`/`_context_stack`/`_get_merged_context()` and `ContextualFilter`
are deleted outright, not merely unused.

**`EventDispatcher`**: `_logger` is now `Optional[EngineLogger]`, defaulting to
`logger or get_logger(__name__)`. A regression test constructs a dispatcher with no
logger, forces a queue-overflow warning (`queue_warning_threshold=0`), and asserts a
record was emitted via `caplog` — confirming both `ErrorHandlingStrategy.LOG` and the
overflow warning now actually log.

**Bootstrap**: `_setup_container()` now points at `default_log_manager` instead of
constructing a second, unrelated `LogManager()`; `Application`/`Sandbox`'s `get_logger()`
calls dropped their `LogCategory` arg (and the now-unused `LogCategory` import).

**Leaf-module sweep**: all 30 `logging.getLogger(__name__)` module-level call sites plus
`error/handlers.py`'s inline one now use `from pyguara.log import get_logger`. Confirmed
by `grep -rn "logging.getLogger" pyguara` returning only `pyguara/log/logger.py`'s own
legitimate wrap inside `EngineLogger.__init__`.

**Two things found and fixed mid-execution, not called out in the decision ticket:**

1. **Import cycle.** `pyguara/log/{logger,handlers,manager}.py` imported `EventDispatcher`
   at runtime for type hints only (never `isinstance`-checked — just a constructor param
   and a dispatch() call on whatever's passed). Making `EventDispatcher` default to
   `get_logger()` needs `pyguara.events.dispatcher` to import `pyguara.log` at module
   level, which would cycle back. Fixed by moving all three `EventDispatcher` imports
   behind `TYPE_CHECKING` with quoted annotations — purely a typing-time reference now,
   zero runtime behavior change.
2. **printf-style call sites.** A meaningful fraction of the 30 modules log
   stdlib-style, e.g. `logger.error("Failed '%s': %s", path, e, exc_info=True)`. Since
   `EngineLogger.error/warning/etc.` had `category` as the second *positional* parameter,
   any of these would have bound the first extra arg to `category` and then raised
   `TypeError` on a third — a straight crash the moment those lines execute, not caught
   by mypy or the type-check-excluded test suite. Fixed at the root rather than rewriting
   every call site: `category` became keyword-only and `debug/info/warning/error/critical`
   gained `*args` passthrough to `self._logger.log(level, msg, *args, ...)`, preserving
   stdlib's lazy `%`-formatting exactly. Regression test added
   (`test_printf_style_args_are_forwarded_like_stdlib_logging`). No caller outside
   `pyguara/log/` passed `category` positionally, so this is purely additive — nothing to
   invalidate elsewhere on the map.

Full suite green (1053 passed, up from 1048 — 5 new regression tests), `ruff check .` and
`mypy pyguara` clean. `games/*/bootstrap.py`'s own `LogManager(event_dispatcher)`
constructions were deliberately left untouched — that's *Bootstrap collapse* fog, not this
ticket.
