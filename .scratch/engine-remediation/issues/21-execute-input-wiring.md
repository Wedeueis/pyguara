# Execute the input wiring and legacy retirement

Type: task
Status: open
Blocked by: —
Audit ref: INPUT-1 (high), follows from Input wiring and legacy retirement, ticket 10

## Question

Nothing to decide — execute the decisions recorded in
[Input wiring and legacy retirement](10-input-wiring-and-legacy-retirement.md).

**`pyguara/input/manager.py`:**
- Add `self._gamepad_manager.update()` inside `InputManager.update()` (already there — confirm
  it stays the only line, or grows to include the new bound-action wiring below).
- Delete `self._joysticks`, `_detect_controllers()`, and the constructor's
  `pygame.joystick.init()` / backend `init_joysticks()` fallback call tied to it.
- Delete `_cooldowns` from `__init__`.
- Delete the `JOYBUTTONDOWN`, `JOYBUTTONUP`, `JOYAXISMOTION`, `JOYDEVICEADDED`,
  `JOYDEVICEREMOVED` branches from `process_event()`.
- Wire bound gamepad Actions off `GamepadManager` state: on each `update()`, after
  `self._gamepad_manager.update()` returns, diff current button/axis state against bindings
  (`InputDevice.GAMEPAD` entries in `KeyBindingManager`) and call the existing
  `_handle_input`/`_handle_axis`/`_dispatch_action` machinery — or have `GamepadManager`
  dispatch `GamepadButtonEvent`/`GamepadAxisEvent` and have `InputManager` subscribe to its own
  dispatcher for those and translate them. Pick whichever keeps `_handle_input`'s
  press/release/hold logic and `_handle_axis`'s deadzone-then-analog-only logic intact —
  don't duplicate that logic in `GamepadManager`.
- `input_backend: Optional[IInputBackend] = None` → `input_backend: IInputBackend` (required
  constructor param, no fallback branch).

**`pyguara/input/gamepad.py`:**
- `input_backend: Optional["IInputBackend"] = None` → `input_backend: "IInputBackend"`
  (required); delete the `pygame.joystick.get_init()`/`.init()` direct-call fallback branches
  in `__init__`, `_scan_devices()`, and `shutdown()`.

**`pyguara/input/types.py`:**
- Delete `InputAction.cooldown`.

**`pyguara/application/application.py`:**
- Call `self._input_manager.update()` once per frame in `run()`, before `_process_input()`.

**`pyguara/application/bootstrap.py`:**
- Register `PygameInputBackend` (`pyguara/input/backends/pygame_backend.py`) as the DI-supplied
  `IInputBackend` singleton, so `InputManager`'s (now-required) constructor param resolves via
  auto-wiring.

**Tests:**
- `tests/test_input.py` — the mock-backend gamepad tests already model the target shape; update
  any test that currently relies on `self._joysticks`/`_detect_controllers` or the pygame
  fallback path to construct with an explicit mock `IInputBackend` instead.
- Add a regression test that binds a `GAMEPAD` device action, drives it through a mock
  `IInputBackend`/`IJoystick`, calls `InputManager.update()`, and asserts the bound `Action`
  fires — proving the new path (GamepadManager state → bound Action dispatch) actually works,
  not just that `GamepadManager` itself updates.
- Confirm no test still exercises the deleted `JOYBUTTONDOWN`/`JOYAXISMOTION`/etc. branches or
  the deleted legacy `_joysticks` dict.

## Done when

- `InputManager.update()` is called once per frame from `Application.run()`, before
  `_process_input()`.
- `process_event()` no longer branches on any `JOY*` pygame event type.
- `self._joysticks`, `_detect_controllers()`, `_cooldowns`, and `InputAction.cooldown` are gone
  from the codebase, not merely unused.
- A bound gamepad Action fires from `GamepadManager`'s polled state, proven by a regression test
  using a mock `IInputBackend` — no hardware, no real pygame joystick subsystem required.
- `IInputBackend` is a required constructor parameter on both `InputManager` and
  `GamepadManager`; `bootstrap.py` registers `PygameInputBackend` in DI so production wiring
  still resolves automatically.
- `protocolo_bandeira` and `true_coral`'s own cooldown fields/logic are untouched.
- Full suite green, `ruff check .` and `mypy pyguara` clean.
