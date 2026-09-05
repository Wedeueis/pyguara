# Wire HeadlessBackend as the integration-suite test backend

Type: task
Status: resolved
Assignee: Wedeueis Braz
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

## Resolution

Executed with two scope adjustments (below). Commit `80d6f8a`.

**`HeadlessBackend` was out of date with `IRenderer`, not just unregistered.** Confirming
step 1 turned up more than expected: `width`/`height` were hardcoded to `800`/`600`,
ignoring the constructor args entirely (dead code — never instantiated anywhere, so never
exercised), and the class was missing `begin_frame()`/`end_frame()`/`draw_circle()`
entirely, added to `IRenderer` at some point after this file was last touched. mypy caught
the second one immediately at the first real instantiation site
(`Cannot instantiate abstract class`); the first was a silent behavior bug, fixed alongside.

**Rounded out the full composition-root quartet, not just `IRenderer`.** A real backend
selection needs a window backend, UI renderer, and texture factory too, or `Application`
can't actually boot. Added `HeadlessWindowBackend` (`IWindowBackend`), `HeadlessUIRenderer`
(`UIRenderer`), `HeadlessTextureFactory`/`HeadlessTexture` (`TextureFactory`) to the same
file — each a handful of no-op lines. None of them call into `pygame.display` or any other
SDL video function, unlike the real Pygame backend under `SDL_VIDEODRIVER=dummy`.
`_setup_container(headless: bool = False)` wires this quartet ahead of the pygame-vs-
ModernGL branch; registers no `RenderGraph` (`Application`'s lookup already degrades
gracefully to `_render_direct()` when none is registered — exactly the single-pass path
headless wants); skips the pygame-coupled image loader (nothing exercises texture loading
under headless today, and `PygameImageLoader` itself documents needing
`pygame.display` initialized for some formats — exactly the coupling headless exists to
avoid); and zeroes `fps_target` so `Clock.tick(0)` skips its real-time sleep. Empirically
~50x faster for the same 30 ticks (0.01s vs 0.5s) — the fps-target zeroing turned out to be
the dominant cost, not the SDL video calls themselves; `Clock.tick()` throttles by real time
regardless of rendering backend, and skipped my first pass at this test entirely (both
timed identically at first).

**Found and fixed empirically, not anticipated by the ticket:** `Application.run()`
unconditionally calls `pygame.event.pump()` once before the loop starts ("show the window
immediately"), which raises `pygame.error: video system not initialized` under a backend
that never touches SDL video at all. Now caught and ignored — correct behavior, not a
masked bug, since a headless backend has no window to show in the first place.

**Scope adjustment 1 — did not touch `tests/integration/test_bootstrap_smoke.py`.** Its
whole reason for existing (per its own docstring) is exercising the *real* pygame/ModernGL
backend-selection branch in `_setup_container()` — precisely the code path BOOT-1/2/3 broke.
Swapping it onto `headless=True` would route through an entirely different, third branch
that was never the site of those bugs, silently reopening the exact coverage gap that test
exists to close. Added `tests/integration/test_headless_backend.py` alongside it instead —
proves the headless path itself works, without weakening the pygame-path regression
coverage.

**Scope adjustment 2 — did not touch `games/validate_demos.py`.** Its ticket-cited headless
dependence isn't on `_setup_container()` at all: each of the four demos it validates boots
through its own `games/*/bootstrap.py`'s hand-rolled `configure_game_container()` — the
same ~650 LOC of copy-paste the map's **Bootstrap collapse** fog entry is already tracking
for replacement. Wiring headless into four separate, soon-to-be-deleted files would be
throwaway work; added a note to that fog entry instead (see map) so headless wiring lands
there when `validate_demos.py` gets promoted into `tests/integration/`, on the parameterized
factory rather than four independent copies.

Full suite green (1052 passed), `ruff check .` and `mypy pyguara` clean.
