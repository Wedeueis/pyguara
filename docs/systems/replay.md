# Replay System

`pyguara.replay` records the **input event stream** of a session frame by
frame and plays it back, re-driving the game loop from the recorded frame
timings. It is meant for bug repro, regression tests, and sharing a run.

## Wiring

`Application` owns the whole surface — you do not construct a `ReplayRecorder`
or `ReplayPlayer` yourself:

```python
app = create_application()
app.run(scene)                       # ... play normally ...

seed = app.start_recording(seed=42, description="boss fight bug")
# ... frames pass; every input event is captured ...
data = app.stop_recording()          # -> ReplayData
app.save_recording(data, "runs/boss")  # -> writes runs/boss.replay.gz
```

```python
app = create_application()
app.load_replay("runs/boss.replay.gz")   # starts playback immediately
app.run(scene)                            # the replay drives input; real
                                          # input is swallowed until it ends
```

Recording and playback are **mutually exclusive**: `start_recording()` while a
replay is loaded, or `load_replay()` while recording, raises `RuntimeError`.

Internally `Application` frames each recorder frame around `poll_events()`
(`begin_frame` / `end_frame`), feeds `ReplayRecorder` from
`InputManager.process_event` / the gamepad callbacks, and on playback pumps
each recorded frame's events back through `InputManager.process_replayed_event`,
which re-runs them through the *same* binding logic a live event takes.

## What is captured

Per frame: `frame_id`, `timestamp`, `delta_time`, and an ordered list of
`RecordedInputEvent` — keyboard up/down (with held modifiers), mouse
up/down/move (with position and modifiers), and gamepad buttons/axes.
Session metadata: `seed`, `start_scene`, engine version, UTC `recorded_at`,
duration, frame count, `description`.

`ReplayRecorder.record_action()` also exists for a game that wants to record a
*synthetic* high-level action directly (AI- or script-driven), replayed via the
`ACTION` branch of `process_replayed_event`.

## Determinism — what reproduces, what does not

On playback `Application.run()` takes each frame's duration from the recording
(`ReplayPlayer.peek_delta()`) instead of the wall clock, so the fixed-step
accumulator count, `_update()` deltas, tweens, particles and
`WaitForSeconds` all advance exactly as they did while recording, on any
machine and at any render rate.

Reproduces:

- bound actions and the raw `OnRawKeyEvent` / `OnMouseEvent` stream (position
  and modifiers included), so both gameplay and UI interactions replay;
- everything downstream of those that is a pure function of input + time —
  fixed-step physics, animation, coroutine waits, camera smoothing.

Does **not** reproduce, today:

- **RNG.** The `seed` is recorded and exposed as `ReplayPlayer.seed`, but
  nothing reseeds a random source on playback — there is no engine RNG service
  yet (tracked in the roguelike-core issue). A game that seeds its own RNG from
  `player.seed` on load will replay; one that calls `random.*` on the global
  module state will not.
- Anything a game reads from outside the input+time envelope directly:
  `time.time()` / `datetime.now()`, the filesystem, the network, thread
  scheduling.
- Floating-point results across different CPU/BLAS builds.
- Starting state. The game must rebuild an identical initial world; the
  regression test seeds both runs from one template `Entity` via
  `Entity.clone()`.

## File format

JSON, gzip by default. The on-disk format follows the extension: `.replay.gz`
is gzip, `.replay` is plain, a path with neither gets one appended per the
`compress` argument. `ReplaySerializer.get_metadata(path)` returns just the
`metadata` block for a save/replay menu. `load()` refuses a file whose
`metadata.version` exceeds `ReplaySerializer.SUPPORTED_VERSION` — there is no
migration layer.

## API surface

| Call | Purpose |
| --- | --- |
| `Application.start_recording(seed=None, description="")` | begin capture; returns the seed |
| `Application.stop_recording()` | end capture; returns `ReplayData` |
| `Application.save_recording(data, path, compress=True)` | write to disk |
| `Application.load_replay(path)` | load and start playback |
| `save_replay(data, path, compress=True)` / `load_replay(path)` | module-level serializer helpers |
| `ReplaySerializer.get_metadata(path)` | read the metadata block only |

`ReplayPlayer` exposes two playback models for a caller driving its own loop
(the `Application` path uses the first):

| Call | Model |
| --- | --- |
| `advance_frame()` + `peek_delta()` | one recorded frame per host frame; host steps its clock by the recorded delta |
| `update(dt)` | wall-clock; consumes every frame whose `timestamp` has elapsed; honours `playback_speed` |

Plus `seek_to_frame`, `pause_playback` / `resume_playback`, `progress`,
`current_frame` / `total_frames`, `is_playing` / `is_paused` / `is_finished`,
and `add_event_handler` for a callback per replayed event.
