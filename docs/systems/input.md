# Input System

`pyguara.input` is the translation layer between hardware (keyboard, mouse,
gamepad) and the **semantic actions** your game logic reacts to. Game code
listens for `"jump"`, never for a key code, so the same logic survives
rebinding and works across devices.

## Pipeline

1. **Backend** (`IInputBackend`) — abstracts the joystick subsystem so the
   manager can run headless in tests. `PygameInputBackend` is the shipped one.
2. **Raw events** — `InputManager.process_event()` ingests pygame keyboard and
   mouse events; `InputManager.update()` polls gamepad state once per frame.
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
| `OnActionEvent` | `action_name`, `context`, `value` |
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
read from the pygame event queue.

```python
from pyguara.input import GamepadAxis, GamepadButton

pad = input_manager.gamepad
if pad.get_button(0, GamepadButton.A):
    ...
move_x = pad.get_axis(0, GamepadAxis.LEFT_STICK_X)
pad.rumble(0, low_frequency=0.4, high_frequency=0.4, duration_ms=200)
```

`controller_id` is a **stable slot number** ("player 1" is `0`). It is pinned
to one physical device by SDL instance id for as long as that device is
plugged in, so unplugging one controller never renumbers the others. A slot is
freed on disconnect and reused by the next controller to connect.
`GamepadConfig` (constructor argument) tunes `deadzone`, `trigger_deadzone`,
`axis_sensitivity` and `vibration_enabled`.

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
