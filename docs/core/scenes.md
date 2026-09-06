# Scenes

A scene is one self-contained slice of the game: a level, a menu, a cutscene.
`SceneManager` decides which scenes are live, which receive updates, and which
get drawn.

## A scene owns its world

Each `Scene` has its **own** `EntityManager` and `SystemManager`. There is no
global one. A pause menu pushed over a level therefore cannot see or disturb
the level's entities.

`resolve_dependencies()` builds the rest — camera, render system, prefab
factory, and the four engine systems (Steering, AI, AudioSource, Animation) —
before `on_enter()` ever runs.

```python
class Level(Scene):
    def on_enter(self) -> None:
        player = self.entity_manager.create_entity()
        player.add_component(Transform(position=Vector2(100, 100)))

    def update(self, dt: float) -> None:
        ...                      # display rate: animation, camera

    def fixed_update(self, fixed_dt: float) -> None:
        ...                      # fixed rate: physics, AI
```

Only `on_enter`, `on_exit` and `update` are abstract. `fixed_update`,
`on_pause`, `on_resume` and `render` have working defaults.

## Registering

```python
manager.register(Level("level_1", dispatcher))
```

Registration order and container availability do not matter: a scene
registered before the DI container arrives is wired when it does. Registering
a second scene under a name already in use replaces it and logs a warning,
since the displaced scene becomes unreachable.

## Switching versus stacking

Two ways to change what is active, with different lifetimes:

```python
manager.switch_to("menu")            # replace everything
manager.push_scene("pause")          # overlay, keeping what is beneath alive
manager.pop_scene()                  # return to what is beneath
```

**`switch_to()` tears down the entire stack.** Every scene currently live is
exited, LIFO — the current one first, then the stack top-down — before the new
scene is entered. Nothing survives a switch.

**`push_scene()` keeps the scene beneath alive.** It is paused, not exited, and
`pop_scene()` resumes it. This is the pause-menu, dialog and inventory shape.

### `pause_below`

```python
manager.push_scene("pause", pause_below=True)    # default: freeze what's under
manager.push_scene("dialog", pause_below=False)  # let it keep running
```

`pause_below` controls **updates only**. Scenes beneath are always still
rendered, which is what makes a pause menu show the frozen game behind it.

The rule composes down a deep stack: the walk starts at the current scene and
stops at the first `pause_below=True` it meets, so an inventory over a
non-pausing dialog over a level updates all three, while one pausing layer
freezes everything below it.

## Transitions

```python
from pyguara.scene.transitions import FadeTransition

manager.switch_to("menu", FadeTransition())
```

A transition defers the lifecycle hooks so the outgoing scene is still alive
to be rendered while it fades: the outgoing scene exits when it is fully
hidden, and the incoming one enters when it becomes visible.

!!! warning "One at a time"
    A `switch_to()`, `push_scene()` or `pop_scene()` requested while a
    transition is running is **ignored and logged**. Letting a second request
    through replaced the pending scene, so the first target was skipped
    without ever receiving `on_enter()` while its predecessor had already been
    exited.

    Check `manager.is_transitioning()` before changing the stack, or drive
    changes from a transition's completion.

While a transition runs, `update()` and `fixed_update()` are skipped entirely —
the world is frozen for its duration.

## The frame

`SceneManager.fixed_update()` runs at the fixed rate and, per active scene:

1. snapshots `previous_position` for every `Transform` with `interpolate=True`,
   **before** any system moves it — one central point that every current and
   future position-mutating system runs after;
2. ticks that scene's `SystemManager`;
3. calls the scene's own `fixed_update()`;
4. flushes its `EntityManager`, the frame boundary the ECS lifecycle defers
   index cleanup to.

Active scenes run bottom-to-top, so an overlay sees the state its base already
produced this tick.

`render()` draws the whole stack bottom-to-top and sets `render_alpha` on each
scene first, so `Transform.interpolate` entities are drawn between fixed steps
rather than snapping at the physics rate.

## Shutdown

`cleanup()` exits every live scene exactly once, LIFO — including a scene a
transition has started entering but not yet made current, so an application
shutting down mid-fade does not leave one holding its world.

`Application.shutdown()` calls it for you.

## Rules of thumb

1. `push_scene()` when you intend to come back; `switch_to()` when you do not.
2. Nothing survives `switch_to()` — do not stash state on a scene object
   across one.
3. Check `is_transitioning()` before changing the stack.
4. Deterministic work in `fixed_update()`, visual work in `update()`.
5. Override `on_pause`/`on_resume` for music and timers; the system manager is
   already gated for you.
