# Scripting System

`pyguara.scripting` runs **coroutines** — Python generator functions that
`yield` control back to the engine — so sequential, time-based game logic can
be written as a straight-line function instead of a state machine or a chain
of callbacks. The model is close to Unity's coroutines.

## Wiring

The bootstrap registers a single `CoroutineManager` as a DI singleton, and
`Application` ticks it once per frame from `_update()` — the **variable-rate**
step, alongside UI and tweens, so sequences look smooth rather than being
frame-reproducible. Reach it from a scene through the container:

```python
from pyguara.scripting import CoroutineManager

class MyScene(Scene):
    def on_enter(self) -> None:
        self._coroutines = self.container.get(CoroutineManager)
        self._coroutines.start_coroutine(self.intro())

    def intro(self):
        yield from ...  # see below
```

Because the manager is app-wide, coroutines are **not** stopped when a scene
exits. A sequence that outlives its scene keeps ticking against entities that
may no longer exist — keep the `Coroutine` handles a scene starts and
`stop_coroutine()` them in `on_exit()`, or call `stop_all()` if the manager is
effectively scene-private.

## Wait instructions

A coroutine controls its own timing by yielding a `WaitInstruction`:

| Yield | Resumes when |
| --- | --- |
| `WaitForSeconds(seconds)` | that much game time has elapsed |
| `WaitUntil(predicate)` | `predicate()` first returns truthy |
| `WaitWhile(predicate)` | `predicate()` first returns falsy |
| `None` (a bare `yield`) | next frame |
| another `Coroutine`, or a generator | that sub-sequence has finished |

Convenience factories `wait_for_seconds()`, `wait_until()` and `wait_while()`
return the matching instruction.

```python
from pyguara.scripting import wait_for_seconds, wait_until

def wave_sequence(spawner, enemies):
    print("wave starting")
    yield wait_for_seconds(2.0)

    spawner.spawn_wave()
    yield wait_until(lambda: len(enemies) == 0)

    print("wave cleared")
```

### Nested sequences

Yielding another coroutine or a raw generator suspends the parent until the
child completes, then resumes the parent in the same frame:

```python
def cutscene():
    yield pan_camera_to(boss)          # a generator function call
    yield wait_for_seconds(0.5)
    yield boss_intro_lines()           # another one
    hud.show()
```

`WaitForSeconds` timing is frame-granular: the frame that yields the
instruction is not counted, and time elapsed past the duration is not carried
into the next wait, so a long chain of short waits drifts by up to a frame
each. Use `WaitUntil` against a clock you own if a sequence must hit a wall
time exactly.

## Managing coroutines

`CoroutineManager`:

- `start_coroutine(generator) -> Coroutine` — begins running it next
  `update()`; the returned handle is what you stop.
- `stop_coroutine(coroutine) -> bool` — stops and drops one; `False` if it
  was already gone (a finished coroutine removes itself).
- `stop_all()` — stops and drops every coroutine.
- `active_count` / `active_coroutines` (a copy) — introspection.

Stopping a coroutine **closes its generator**, so `finally` blocks and
`with` statements inside the sequence run their cleanup immediately rather
than whenever the generator is garbage-collected:

```python
def show_dialogue(box):
    box.open()
    try:
        yield wait_until(box.dismissed)
    finally:
        box.close()          # runs even if the coroutine is stopped early
```

Coroutines may call `start_coroutine()`, `stop_coroutine()` and `stop_all()`
from inside their own body during `update()` — including stopping
themselves. The pass iterates a snapshot: a coroutine stopped mid-frame is
skipped, one started mid-frame is carried forward and first runs next frame,
and no sibling is skipped by the mutation. (A coroutine that stops *itself*
from inside its body cannot have its generator closed at that instant; its
`finally` blocks then run at GC.)

## Errors

What happens when a coroutine body raises is governed by the manager's
`error_strategy` (`pyguara.errors.ErrorHandlingStrategy`), the same knob
`EventDispatcher` and `DIContainer` use:

| Strategy | Behaviour |
| --- | --- |
| `RAISE` (default) | log the traceback, stop the offender, re-raise |
| `LOG` | log the traceback, stop the offender, carry on |
| `IGNORE` | stop the offender silently |

Under every strategy the failing coroutine is stopped and removed, and the
other coroutines still run that frame — one bad sequence cannot strand the
rest or corrupt the manager's list. An exception inside a nested sequence is
handled the same way at the top-level coroutine.

```python
from pyguara.errors import ErrorHandlingStrategy
from pyguara.scripting import CoroutineManager

manager = CoroutineManager(error_strategy=ErrorHandlingStrategy.LOG)
```
