# Logging migration

Type: grilling
Status: open
Blocked by: 01
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
