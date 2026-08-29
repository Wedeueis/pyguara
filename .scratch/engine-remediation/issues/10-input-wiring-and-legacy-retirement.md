# Input wiring and legacy retirement

Type: grilling
Status: open
Blocked by: —
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
