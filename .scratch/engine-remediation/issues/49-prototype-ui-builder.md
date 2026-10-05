# Prototype the declarative UI builder API

Type: prototype
Status: resolved
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


## Resolution

**Built for production directly, not as a throwaway prototype.** The dev's
call, taken when this was picked up: skip the prototype-and-judge step and
implement the real thing, treating the sketched context-manager syntax as
settled.

`pyguara/ui/builder.py` -- `UIBuilder`, exported from `pyguara.ui`, with
`docs/systems/ui-builder.md`. The syntax is the one this ticket sketched,
unchanged:

```python
with UIBuilder(ui_manager) as ui:
    with ui.box(Vector2(270, 288), Vector2(260, 220), spacing=14) as column:
        ui.label("Main Menu", font_size=44)
        ui.button("Start Game", on_click=self.start)
```

Inherited from ticket 39 and not revisited: opt-in sugar coexisting with the
imperative API (no demo migrated), `on_click` as pure passthrough, no theme
wiring.

What building it for real added beyond the sketch:

- **Custom widgets as the design centre.** The sketch names only
  `box_container`/`label`/`button`, but no demo screen is built from stock
  components -- `guara_falcao` uses `BevelPanel`, `BevelButton` and `Scrim`.
  `add()` and `nest()` take any `UIElement` subclass, keep its concrete type
  for the caller, and leave its own constructor arguments alone. The stock
  factories sit on top of that rather than in front of it.
- **Roots, layers and mounting.** `guara_falcao`'s title screen spans
  `UILayer.BACKDROP` and `UILayer.CONTENT`, so `layer()` scopes the layer
  roots mount at. A block that raises mounts nothing.
- **A container attaches when its factory is called**, not on `__enter__`,
  so `ui.panel(...)` without a `with` adds a childless panel rather than
  silently adding nothing. The first implementation was a
  `@contextmanager`, which made the tree depend on when the garbage
  collector ran an unbalanced generator's `finally`; a test passed because
  of it, which is how it was found.
- **`UIBuilderError`** for use before/after the block, reuse, `mount()` with
  no manager, and re-attaching an owned element.

Verified by structural tree comparison rather than by eye: the same screen
built both ways, laid out, compares equal -- including one built from the
real design-system widgets across two layers, with identical handler objects
and `skin=` preserved. 41 tests.

No follow-up task ticket is spun: the thing this ticket would have
recommended building is what landed.
