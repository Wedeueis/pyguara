# Wire replay into InputManager and Application

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: follows from Dead-code disposition, ticket 09

## Question

Nothing to decide — execute the decision recorded in [Dead-code
disposition](09-dead-code-disposition.md): `replay/` (`ReplayRecorder`/`ReplayPlayer`/
`ReplaySerializer`) is fully built and tested in isolation (`tests/test_replay.py`) but not
connected to `InputManager` or `Application`. Wire it in.

## Steps

1. `InputManager` recording hook: a way to observe every input event as it's processed and
   feed it to a `ReplayRecorder` when one is active (start/stop recording), without recording
   becoming mandatory overhead when nothing is recording.
2. `Application`-level integration: start/stop a recording, save it via `ReplaySerializer`,
   load and play one back via `ReplayPlayer` — wire these as real entry points (CLI flag,
   `Application` method, or both — pick whichever matches how the rest of `Application`'s
   surface is shaped).
3. Entity reconstruction on playback: use `Entity.clone()` (added in ticket *ECS lifecycle
   contract* specifically for this kind of detached-copy use case) rather than `copy.deepcopy`
   — `Entity` rejects deepcopy outright.
4. A regression test that records a short deterministic session (fixed seed, scripted input),
   saves it, plays it back through a real `create_application()`/scene, and asserts the
   replayed state matches the recorded one.

## Done when

- `InputManager` can feed a live `ReplayRecorder` without recording being mandatory when idle.
- `Application` exposes a real way to start/stop recording and play a saved replay back.
- Playback reconstructs entities via `Entity.clone()`, not deepcopy.
- The end-to-end regression test above passes.
- Full suite green, `ruff check .` and `mypy pyguara` clean.

## Resolution

Executed as specified. Commit `65c6c9e`.

**`InputManager`** gained `attach_recorder()`/`detach_recorder()` and a `_recorder:
Optional[ReplayRecorder]` field; `process_event()` calls the matching `record_*` method
(guarded by a single `is not None and .is_recording` check, so idle overhead is one
attribute read plus one property check) for the KEY_DOWN/UP, MOUSE_DOWN/UP, and MOUSE_MOVE
branches. Deliberately did *not* touch the legacy `JOY*` branches — those belong to [Input
wiring and legacy retirement](10-input-wiring-and-legacy-retirement.md)/[its execution
ticket](21-execute-input-wiring.md), not this one, and recording through code about to be
deleted would've been wasted work. A new `process_replayed_event()` translates a
`RecordedInputEvent` back through the exact same `_handle_input()`/`_handle_axis()`/
`_dispatch_action()` paths a live event takes, so playback is driven by the same binding
logic as recording, not a parallel reimplementation.

**`Application`** gained `start_recording()`/`stop_recording()`/`save_recording()`/
`load_replay()` as the real entry points (method-based, matching the rest of
`Application`'s surface — no CLI flag added, since nothing else on `Application` is
CLI-driven either), mutually exclusive with each other via `RuntimeError`.
`_process_input()` now takes `frame_time` (needed to frame recorder frames) and wraps the
per-frame poll with `begin_frame()`/`end_frame()` while recording, driving
`ReplayPlayer.advance_frame()` into the input manager while a replay is loaded. Factored
into `_begin_replay_frame()`/`_end_replay_frame()` so `SandboxApplication`'s own
`_process_input()` override (interleaving `ToolManager` priority) shares the wiring
instead of duplicating it — required a signature fix there too (`mypy` caught the
[override] mismatch).

**Regression test** (`tests/integration/test_replay_wiring.py`, deliberately unmarked like
`test_bootstrap_smoke.py` so it runs under `make test-unit`): two real
`create_application()`/`BootScene` instances. The first records a 10-frame scripted
session (three key-triggered moves) via `_process_input()` fed a monkeypatched
`poll_events()`, saves via `ReplaySerializer` to a real file, and shuts down. The second
loads that file and drives the same number of frames with a monkeypatched
`poll_events()` returning nothing (proving the replay itself drives movement, not
leftover real input). Both runs move a `Transform` component on an entity via the same
`OnActionEvent` handler; both entities are seeded via `template.clone(...)` from one
shared template `Entity` (never `copy.deepcopy`, which `Entity` rejects), so both runs
start from bit-for-bit identical state. Asserts the two final positions match, plus a
sanity check that movement actually happened (rules out a false-positive "nothing moved"
pass).

**Found mid-execution, not fixed here — spun into [Execute the scene lifecycle
repair](29-execute-scene-lifecycle-repair.md):** while wiring `_boot()`'s scene
registration for the test, noticed `pyguara/scene/manager.py` still has the *pre-repair*
shape — parallel `_scene_stack`/`_pause_below_flags` arrays (SCENE-2's off-by-one still
live) and no `on_from_hidden`/`on_to_shown` callback wiring. [Scene lifecycle
repair](07-scene-lifecycle-repair.md) closed noting "Implementation is future work," but —
like tickets 04 and 06 before it — no `task` ticket was ever created to carry it out. Not
touched here since it's unrelated to replay wiring and would have widened this ticket's
scope.

Full suite green (1050 passed), `ruff check .` and `mypy pyguara` clean.
