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
  fixed-step physics, animation, coroutine waits, camera smoothing;
- draws from `RandomService`: `start_recording()` pins the service's root
  seed into the replay and `load_replay()` re-roots the service on it;
- a flock: queries come back in a reproducible order, so `FlockingSystem`
  integrates the same way on playback
  (`tests/integration/test_replay_flock.py`).

Does **not** reproduce, today:

- **The global `random` module.** Only `RandomService` streams are
  re-rooted; `random.*` on the module's global state is not.
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

## A library of replays

`ReplayLibrary` keeps a game's replays by name in one folder, for a replay
menu:

```python
from pyguara.replay import ReplayLibrary

library = ReplayLibrary.for_game("Reclaimer")    # <data dir>/replays
library.save(app.stop_recording(), "boss rush")  # FileExistsError if taken
for entry in library.entries():                  # newest first
    label = entry.name if entry.metadata else f"{entry.name} (damaged)"
app.load_replay(str(library.path_of("boss rush")))
library.rename("boss rush", "best run")
library.delete("best run")
```

Each replay is `<name>.replay.gz`; a plain `.replay` saved there by other
means is found too. A damaged file is listed with `metadata` None rather
than left out, and `load()` raises for it. A name is refused, with
`ValueError`, unless it is a plain file name on every platform: no path
separators or `<>:"|?*`, no leading or trailing space or dot, not a name
Windows reserves, at most 100 characters. Any script is fine.

## Watching a replay: pause, step, speed and seek

`load_replay()` gives the application a `ReplayControls`, as
`app.replay_controls`. Setting `visible` draws a scrub bar along the bottom
of the screen and lets these keys drive it:

| Key | Does |
| --- | --- |
| Space | pause or resume |
| `.` | play one frame, then hold |
| `[` / `]` | slower / faster: 0.25x, 0.5x, 1x, 2x, 4x, 8x |
| Left / Right | back / forward 5 seconds |
| Home | back to the start |

The same are methods (`pause`, `resume`, `step`, `slower`, `faster`,
`seek(frame)`, `skip(seconds)`) for a game drawing its own buttons.

```python
def restart() -> None:
    scene_manager.register(ArenaScene(dispatcher))  # a fresh copy
    scene_manager.switch_to("ArenaScene")

app.load_replay(str(library.path_of("boss rush")), restart=restart)
app.replay_controls.visible = True
```

Every speed runs whole recorded frames, each with its own delta and input,
so a replay watched at 4x or stepped frame by frame ends where it would at
1x. Speed changes how many recorded frames run per displayed frame, not the
size of a step. Seeking forward runs the frames in between without
drawing them, 240 per displayed frame, so a long seek shows progress
instead of freezing the window.

**Seeking back needs `restart`.** A replay holds input, not world states, so
the only way back is to replay from the start. `restart` puts the world back
where the recording began, usually by switching to a fresh copy of the scene
it started in.
Before calling it the engine reseeds `RandomService`, resets its fixed-step
accumulator, and drops every event still waiting in `dispatch_after`
(`EventDispatcher.cancel_delayed()`): the replayed run schedules its own.
Without `restart`, seeking back raises `RuntimeError` and the back keys do
nothing. Anything the game keeps outside the scene is not reset, so
`restart` must reset it.

While the bar is hidden, a replay that ends hands input back to the game,
as it always has, and `replay_controls` becomes None. While it is shown,
playback holds on the last frame, so the viewer can seek back.

## API surface

| Call | Purpose |
| --- | --- |
| `Application.start_recording(seed=None, description="")` | begin capture; returns the seed |
| `Application.stop_recording()` | end capture; returns `ReplayData` |
| `Application.save_recording(data, path, compress=True)` | write to disk |
| `Application.load_replay(path, restart=None)` | load and start playback |
| `Application.replay_controls` | pause, step, speed and seek the replay; `visible` shows the scrub bar |
| `save_replay(data, path, compress=True)` / `load_replay(path)` | module-level serializer helpers |
| `ReplaySerializer.get_metadata(path)` | read the metadata block only |
| `ReplayLibrary(directory)` / `ReplayLibrary.for_game(name)` | named replays in a folder: `entries`, `save`, `load`, `rename`, `delete`, `path_of` |

`ReplayPlayer` exposes two playback models for a caller driving its own loop
(the `Application` path uses the first):

| Call | Model |
| --- | --- |
| `advance_frame()` + `peek_delta()` | one recorded frame per host frame; host steps its clock by the recorded delta |
| `update(dt)` | wall-clock; consumes every frame whose `timestamp` has elapsed; honours `playback_speed` |

Plus `seek_to_frame`, `pause_playback` / `resume_playback`, `progress`,
`current_frame` / `total_frames`, `is_playing` / `is_paused` / `is_finished`,
and `add_event_handler` for a callback per replayed event.
