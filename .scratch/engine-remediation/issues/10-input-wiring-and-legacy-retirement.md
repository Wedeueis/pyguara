# Input wiring and legacy retirement

Type: grilling
Status: resolved
Blocked by: —
Assignee: Wedeueis Braz
Audit ref: INPUT-1 (high)

## Question

`InputManager.update()` is never called. `Application._process_input()` calls only
`process_event()`. Nothing in the engine or any game calls `update()`, which is the sole
driver of `GamepadManager` — 391 lines handling hot-plug detection, button-state tracking and
deadzone-filtered axis polling. All of it is dead at runtime.

The same class carries a second, older gamepad path (`self._joysticks`,
`input/manager.py:53`) commented "legacy … backwards compatibility" — in a pre-alpha project
with no releases to be backward-compatible with. `self._cooldowns` is initialised and never
read.

## To resolve

- Where does `update()` belong in the loop? Before `poll_events` (so state is fresh for the
  frame) or after (so it reflects this frame's events)? It must be once per frame, not per
  fixed step — and the distinction matters for input buffering.
- Does the legacy `_joysticks` path get deleted, or is there a behaviour in it that
  `GamepadManager` lacks?
- `_cooldowns` — was an action-cooldown feature intended? Implement or remove.
- `InputManager` imports pygame directly and calls `pygame.joystick.init()` when no backend is
  supplied. Does the backend become mandatory?
- Is there a regression test shape that can cover gamepad state without hardware? The
  `IInputBackend` protocol exists precisely for this — is it sufficient?

## Why this is unblocked

The audit is sufficient input for the discussion. Implementing the answer wants a booting
engine (Repair the composition root, Bootstrap smoke test), but deciding it does not — so this
sits on the frontier and can run in parallel with the critical fixes.

## Answer

**Two gamepad paths converge on one: `GamepadManager`.** Today the engine has two
non-integrated gamepad models: raw pygame `JOY*` events routed through `process_event()` into
the action/`KeyBindingManager` system (the only path that currently reaches bound Actions, and
the only one that's live), and `GamepadManager` (391 lines, hot-plug, per-button/axis state,
deadzone, rumble — but `update()` is never called, so it's fully inert; no game references
`.gamepad`). `GamepadManager` becomes the sole gamepad backend:

- `InputManager.update()` calls `self._gamepad_manager.update()`, and `Application` calls
  `input_manager.update()` once per frame, **before** `_process_input()`/`poll_events()` — the
  gamepad state consumed this frame is the state SDL's pump left in place from last frame's
  event drain.
- Bound gamepad Actions fire off `GamepadManager`'s polled, deadzone-filtered state instead of
  raw pygame events. (Wiring detail — e.g. `GamepadManager` firing into
  `InputManager._handle_input`/`_handle_axis`, or `InputManager` diffing gamepad state itself —
  is for the execution ticket, not this decision.)
- `process_event()`'s `JOYBUTTONDOWN`/`JOYBUTTONUP`/`JOYAXISMOTION`/`JOYDEVICEADDED`/
  `JOYDEVICEREMOVED` branches are deleted. This does **not** stop the engine talking to the OS:
  `Application._process_input()` still calls `self._window.poll_events()` every frame,
  unchanged, for keyboard/mouse/quit — and that same SDL event pump is what keeps pygame's
  internal joystick device list current. `GamepadManager` just stops branching on those event
  *types* and reads device/button/axis state directly (`get_joystick_count()`, `get_button()`,
  `get_axis()`) instead.
- The legacy `self._joysticks` dict and `_detect_controllers()` in `InputManager` are deleted
  outright — no behavior in them that `GamepadManager` lacks once it owns hot-plug too.

**`_cooldowns` / `InputAction.cooldown`: removed, not implemented.** These are a different
concept from the games' existing cooldowns (`protocolo_bandeira`'s `attack_cooldown`/
`current_cooldown`, `true_coral`'s `_move_cooldown`), which gate whether a game-state ability
*can act* — game logic, tied to entity/weapon state. `InputAction.cooldown` reads as raw
input-debounce (rate-limiting how often one bound action can re-fire from repeated presses),
orthogonal to ability cooldowns. There's no evidence of a real repeat-input bug motivating it —
it was initialized and never read. Delete both the field and the dict; `protocolo_bandeira` and
`true_coral` keep their own cooldown logic untouched. Revisit only if a concrete input-repeat
problem surfaces.

**`IInputBackend` becomes mandatory.** `bootstrap.py` never registers `IInputBackend` in the DI
container today, so production code silently takes the `Optional[...] = None` pygame-direct
fallback in both `InputManager` and `GamepadManager` — only unit tests exercise the protocol
path, via an explicit mock. Register `PygameInputBackend` as the DI-supplied `IInputBackend` in
`bootstrap.py`; drop the `None`-fallback branches from both constructors. One code path, always
through the protocol.

**Test shape: the protocol is already sufficient, no new infrastructure needed here.**
`tests/test_input.py` already constructs `GamepadManager` with a mock backend and drives
hot-plug/deadzone/multi-controller/state-change coverage without hardware — that pattern
carries over unchanged once `GamepadManager` is the canonical path. Broader headless backend
wiring for the integration suite is separately tracked by
[Wire HeadlessBackend as the integration-suite test backend](19-wire-headless-test-backend.md).

Execution: [Execute the input wiring and legacy retirement](21-execute-input-wiring.md).
