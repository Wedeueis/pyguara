# Input System

`pyguara.input` is the translation layer between hardware (keyboard, mouse,
gamepad) and the **semantic actions** your game logic reacts to. Game code
listens for `"jump"`, never for a key code, so the same logic survives
rebinding and works across devices.

## Pipeline

1. **Backend** (`IInputBackend`) — abstracts the joystick subsystem so the
   manager can run headless in tests. The bootstrap picks the one that
   matches the renderer: `NativeInputBackend` (gamepads through gilrs) on
   wgpu, the default, `PygameInputBackend` on pygame, and
   `NullInputBackend`, which has no devices, on the headless application.
2. **Raw events** — `InputManager.process_event()` ingests the engine's own
   keyboard, mouse and text events, which the window backend (winit on
   wgpu, SDL on pygame) has already translated;
   `InputManager.update()` polls gamepad state once per frame.
3. **Binding lookup** — `KeyBindingManager` maps `(device, code)` in the active
   *context* to action names.
4. **Action dispatch** — an `OnActionEvent` is published for game logic;
   `OnRawKeyEvent` / `OnMouseEvent` are published in parallel for the UI layer.

`InputManager` is registered as a singleton by the application bootstrap, so a
scene resolves it from the container:

```python
from pyguara.input import ActionType, InputDevice, InputManager
from pyguara.input.keys import SPACE

input_manager = container.get(InputManager)
input_manager.register_action("jump", ActionType.PRESS)
input_manager.bind_input(InputDevice.KEYBOARD, SPACE, "jump")
```

Use the constants in `pyguara.input.keys` (`SPACE`, `A`, `LEFT`, `F1`, …), not
`pygame` constants — game code never imports the backend.

## Actions

`register_action(name, action_type, deadzone=0.1)` defines what an action *is*:

| `ActionType` | Fires when |
| --- | --- |
| `PRESS` | the input goes down |
| `RELEASE` | the input comes up |
| `HOLD` | the input goes down *and* when it comes up (value `1.0` then `0.0`) |
| `ANALOG` | a bound gamepad axis moves (value is the post-deadzone axis position) |

An `ANALOG` action only responds to a bound **axis**; a digital key bound to
one produces nothing. Likewise a `PRESS`/`RELEASE`/`HOLD` action bound to an
axis does nothing — axes drive `ANALOG` only.

## Buffering and held time

Input has its own clock. `Application` moves it on once a frame by the
frame's real duration, not scaled by `time_scale`, and by each recorded
duration during a replay, so everything below replays on the same frame.
`input_manager.time` reads it; code running an `InputManager` without
`Application` calls `advance(seconds)` itself.

```python
# Pressed jump up to 100 ms before landing still jumps, once.
if body.on_ground and input_manager.consume_press("jump", 0.1):
    body.jump()

# Charge for as long as attack is held.
charge = min(input_manager.held_for("attack") / 1.5, 1.0)
```

| Method | Answers |
| --- | --- |
| `was_pressed_within(action, seconds, player=0)` | whether the action was pressed, or a gesture of that name made, that recently |
| `consume_press(action, seconds, player=0)` | the same, and takes the press so it is not answered again |
| `is_held(action, player=0)` | whether any key or button holds it down |
| `held_for(action, player=0)` | how long it has been held, 0 while up |

These track every registered action whatever its `ActionType`, and per
player when a `PlayerRouter` is in use. An action bound to two keys is held
until both are up. A release lets go of what its key pressed even after
the context has changed, and an unplugged pad lets go of everything it held.
`reset_timing()` forgets all of it; a replay calls it as it starts and when
it rewinds.

## Gestures

A gesture is made from actions, so it follows rebinding and every device
bound to them. When one is made, an `OnActionEvent` under its name is
dispatched for that player, and it is buffered like a press.

```python
from pyguara.input import ActionSequence, Chord, DoubleTap, Hold, Tap

input_manager.add_gesture(Hold("charge", "attack", seconds=0.5))
input_manager.add_gesture(Tap("jab", "attack", max_seconds=0.2))
input_manager.add_gesture(DoubleTap("dash", "right", window=0.3))
input_manager.add_gesture(Chord("special", ("attack", "jump"), window=0.1))
input_manager.add_gesture(ActionSequence("slam", ("down", "down", "attack")))
```

| Gesture | Made when |
| --- | --- |
| `Hold` | the action has been held for `seconds`; once per press |
| `Tap` | the action is released within `max_seconds` of its press |
| `DoubleTap` | the action is pressed again within `window`; a third press starts a new pair |
| `Chord` | every action is down, all pressed within `window` of one another, in any order |
| `ActionSequence` | the actions are pressed in order, each within `window` of the last; presses of other actions are ignored |

The actions a gesture watches must be registered first, and its name must
not be a registered action's. The plain action still fires as well: a
double-tap of `right` is two `right` presses and a `dash`. A gesture never
watches another gesture. `remove_gesture(name)` stops one; `gestures`
lists them.

