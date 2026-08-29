# Execute the logging migration

Type: task
Status: open
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
