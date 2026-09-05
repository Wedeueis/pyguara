# Execute the scene lifecycle repair

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: SCENE-1, SCENE-2 (high), follows from Scene lifecycle repair (ticket 07)

## Question

Nothing to decide — execute the decisions recorded in [Scene lifecycle
repair](07-scene-lifecycle-repair.md). Found unexecuted while working [Wire replay into
InputManager and Application](18-wire-replay-recording-playback.md): ticket 07 closed with
"Not implemented in this session ... Implementation is future work per the ticket-type
rule," but — like tickets 04 and 06 before it — no `task` ticket was ever created to carry
that work out. `pyguara/scene/manager.py` still has the pre-repair shape today: parallel
`_scene_stack`/`_pause_below_flags` arrays (SCENE-2's off-by-one bug still live), and
`TransitionManager` isn't called with `on_from_hidden`/`on_to_shown` callbacks anywhere.
`Application.__init__` also never calls `scene_manager.set_screen_size()`.

## Steps

1. **`pyguara/scene/transitions.py`**: `TransitionManager.start_transition()` takes two new
   callback params, `on_from_hidden: Optional[Callable[[], None]]` and
   `on_to_shown: Optional[Callable[[], None]]`. Two-phase transitions fire both at the
   existing phase-flip midpoint (already exactly when `render()` swaps which scene it
   shows); single-phase transitions fire both at transition start.
2. **`pyguara/scene/manager.py`**:
   - Per-operation callback mapping: `switch_to` → (`from_scene.on_exit`,
     `target_scene.on_enter`); `push_scene` → (`None`, `target_scene.on_enter`);
     `pop_scene` → (`popped_scene.on_exit`, `previous_scene.on_resume`).
   - Replace `_scene_stack: List[Scene]` + `_pause_below_flags: List[bool]` with one
     `_stack: List[StackEntry]` (a small `StackEntry(scene, pause_below)` — dataclass or
     NamedTuple), plus a new `_current_pause_below: bool` tracked alongside
     `_current_scene` (set from the `pause_below` argument whenever a scene becomes
     current; `False` for the base scene).
   - `_get_active_scenes()` (or whatever it's currently named — re-check, it may have
     moved) becomes one uniform walk: start with `current_scene`, gate =
     `_current_pause_below`; walk `_stack` from the top down, stop once the gate is
     `True`, else include the entry's scene and update the gate to *that entry's own*
     `pause_below`.
   - `cleanup()`: call `on_exit()` on `_current_scene` first (entered last), then walk
     `_stack` top-to-bottom calling `on_exit()` on every remaining entry.
3. **`pyguara/application/application.py`**: call
   `self._scene_manager.set_screen_size(self._window.width, self._window.height)` once in
   `__init__`, right after `_window` and `_scene_manager` are both resolved from the
   container (check `Window`'s actual width/height attribute names first).
4. Regression tests:
   - Two-phase `push_scene()` with a transition does NOT call `on_exit()` on the paused
     scene underneath.
   - Single-phase transition: `to_scene.on_enter()` has already run by the time `render()`
     first shows it (not deferred to transition completion).
   - A three-deep stack (base → paused middle → active top) with the middle scene's
     `pause_below=True` correctly excludes the base scene from `_get_active_scenes()`
     (or its renamed equivalent) — this is SCENE-2's regression case.
   - `cleanup()` calls `on_exit()` exactly once on every scene that was ever entered,
     including everything still on the stack.
   - `Application.__init__` results in `TransitionManager` holding the real window
     dimensions, not the 800×600 default.

## Done when

- `pyguara/scene/manager.py` has one `_stack: List[StackEntry]`, no parallel
  `_pause_below_flags` array.
- `TransitionManager.start_transition()` accepts and fires `on_from_hidden`/`on_to_shown`
  per the two-phase/single-phase timing above.
- `push_scene()` with a transition no longer exits the scene being paused underneath;
  `pop_scene()` resumes rather than re-entering the scene it returns to.
- `cleanup()` unwinds every scene ever entered, LIFO, exactly once each.
- `Application` calls `set_screen_size()` once at init with the real window dimensions.
- All four regression tests above pass.
- Full suite green, `ruff check .` and `mypy pyguara` clean.

## Resolution

Executed as specified. Commit `6794b03`.

`TransitionManager.start_transition()` takes `on_from_hidden`/`on_to_shown`, stored and
fired at the decided timing: two-phase fires both together at the existing phase-flip
midpoint in `update()` (where `on_enter()` used to be hardcoded); single-phase fires both
immediately inside `start_transition()` itself, removing the old completion-time
`if not two_phase: from_scene.on_exit(); to_scene.on_enter()` block entirely.
`SceneManager` wires the per-operation mapping from the ticket, with one deliberate,
necessary substitution: wherever the ticket names a bare `on_exit`/`on_resume`, the actual
callback passed is `self._exit_scene`/`self._resume_scene` (the existing wrapper methods
that additionally guarantee `system_manager.cleanup()`/`set_enabled(True)`), not the raw
scene method. Ticket 24 added those wrappers specifically because scenes already override
`on_exit()`/`on_resume()` without calling `super()`; passing the bare hook through the new
transition-callback path would have silently reopened that exact gap for any transitioned
switch/pop. `on_enter` has no such wrapper today (nothing else needs guaranteeing on
enter), so it's passed straight through, matching the ticket's text.

`_stack: List[StackEntry]` replaces the parallel arrays; `StackEntry.pause_below` holds
the *entry's own* pause_below (the value it was active with), populated by snapshotting
`_current_pause_below` onto the outgoing scene at push time — the direct mapping the old
parallel-array shape obscured into the off-by-one. `_get_active_scenes()` is the uniform
walk exactly as decided; `cleanup()` unwinds LIFO via `self._exit_scene`, which — like the
transition wiring above — was already the correct choice, not a new decision.

One bug fixed as a natural consequence of following the decision, not a separate scope
addition: the *original* `pop_scene()` called `_exit_scene()` on the popped scene
synchronously, before ever handing it to the transition manager — precisely the SCENE-1
symptom the ticket's own background section describes ("`pop_scene()` exits the outgoing
scene *before* handing it to the transition manager as a live render source"). Wiring
`popped_scene`'s exit through `on_from_hidden` instead (fired at the correct phase-timing
point) fixes this as a direct implication of "execute the decision", not an extra fix
layered on top.

`Application.__init__` now calls `set_screen_size()` right after `_window`/`_scene_manager`
are both resolved, confirmed via `Window.width`/`Window.height` properties.

All five regression tests (four elective plus the third's SCENE-2 case, which needed a
top-level `pause_below=False` to actually exercise the previously-buggy non-top-of-stack
branch rather than short-circuiting at the top-of-stack case) plus one more for pop's
resume-not-reenter guarantee, added to `tests/test_scene_stack.py`; the window-dimensions
check added to `tests/integration/test_bootstrap.py` against the real `create_application()`
app. Two pre-existing tests in `tests/test_scene_transitions.py`
(`test_manager_two_phase_transition`, `test_manager_single_phase_transition`) asserted the
*old* hardcoded timing (on_exit firing at two-phase start, deferred to completion for
single-phase) — exactly the behavior this ticket's decision inverts — so both were
rewritten to pass explicit `on_from_hidden`/`on_to_shown` callbacks and assert the
corrected timing instead of silently deleted or left failing.

Full suite green (1094 passed, up from 1088 -- 6 new tests). `ruff check .`,
`ruff format --check`, and `mypy pyguara` (216 files) all clean. No scope beyond the
ticket's own text was touched; `games/*` referenced neither `_scene_stack` nor
`_pause_below_flags` directly (grep-confirmed), so no caller-side changes were needed.
