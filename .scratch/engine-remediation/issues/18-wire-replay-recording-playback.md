# Wire replay into InputManager and Application

Type: task
Status: open
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
