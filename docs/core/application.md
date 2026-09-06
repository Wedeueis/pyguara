# Application Lifecycle

`pyguara.application` owns the game loop, the composition root that wires
everything together, and the shutdown sequence.

## The loop

`Application.run()` drives a **fixed-timestep loop with an accumulator**, so
physics behaves identically whatever the display framerate:

```
per frame:
  1. measure frame time, clamped to physics.max_frame_time
  2. poll input and system events
  3. drain the queued-event backlog  (once, under a time budget)
  4. while accumulator >= fixed_dt:  _fixed_update(fixed_dt)
  5. _update(frame_time)
  6. _render()
```

**`_fixed_update(fixed_dt)`** may run several times in one frame, or none at
all. Anything that must be reproducible belongs here: physics, AI decisions,
collision response.

**`_update(dt)`** runs exactly once per frame, at display rate. Anything that
should look smooth belongs here: UI, tweens, particles, camera smoothing,
coroutines.

**`_render()`** computes `alpha` — how far the frame sits between the last two
fixed steps — and hands it to the scene so `Transform.interpolate` entities do
not visibly move at the physics rate.

### Why the frame time is clamped

`physics.max_frame_time` (0.25s by default) bounds how much backlog one frame
can add. Without it, a frame that takes longer than the work it schedules
compounds into an ever-growing queue of fixed updates — the "spiral of death".
At 60 Hz the clamp caps a single frame at 15 fixed steps.

### Why the event queue is drained outside that loop

Queued events are drained **once per frame**, before the fixed updates that
consume them, under `event_queue_time_budget_ms` (5ms by default).

Draining inside the accumulator loop would multiply the budget by the step
count — a frame lagging by the full `max_frame_time` would spend 15× the
budget, at exactly the moment a spiral is beginning. The budget exists to
prevent that, so it is spent per frame.

## Lifecycle events

```python
from pyguara.events.lifecycle import ApplicationStartEvent, QuitEvent

dispatcher.subscribe(ApplicationStartEvent, on_start)
dispatcher.subscribe(QuitEvent, save_before_exit)
```

`ApplicationStartEvent` fires once, after the starting scene is active and
before the first frame. `QuitEvent` fires when the window reports a close
request, before `shutdown()` runs, so handlers can still touch live state.

## Shutdown

`run()` always calls `shutdown()` on the way out — normal exit, `KeyboardInterrupt`,
or an uncaught exception alike. It is idempotent, so calling it yourself
afterwards is harmless.

Each teardown step is isolated: scene cleanup, render-graph release and window
close each run even if an earlier one raised, and a failure is logged rather
than swallowed. The log manager is shut down last, since everything above
reports through it.

## Bootstrapping

`bootstrap.py` is the **composition root**: every service is registered and
wired before the game starts.

```python
from pyguara.application.bootstrap import create_application

app = create_application()
app.run(MyScene("game", dispatcher))
```

| Entry point | Backend |
| --- | --- |
| `create_application()` | The configured backend — pygame or ModernGL |
| `create_sandbox_application()` | Same, plus the developer tool overlays |
| `create_headless_application()` | No SDL video at all; for tests |
| `create_headless_sandbox_application()` | Headless, plus tools |

The headless entry points are **test-only**. They swap the
window/renderer/UI-renderer/texture-factory quartet for no-op equivalents so
the suite can boot a real `Application` without a display; everything else
wires up identically.

## Configuration

Configuration is managed by `ConfigManager` (`pyguara/config`) — see
**[Configuration](configuration.md)** for the full reference. In brief:
- **Loading/Saving**: JSON serialization.
- **Validation**: Rules checking (e.g., "Screen width must be > 640").
- **Events**: Dispatches `OnConfigurationChanged` when settings are modified.

---

# Error Handling

Subsystems that run user-supplied callbacks share one policy for what happens
when that code raises, defined in `pyguara.errors`:

```python
from pyguara.errors import ErrorHandlingStrategy

EventDispatcher(error_strategy=ErrorHandlingStrategy.LOG)
DIContainer(error_strategy=ErrorHandlingStrategy.LOG)
```

- **`RAISE`** (default): log, then re-raise. Fail fast during development.
- **`LOG`**: log and carry on. Graceful degradation in production.
- **`IGNORE`**: swallow silently. Tests and narrow edge cases only.

`EventDispatcher` applies this to both handlers and their filters;
`DIContainer` applies it to constructor introspection failures.
