# Bootstrap smoke test

Type: task
Status: resolved
Blocked by: 02
Audit ref: root cause

## Question

Nothing to decide — execute. Write the test that would have caught all six criticals.

The audit's central finding is not any single bug: it is that 1,022 passing tests, clean ruff
and clean mypy coexisted with an engine whose public entry point could not run. Every
subsystem is tested against hand-built mocks, and all nine demos hand-roll their own DI
container. `tests/integration/test_app_flow.py` builds a container by hand that omits
`RenderGraph`, so it silently takes the working render path and passes.

Nothing in the repository executes `_setup_container()`.

## Done when

- An integration test calls the real `create_application()`, runs a real scene for ~30 frames
  under `SDL_VIDEODRIVER=dummy`, and asserts clean shutdown.
- It fails on unpatched `main` for BOOT-1 (and would have for BOOT-2 and LOG-1).
- It runs in the default `pytest` invocation, not behind an opt-in marker.
- A second case covers `create_sandbox_application()`, which inherits the same render path.

## Note for later

This is the seed of the integration suite that Demo migration will grow into. Keep it in
`tests/integration/` and name it so the demo cases can join it.

## Answer

Added `tests/integration/test_bootstrap_smoke.py` with two tests:
`test_create_application_boots_runs_and_shuts_down_cleanly` and
`test_create_sandbox_application_boots_runs_and_shuts_down_cleanly`. Each calls the real
`create_application()` / `create_sandbox_application()`, constructs a real `BootScene`, runs
30 fixed updates via `app.run()` (monkeypatching `_update` to flip `_is_running` off after 30
ticks, same pattern as `games/validate_demos.py`), and asserts clean shutdown: the loop ran
exactly 30 ticks, `_is_running` is `False`, `window.is_open` is `False`, and
`log_manager._loggers` is empty (handlers closed).

Deliberately **left unmarked** (no `@pytest.mark.integration`) even though the file lives in
`tests/integration/` — `make test-unit`/`make ci` filter tests with `-m "not integration"`,
so a marked test here would reproduce the exact blind spot the audit found: a real check that
never runs in the everyday gate. Verified it's picked up by
`pytest tests/ -m "not slow and not integration"` (the `make test-unit` filter). Verified via
`git stash` that both tests fail against the pre-fix code (BOOT-1's render crash reproduces in
both `create_application()` and `create_sandbox_application()`).

`tests/integration/test_app_flow.py`'s hand-built mock container (the thing that let all this
ship) was left untouched — replacing it isn't part of this ticket's scope.

Full suite: 1035 passed, `ruff check` clean.