## Bindings

```python
input_manager.bind_input(InputDevice.KEYBOARD, SPACE, "jump")
input_manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")
```

A key may carry several actions and an action may have several keys. The
manager owns a `KeyBindingManager`; reach it for queries and rebinding through
the rebinding API below.

## Contexts

A **context** is the current input mode. Only bindings registered for the
active context resolve, so one key drives different actions in gameplay and in
menus:

```python
from pyguara.input import InputContext
from pyguara.input.keys import RETURN

input_manager.bind_input(InputDevice.KEYBOARD, SPACE, "jump", InputContext.GAMEPLAY)
input_manager.bind_input(InputDevice.KEYBOARD, RETURN, "confirm", InputContext.MENU)

input_manager.context = InputContext.MENU        # property
input_manager.set_context(InputContext.GAMEPLAY) # imperative alias
```

The manager starts in `InputContext.GAMEPLAY`. Contexts are
`GAMEPLAY`, `UI`, `MENU`, `DEBUG`. Changing to a different context publishes an
`InputContextChangedEvent` (`old_context`, `new_context`); setting the context
it already holds is a no-op and publishes nothing. A binding registered for a
context that is never made active never fires.

## Events

All input events carry `timestamp` (set at construction) and `source` (the
manager that emitted them).

| Event | Fields |
| --- | --- |
| `OnActionEvent` | `action_name`, `context`, `value`, `player` |
| `OnRawKeyEvent` | `key_code`, `is_down`, `modifiers` |
| `OnMouseEvent` | `position`, `button`, `is_down`, `is_motion` |
| `InputContextChangedEvent` | `old_context`, `new_context` |
| `GamepadButtonEvent` | `controller_id`, `button`, `is_pressed` |
| `GamepadAxisEvent` | `controller_id`, `axis`, `value`, `previous_value` |

```python
def on_action(self, event: OnActionEvent) -> None:
    if event.action_name == "jump" and event.value > 0.5:
        self.player.jump()
```

## Gamepads

`InputManager.update()` drives an owned `GamepadManager` (also reachable as
`input_manager.gamepad`) that polls device state, applies deadzones, and
publishes `GamepadButtonEvent` / `GamepadAxisEvent` on change. Bound
`InputDevice.GAMEPAD` actions are driven off those events; gamepads are not
read from the window's event queue.

```python
from pyguara.input import GamepadAxis, GamepadButton

pad = input_manager.gamepad
if pad.get_button(0, GamepadButton.A):
    ...
move_x = pad.get_axis(0, GamepadAxis.LEFT_STICK_X)
pad.rumble(0, low_frequency=0.4, high_frequency=0.4, duration_ms=200)
```

`controller_id` is a **stable slot number** ("player 1" is `0`). It is pinned
to one physical device by its backend's device id (SDL's on pygame,
gilrs's on wgpu) for as long as that device is
plugged in, so unplugging one controller never renumbers the others. A slot is
freed on disconnect and reused by the next controller to connect.
`GamepadConfig` (constructor argument) tunes `deadzone`, `trigger_deadzone`,
`axis_sensitivity` and `vibration_enabled`.

**A game sees its gamepads only while its window has focus.** On the wgpu
backend pads are read through gilrs, whose Windows backend (Windows.Gaming.Input)
delivers input only to the process that owns the foreground window; pygame's
SDL ignores an unfocused pad by default too, so this is not new. Alt-tabbed
out, buttons read as released and sticks as centred.

This bites a **test script**: one that reads `NativeGamepads` from a console
with no window of its own sees nothing, and on Windows the focused terminal
takes the input instead (Windows Terminal switches tabs on the bumpers). Open
a window and keep it focused while probing a pad.

## Rebinding and persistence

`KeyBindingManager` supports runtime rebinding with conflict handling and
JSON-serializable export:

```python
from pyguara.input import ConflictResolution, KeyBindingManager, RebindResult

bindings: KeyBindingManager = input_manager.bindings
result, conflict = bindings.rebind(
    "jump", InputDevice.KEYBOARD, RETURN, InputContext.GAMEPLAY,
    resolution=ConflictResolution.SWAP,
)
```

| `ConflictResolution` | Behaviour when the target key is taken |
| --- | --- |
| `ERROR` (default) | raises `ValueError` |
| `SWAP` | the two actions trade keys |
| `UNBIND` | the conflicting action loses its binding |
| `ALLOW` | both actions share the key |

`rebind()` returns `(RebindResult, BindingConflict | None)`. `RebindResult` is
`SUCCESS`, `SWAPPED` or `UNBOUND` — there is no `CONFLICT` value, because
`ERROR` raises instead of returning. A `SWAP` of an action that had no prior
binding has no key to trade back and returns `UNBOUND`.

```python
data = bindings.export_bindings()   # dict, ready for json.dump
bindings.import_bindings(data)       # replaces all current bindings
bindings.reset_to_defaults()         # clears every context
```
