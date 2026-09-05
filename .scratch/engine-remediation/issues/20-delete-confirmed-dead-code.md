# Delete confirmed dead code

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: follows from Dead-code disposition, ticket 09

## Question

Nothing to decide — execute the decision recorded in [Dead-code
disposition](09-dead-code-disposition.md): delete three islands confirmed to have zero
references anywhere in `pyguara/`, `games/`, or `tests/`.

## Steps

- Delete `pyguara/ecs/archetype.py` (`Archetype`, `ArchetypeGraph`). Confirmed no real
  references — the one `ecs/query_cache.py` grep hit is unrelated.
- Delete `pyguara/error/` (`exceptions.py`, `handlers.py`, `types.py`, `__init__.py`) —
  `EngineException`/`ErrorCategory`/`ErrorSeverity`/`safe_execute`/`retry`/`RetryPolicy`,
  never raised, applied, or imported outside the package itself. Not to be confused with
  `ErrorHandlingStrategy` (`events/types.py`, `di/types.py`) — a separate, in-use enum this
  ticket does not touch.
- Delete `games/XXX_scenes/` (`__init__.py`, `scenes.py`) — orphaned, placeholder-named demo,
  not referenced by `validate_demos.py` or anything else.

## Done when

- All three are gone.
- `grep -rn "archetype\|ArchetypeGraph"` (excluding this ticket file and the map) returns
  nothing under `pyguara/`.
- `grep -rln "from pyguara.error\|pyguara\.error\b"` returns nothing.
- `games/XXX_scenes/` no longer exists.
- Full suite green, `ruff check .` and `mypy pyguara` clean.

## Resolution

Executed exactly as specified, no surprises. Commit `e26dbf4`. Re-confirmed zero external
references before deleting (only hit: the pre-existing unrelated comment mentioning
"archetypes" in `ecs/query_cache.py`'s docstring, same one the ticket already called out).
All three done-when greps return clean; `mypy pyguara` checked 215 source files (was 220 —
matches the 5 deleted `.py` files: `archetype.py` + 4 in `error/`). Full suite green (1052
passed, unchanged — nothing exercised any of this code).
