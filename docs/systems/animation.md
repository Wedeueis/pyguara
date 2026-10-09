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

The two endpoints must have the **same shape**, and `current_value` comes back
as **the type that went in**:

| Endpoints | `current_value` |
| --- | --- |
| two numbers | `float` |
| two `Vector2` | `Vector2` |
| two `Color` | `Color`, channels rounded and clamped |
| two equal-length tuples | `tuple` |
| two equal-length lists | `list` |

That the type survives matters because the usual destination is an attribute:
writing a plain tuple to `transform.position` is a bug that surfaces as an
`AttributeError` several frames later, nowhere near the tween.

`Color` tweening is first-class — hit-flash white, poison tint, corpse fade —
and overshooting easings are safe, because `Color`'s own constructor clamps.

A mismatched or unsupported endpoint raises **at construction**, not
mid-playback: a tween is usually built a long way from where it is ticked, and
a shape error reported at tick time names a frame rather than a call site.

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
`manager.update(dt)` from a system or scene you own. For tweening an *entity's*
properties, reach for [`tween_property()`](#tweening-entity-properties)
instead; that path is ticked for you. Two `Tween` instances are
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

## Tweening entity properties

```python
from pyguara.animation import tween_property

tween_property(entity, "transform.position", to=target,
               duration=0.3, easing=EasingType.EASE_OUT_QUAD)
```

That is the whole of it. `TweenSystem` is registered on every scene's
`SystemManager` (priority **120**), so the value is written every tick and the
binding is dropped when it finishes.

Before this, tweening one property was about forty lines per effect: hold a
reference, own a `TweenManager`, tick it in a system you wrote, read
`current_value`, write it back.

### Paths

The first segment names a component the way `entity.transform` does; the rest
walk attributes from there.

```python
tween_property(entity, "transform.position", to=Vector2(100, 0), duration=0.4)
tween_property(entity, "sprite.color", to=Color(255, 0, 0), duration=0.1)
tween_property(entity, "transform.rotation", to=3.14, duration=1.0)
```

The write **replaces** the final attribute rather than mutating it, which is
the only approach that works for a value type: `Vector2` wraps an immutable
`pymunk.Vec2d`, and `Color`'s channels are clamped on construction.

A path that does not resolve raises `PropertyPathError` **at the call**, not
later. A tween that quietly does nothing is worse to debug than one that
refuses to start.

### What a second tween does

The start point is read from the property itself, so a call interrupting an
earlier tween of the same path begins from wherever it had got to — which is
what makes a knockback retargeted mid-flight look continuous rather than
snapping back.

By default a new tween **replaces** any tween already running on that exact
path. Two tweens writing one property every frame is never what anyone wanted:
the last writer wins and the result depends on binding order. Pass
`replace=False` if you really mean both.

```python
stop_property(entity, "transform.position")   # leaves the value where it got to
stop_tweens(entity)                           # everything on this entity
```

### Why a scene system, not a global manager

An app-wide `TweenManager` outlives the scene whose entities it animates, and
goes on writing to components of entities that no longer exist. That is the
same leak #55 fixed for coroutines. A scene-owned system cannot have it: the
scene's `SystemManager.cleanup()` takes the tweens with it.

Priority 120 puts it **first** in the engine band, before steering, AI and the
scene's own update — otherwise every reader is one frame behind the animation
it can see on screen.

## Timelines

Chaining through nested `on_complete` callbacks stops being readable past two
steps, and cannot express "these two at once, then that one" at all. Combat
juice is naturally a timeline.

```python
from pyguara.animation import Timeline

(Timeline()
    .then(wind_up)
    .wait(0.05)
    .call(spawn_hitbox)
    .parallel(knockback, screen_shake)
    .then(recover)
    .start())
```

A `Timeline` ticks with the same `update(dt) -> bool` contract a `Tween` has
(the `Animatable` protocol), so a `TweenManager` holds either without knowing
which, and **a timeline can be a step inside another timeline**.

| Method | Does |
| --- | --- |
| `then(animatable)` | Run it, then continue |
| `wait(seconds)` | Pause |
| `call(fn)` | Call it, in order with the steps around it |
| `parallel(*animatables)` | Run them together; finish with the slowest |

`loops` follows `Tween.loops`: `0` once, `-1` forever, `N` extra repeats.
`on_complete` fires once, after the last loop. `stop()` halts **every** step,
so an interrupted parallel group does not leave its members running, and does
not fire `on_complete`.

Two timing rules:

- **Leftover time carries into the next step, in the same call.** Five 1 ms
  steps would otherwise take one frame each — 83 ms at 60 Hz for 5 ms of
  animation.
- **A step that takes no time runs in the same call too**, so
  `then(tween).call(spawn_hitbox)` does not fire the callback a frame after the
  tween it belongs to. At most one full pass over the steps happens per call,
  so a looping timeline of nothing but callbacks misbehaves rather than hanging
  the frame.

An empty timeline is **complete**, not stuck: a game building one from a
filtered list of effects should not hang when the filter matches nothing.

## Sprite animation

A **clip** is an ordered list of textures plus a frame rate. An **`Animator`**
plays one clip at a time and writes the current frame onto a `Sprite`.

`Animator` is a data-only component &mdash; the clip table and the playback
cursor &mdash; so the behaviour that moves that cursor is free functions
beside it, the same split `Transform`/`set_parent` and `Health`/`apply_damage`
use. Import them from the same module.

```python
from pyguara.graphics.components.animation import (
    AnimationClip,
    Animator,
    add_clip,
    play_clip,
)

animator = Animator(sprite)
add_clip(animator, AnimationClip("run", run_frames, frame_rate=12.0, loop=True))
add_clip(animator, AnimationClip("hit", hit_frames, frame_rate=20.0, loop=False))

play_clip(animator, "run")             # no-op if "run" is already playing
play_clip(animator, "run", force_reset=True)  # restart from frame 0
```

`AnimationClip` rejects an empty frame list or a non-positive `frame_rate` at
construction. `advance_animator(animator, dt)` catches up **every** whole frame
the `dt` covers, so a lag spike or a host slower than the clip's `frame_rate`
does not drop frames or drift behind. A non-looping clip stops on its last
frame; `is_finished` then reports `True` (and `is_playing` `False`).
`play_clip()` with an unknown clip name logs a warning and does nothing.

### Playback modes

`loop` could only say "start over" or "stop". `mode` says more:

| `PlaybackMode` | At the last frame |
| --- | --- |
| `ONCE` | Stop there |
| `LOOP` | Back to frame 0 |
| `PING_PONG` | Play backwards, then forwards again |
| `LOOP_TIMES` | Loop `loop_count` times, then stop |

`PING_PONG` is what an idle bob or a breathing loop wants: the hard cut back to
frame 0 is visible as a hitch. It walks frame by frame rather than computing
the destination, so a lag spike still fires **every** frame event it crossed,
including the turn at the far end.

`loop` remains the serialized form and `mode` is derived from it when nothing
set one, so an existing clip or prefab file keeps working. Setting both
inconsistently resolves in `mode`'s favour — it is the more specific statement.

### Playback speed

```python
animator.playback_speed = 2.0    # haste
animator.playback_speed = 0.0    # hitstop
```

A multiplier over the clip's own `frame_rate`, so a haste or slow buff is one
field rather than a faster copy of every clip. **Zero holds the cursor without
clearing `is_playing`**, which is what a hitstop wants: the animation resumes
where it was instead of restarting. A negative speed holds too — running a clip
backwards is `PING_PONG`'s business, and a negative multiplier is far more
likely a sign flip in a buff calculation.

### Building clips from a sheet

```python
sheet = SpriteSheet("assets/hero.png", texture_factory)
walk = sheet.clip("walk_down", 32, 32, row=1, count=8, fps=12.0)
```

`slice_grid()` returns a flat row-major list, so building a clip meant slicing
`frames[8:16]` by hand — the one place a sheet's layout leaked into game code.
A **row**, not an arbitrary span, because that is how sheets are laid out: one
action per row. A row past the end, or a `count` larger than the row, raises:
a clip quietly short of frames animates wrongly rather than visibly failing.

`frame_events` indices are relative to the **clip**, not to the sheet.

### State machine

`AnimationStateMachine` sits on top of an `Animator`: one **state** per clip,
with transitions between them.

```python
from pyguara.graphics.components.animation import (
    AnimationState,
    AnimationStateMachine,
    AnimationTransition,
    TransitionCondition,
    add_state,
    set_default_state,
    transition_to,
)

fsm = AnimationStateMachine(sprite, animator)
add_state(fsm, AnimationState("idle", idle_clip))
add_state(
    fsm,
    AnimationState(
        "attack",
        attack_clip,
        transitions=[
            AnimationTransition(
                "attack", "idle", TransitionCondition.ANIMATION_END
            )
        ],
        on_complete=lambda: print("attack done"),
    ),
)
set_default_state(fsm, "idle")   # enters the state and starts its clip

transition_to(fsm, "attack")     # manual switch; returns False if already there
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
calls `advance_state_machine()` on every `AnimationStateMachine`, then
`advance_animator()` on every standalone `Animator` whose entity does **not**
also have a state machine (the machine drives its own animator). You do not
call it, and you should not advance animators a second time from scene code.

## Directional animation (kit)

Every game this engine targets is top-down, and every top-down character has
N actions × 4 or 8 facings. `pyguara.kits.topdown_movement` carries that:

```python
from pyguara.kits.topdown_movement import (
    DirectionalAnimator, DirectionalClipSet, DirectionalAnimationSystem,
)

clips = DirectionalClipSet(actions=("idle", "walk", "attack"), ways=8)
for name in clips.every_clip_name():
    add_clip(animator, sheet.clip(name, 32, 32, row=rows[name]))

entity.add_component(DirectionalAnimator(clips, action="walk"))
scene.system_manager.register(DirectionalAnimationSystem(em), priority=500)
```

Names follow the usual convention (`"walk_down"`, `"attack_up_left"`), so a
game lists only the exceptions in `overrides`. A **4-way** set maps a diagonal
onto its *left/right* cardinal rather than up/down: a profile view reads as a
three-quarter view far better than a back view does.

`facing_from_vector(v, ways=8)` is the piece everyone writes by hand, with the
two details everyone gets wrong first:

- **Screen Y grows downward**, so a negative Y is *up*.
- **A zero vector returns `None`, not a default.** A stopped character must
  keep facing where it last faced; snapping to `DOWN` on every halt is the
  other classic bug — which is why `DirectionalAnimator.facing` is stored
  rather than recomputed.

The system reads velocity from `TopDownBody` when there is one, and otherwise
from how far the `Transform` moved since the last tick, so a character driven
by a tween, a pathfinder or a script still faces the right way. It asks for the
clip every frame and relies on `play_clip()` ignoring a re-request for the clip
already playing, so walking in a straight line does not restart the cycle sixty
times a second.

The **action** is the game's business; the system only ever changes the facing.

A kit rather than core: 8-way facing is a genre's vocabulary, and nothing in
`pyguara.graphics` should know what "down" means.
