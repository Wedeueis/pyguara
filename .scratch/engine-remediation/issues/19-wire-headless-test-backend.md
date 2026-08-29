# Wire HeadlessBackend as the integration-suite test backend

Type: task
Status: open
Blocked by: —
Audit ref: follows from Dead-code disposition, ticket 09

## Question

Nothing to decide — execute the decision recorded in [Dead-code
disposition](09-dead-code-disposition.md): `pyguara/graphics/backends/headless_renderer.py`'s
`HeadlessBackend` implements `IRenderer` but is never registered anywhere; the current
headless test path (`games/validate_demos.py`, `tests/integration/test_bootstrap_smoke.py`)
goes through real pygame with `SDL_VIDEODRIVER=dummy`/`SDL_AUDIODRIVER=dummy` instead. This is
test infrastructure only — it does not change the map's two-backend (pygame + ModernGL)
shipped-backend parity requirement.

## Steps

1. Confirm `HeadlessBackend` actually satisfies everything the current dummy-driver tests
   exercise (window lifecycle, `_render_direct()`'s `clear()`/`present()` path, whatever
   `validate_demos.py` touches) — extend it if something's missing.
2. Give `_setup_container()` (or a test-only variant of it) a way to select `HeadlessBackend`
   instead of the real Pygame backend.
3. Swap `tests/integration/test_bootstrap_smoke.py` and `games/validate_demos.py` onto it,
   dropping the `SDL_VIDEODRIVER`/`SDL_AUDIODRIVER` dummy-driver environment variables where
   they're no longer needed.

## Done when

- `HeadlessBackend` is a real, selectable backend choice in the composition root.
- The bootstrap smoke test and `validate_demos.py` run against it instead of pygame's dummy
  SDL drivers, and are demonstrably faster and no longer SDL-dependent.
- Full suite green, `ruff check .` and `mypy pyguara` clean.
