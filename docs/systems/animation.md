# Animation

PyGuara's animation code comes in two independent halves:

| Half | Module | Animates |
| --- | --- | --- |
| **Tweening** | `pyguara.animation` | any number or sequence of numbers over time |
| **Sprite animation** | `pyguara.graphics.components.animation` | a `Sprite`'s texture, frame by frame |

They share nothing but the name. Pick whichever fits; a project often uses both.

---

## Tweening

A `Tween` interpolates a value from `start_value` to `end_value` over
`duration` seconds, shaped by an easing function.

```python
from pyguara.animation import Tween, TweenManager, EasingType

tween = Tween(
    start_value=(0.0, 0.0),
    end_value=(100.0, 50.0),
    duration=1.0,
    easing=EasingType.EASE_OUT_QUAD,
)
tween.start()

# every frame:
tween.update(dt)
x, y = tween.current_value
```

### Endpoint types

The two endpoints must have the **same shape**:

* **two numbers** (`int` or `float`) &mdash; `current_value` is a `float`;
* **two equal-length sequences** of numbers (`tuple` or `list`) &mdash;
  `current_value` is a `tuple`.

`Vector2` is a `tuple` subclass, so it tweens &mdash; but you get a plain
`tuple` back, so wrap it if you need the type: `Vector2(*tween.current_value)`.
`Color` and other non-sequence objects are **not** supported; tween their
components, or the packed `(r, g, b, a)` tuple. A mismatched or unsupported
endpoint raises at construction, not mid-playback.

### Lifecycle

| Call | Effect |
| --- | --- |
| `start()` | begin (or restart from the top) |
| `pause()` / `resume()` | freeze / unfreeze; `update()` still returns "alive" |
| `stop()` | reset to `IDLE`; `update()` becomes a no-op until `start()` |
| `update(dt)` | advance; returns `False` once the tween has completed |

Read-only: `current_value`, `progress` (0&ndash;1), `is_playing`, `is_complete`.

### Delay, loops, yoyo

* `delay` &mdash; seconds to wait after `start()` before the first movement.
  Applied once; loop repeats do not re-wait.
* `loops` &mdash; `0` plays once, `-1` loops forever, `N` plays once and then
  repeats `N` more times (`N + 1` playthroughs total).
* `yoyo` &mdash; on each loop, swap the direction instead of snapping back to
  the start, so the value ping-pongs.
* `on_update(value)` fires every frame the tween moves; `on_complete()` fires
  once, only at final completion (never on an intermediate loop, never on an
  infinite loop).

A single `update(dt)` whose `dt` spans several whole loops resolves **one**
loop boundary and carries the remaining time forward, catching up over the
next few frames rather than firing every boundary at once. Clamp `dt` upstream
if a lag spike must not stutter a tween.

### TweenManager

`TweenManager` owns a bag of tweens, ticks them, and drops each one when it
completes.

```python
from pyguara.animation import Tween, TweenManager

manager = TweenManager()
manager.add(tween)   # returns the tween, for chaining
tween.start()

# in your system's update():
manager.update(dt)
```

**Nothing in the engine updates a `TweenManager` for you** &mdash; call
`manager.update(dt)` from a system or scene you own. Two `Tween` instances are
equal only when they are the *same* object, so a manager can hold many
identically configured tweens (five enemies flashing white) without them
aliasing each other. `pause_all()`, `resume_all()`, `stop_all()`, `clear()`,
`tween_count` and `active_tweens` round out the surface. `stop_all()` also
clears; a tween that is `add()`ed but never `start()`ed (or is `stop()`ped)
stays in the bag until you `remove()` or `clear()` it.

### Easing

`pyguara.animation.easing` provides `EasingType` and 31 functions across the
usual families &mdash; quad, cubic, quart, quint, sine, expo, circ, elastic,
back, bounce, each in in / out / in-out. Call one directly, or go through
`ease(t, easing_type)`, which clamps `t` to `[0, 1]` first. Elastic and back
deliberately overshoot outside `[0, 1]`; the rest stay within it.

---

## Sprite animation

A **clip** is an ordered list of textures plus a frame rate. An **`Animator`**
plays one clip at a time and writes the current frame onto a `Sprite`.

```python
from pyguara.graphics.components.animation import AnimationClip, Animator

animator = Animator(sprite)
animator.add_clip(AnimationClip("run", run_frames, frame_rate=12.0, loop=True))
animator.add_clip(AnimationClip("hit", hit_frames, frame_rate=20.0, loop=False))

animator.play("run")             # no-op if "run" is already playing
animator.play("run", force_reset=True)  # restart from frame 0
```

`AnimationClip` rejects an empty frame list or a non-positive `frame_rate` at
construction. `Animator.update(dt)` catches up **every** whole frame the `dt`
covers, so a lag spike or a host slower than the clip's `frame_rate` does not
drop frames or drift behind. A non-looping clip stops on its last frame;
`is_finished` then reports `True` (and `is_playing` `False`). `play()` an
unknown clip name logs a warning and does nothing.

### State machine

`AnimationStateMachine` sits on top of an `Animator`: one **state** per clip,
with transitions between them.

```python
from pyguara.graphics.components.animation import (
    AnimationState,
    AnimationStateMachine,
    AnimationTransition,
    TransitionCondition,
)

fsm = AnimationStateMachine(sprite, animator)
fsm.add_state(AnimationState("idle", idle_clip))
fsm.add_state(
    AnimationState(
        "attack",
        attack_clip,
        transitions=[
            AnimationTransition(
                "attack", "idle", TransitionCondition.ANIMATION_END
            )
        ],
        on_complete=lambda: print("attack done"),
    )
)
fsm.set_default_state("idle")     # enters the state and starts its clip

fsm.transition_to("attack")      # manual switch; returns False if already there
```

* `AnimationState` carries `on_enter`, `on_exit` and `on_complete` callbacks.
  `on_complete` fires **once** when a non-looping clip finishes, not every
  frame it then sits on its last frame; re-entering the state re-arms it.
* `AnimationTransition.condition` is either `ANIMATION_END` (fires once the
  state's clip finishes) or `IMMEDIATE` (fires on the tick after the state is
  entered &mdash; useful for a one-shot intro that hands off to a loop).
  `priority` breaks ties; the highest-priority eligible transition wins, and
  at most one transition fires per update.
* `current_state_name` reports where the machine is.

### AnimationSystem

`AnimationSystem` is registered automatically on every `Scene`'s
`SystemManager` (priority 300) and ticked at the fixed timestep. Each tick it
updates every `AnimationStateMachine`, then every standalone `Animator` whose
entity does **not** also have a state machine (the machine drives its own
animator). You do not call it, and you should not update animators a second
time from scene code.
