# Decide how dev tools should consume input instead of raw pygame events

Type: grilling
Status: open
Blocked by: —
Audit ref: external code review, verified against the codebase 2026-09-05

## Question

An external code review flagged `TransformGizmo.process_event()` (`pyguara/tools/
gizmos.py`) and `EntityInspector.process_event()` (`pyguara/tools/inspector.py`) for
directly checking `pygame.KEYDOWN`/`pygame.K_q`/`K_w`/`K_e`/`K_ESCAPE`/`K_TAB`.
`ToolManager.process_event()` (`pyguara/tools/manager.py`) does the same for
`pygame.K_F12`. Verified true, verbatim.

This is not simply "pygame constants appear in the engine" — `InputManager.
process_event()` (`pyguara/input/manager.py`) also reads raw pygame constants
directly, but that's the single, deliberate translation boundary from OS events to the
engine's `Action`/`IInputBackend` API. The actual problem: the dev tools implement
their *own*, second, parallel raw-pygame-event parser instead of consuming
`InputManager`'s already-translated output, duplicating the translation logic in two
places. `SandboxApplication._process_input()` (or equivalent) feeds every raw event to
`ToolManager.process_event()` *before* `InputManager.process_event()` ever sees it —
so today, this parallel parser runs first, ahead of the abstracted path.

Nothing in the engine currently has a non-pygame window/event source (both the pygame
and ModernGL backends still window and pump events through pygame — `PygameWindow`/
`PygameGLWindow`), so nothing is actually broken today. The risk is latent: a future
non-pygame-windowed backend, or simply the ongoing cost of keeping two raw-event
parsers in sync as input handling evolves.

- Should dev tools consume `InputManager`'s abstracted `Action` API (binding editor
  shortcuts as registered `Action`s, same as game input), or does `InputManager` need a
  *different* surface for tools specifically (e.g. a raw-key subscription API separate
  from gameplay `Action` bindings, since "toggle the inspector" isn't really a game
  action)?
- `ToolManager`/tools currently intercept events *before* `InputManager` sees them
  (so a tool can consume a click before it reaches the game). If tools stop reading
  raw events and instead subscribe to `InputManager`'s translated output, does that
  ordering guarantee survive, or does consuming-before-game-input need a different
  mechanism entirely?
- Is this worth doing now given nothing is currently broken (both backends share the
  same pygame-based windowing/event pump), or does it wait until a real non-pygame
  backend is on the roadmap?
