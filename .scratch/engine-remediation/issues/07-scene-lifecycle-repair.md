# Scene lifecycle repair

Type: grilling
Status: resolved
Blocked by: 04
Audit ref: SCENE-1, SCENE-2 (high)

## Question

**SCENE-1 — any scene change with a transition skips the lifecycle entirely.** The immediate
branch of `switch_to()` calls `on_exit()` then `on_enter()`. The transition branch
(`scene/manager.py:78-88`) installs an `on_complete` that only assigns `_current_scene` —
neither hook fires. `push_scene()` has the same asymmetry. `pop_scene()` exits the outgoing
scene *before* handing it to the transition manager as a live render source. `cleanup()`
ignores every scene still on the stack.

Net effect: the transitions module — 478 LOC, fully unit-tested — is unsafe for any scene that
loads or releases resources in its hooks. `SceneManager.set_screen_size()` is also never
called by `Application`, so transitions run against unset dimensions.

**SCENE-2 — off-by-one in `_get_active_scenes()`.** `_pause_below_flags[i]` holds the
`pause_below` of the scene pushed directly above `_scene_stack[i]`. The top-of-stack case
correctly reads `flags[-1]`, but the general case reads `flags[i + 1]`. A three-deep stack
(game → pause → settings) consults the wrong flag and updates scenes that asked to be frozen.

## To resolve

- When do `on_exit` and `on_enter` fire relative to a transition — at its start, at its end,
  or split (exit at start, enter at end)? This is a real design call: a fade-out wants the
  outgoing scene still rendering, which argues against exiting it up front.
- What renders during a transition, given the charting decision that scenes submit to
  `RenderSystem` rather than drawing? Two scenes submitting into one queue needs an answer.
  Coordinate with RenderSystem wiring when that graduates from the fog.
- Should `_pause_below_flags` exist as a parallel array at all, or become a field on the
  stacked entry? The off-by-one is a symptom of the parallel-array shape.
- Does `cleanup()` unwind the whole stack, and in what order?
- Who calls `set_screen_size()`, and what happens on window resize?

## Answer

Grilled live with the dev, one sub-question at a time. Investigation first turned up that
SCENE-1 as originally described didn't quite match the code: hooks *do* fire today via
`TransitionManager` (not via `SceneManager`'s `on_complete`, which only updates the
`_current_scene` bookkeeping pointer). The real, sharper bugs found while tracing it:

- **Push + two-phase transition destroys the paused scene.** `start_transition()`
  unconditionally calls `from_scene.on_exit()` for any two-phase transition — for
  `push_scene()`, `from_scene` is the scene that just got `on_pause()`'d and is supposed to
  stay alive underneath. Today, pushing a pause-menu scene with a two-phase transition tears
  down the gameplay scene it's pausing over.
- **Single-phase transitions render `to_scene` before its `on_enter()` ever runs.**
  `render()`'s single-phase branch shows `to_scene` from the transition's first frame, but
  `on_enter()` isn't called until `update()` detects completion at the very last frame.
- SCENE-2's off-by-one, traced to its root: `_pause_below_flags[i]` is *already*, by
  construction, "the pause_below flag of the scene directly above `stack[i]`" for every `i` —
  the existing top-of-stack special case (`flags[-1]`) is correct only by coincidence
  (`flags[-1] == flags[len-1]`, which is what that branch wants anyway). The bug is purely
  that the general branch checks `flags[i + 1]` instead of `flags[i]`.

Decisions:

1. **Transition lifecycle hooks: caller-supplied callbacks, not hardcoded calls.**
   `TransitionManager.start_transition()` takes two callbacks, `on_from_hidden` and
   `on_to_shown`, fired at the moment `render()` stops/starts showing that scene rather than
   at a hardcoded point:
   - **Two-phase**: both fire together at the existing phase-flip midpoint (already exactly
     when `render()` swaps which scene it shows).
   - **Single-phase**: both fire at transition *start* — `render()` shows `to_scene` from
     frame one and never shows `from_scene` at all, so a single-phase transition becomes
     lifecycle-equivalent to the immediate-switch path, just with a cosmetic overlay on top.
   - Per-operation mapping: `switch_to` → (`from_scene.on_exit`, `target_scene.on_enter`);
     `push_scene` → (`None` — already paused, stays alive — `target_scene.on_enter`);
     `pop_scene` → (`popped_scene.on_exit`, `previous_scene.on_resume`). This fixes both bugs
     above: push no longer exits the paused scene, and pop resumes rather than re-entering.

2. **Stack shape: single list of entries, plus a tracked current-gate.** Replace
   `_scene_stack` + `_pause_below_flags` (parallel arrays) with one
   `_stack: List[StackEntry]` (`StackEntry(scene, pause_below)`), plus a new
   `_current_pause_below: bool` tracked alongside `_current_scene` (set from the
   `pause_below` argument whenever a scene becomes current; `False` for the base scene).
   `_get_active_scenes()` becomes one uniform walk: start with `current_scene`, gate =
   `_current_pause_below`; for each entry from the top of `_stack` down, stop if the gate is
   `True`, else include the entry's scene and update the gate to *that entry's own*
   `pause_below`. No index arithmetic, nothing to get off-by-one on.

3. **`cleanup()`: unwind LIFO.** `on_exit()` on `_current_scene` first (entered last), then
   walk `_stack` top-to-bottom calling `on_exit()` on every entry. Every scene that was ever
   entered gets torn down exactly once — today, everything still on the stack leaks past
   `.clear()` with no teardown at all.

4. **Screen size: `Application` calls it once at init.** `set_screen_size()` is currently
   never called outside tests; `TransitionManager` defaults to a hardcoded 800×600. Fix:
   `Application` calls `scene_manager.set_screen_size(window.width, window.height)` once,
   right after both are resolved from the container. Live window-resize support doesn't exist
   anywhere in the engine today (no resize event on `Window` or `Application`) — building that
   pipeline is a separate feature, out of scope here.

**Scope note:** "what renders during a transition, given RenderSystem submit-based rendering"
stays with [RenderSystem wiring](13-rendersystem-wiring.md) (still open) — this ticket's
answer is scoped to the current `scene.render(world_renderer, ui_renderer)` mechanism,
unchanged by this decision.

Not implemented in this session — this ticket is a decision, not a `task`. Implementation is
future work per the ticket-type rule.
