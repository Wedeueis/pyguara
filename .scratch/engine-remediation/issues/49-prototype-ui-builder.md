# Prototype the declarative UI builder API

Type: prototype
Status: open
Blocked by: —
Audit ref: follows from Decide on a declarative builder API for UI hierarchies,
ticket 39 — architecture settled there, syntax deferred to this prototype pass

## Question

*Decide on a declarative builder API for UI hierarchies* settled the architecture:
opt-in sugar coexisting alongside today's imperative API (not a replacement),
`on_click` callbacks pass straight through as the same bare-attribute assignment
every demo already does, and theming needs no wiring (`UIElement.__init__` already
calls `get_theme()` unconditionally). What's left is purely ergonomic: **does a
context-manager-based builder actually feel good to use**, which is a question about
an interface that doesn't exist yet, not a fact the codebase can answer by itself.

Build a rough, working `UIBuilder` (context-manager-based, per the original audit's
sketch:
```python
with UIBuilder(renderer) as ui:
    with ui.box_container(direction=VERTICAL, alignment=CENTER):
        ui.label("Main Menu")
        ui.button("Start Game", on_click=self.start)
        ui.button("Quit", on_click=self.quit)
```
) and use it to reconstruct one real demo screen — `TitleScene` (from
`games/guara_falcao/scenes.py` or `games/true_coral/scenes.py`, whichever has the
simpler title/subtitle/button-container layout) is a good candidate since it's small
and already uses exactly the element types (`Label`, `BoxContainer`, `Button`) the
sketch names.

## Done when

- A working `UIBuilder` context manager exists (rough is fine — doesn't need every
  `UIElement` type covered, just enough to reconstruct the chosen demo screen:
  `box_container`, `label`, `button` at minimum).
- The chosen demo's title screen is reconstructed using the builder, side by side
  with its current imperative construction, so both can be compared directly.
- A judgment call recorded on whether the syntax is worth adopting as-is, needs
  changes (and what, specifically), or isn't worth pursuing further — this
  prototype's outcome is itself the answer to "how should it feel," not a rubber
  stamp that it should be built for real.
- If judged worth pursuing: spins a task ticket to build the real thing (informed by
  what the prototype got wrong) rather than promoting the prototype's rough code
  directly into the engine.
