# Execute the scene lifecycle repair

Type: task
Status: open
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
