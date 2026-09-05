# Decide on a declarative builder API for UI hierarchies

Type: grilling
Status: open
Blocked by: —
Audit ref: external code review, verified against the codebase 2026-09-05

## Question

An external code review recommended a context-manager-based builder DSL as sugar over
the current imperative UI construction API (`BoxContainer`/`add_child()` in
`pyguara/ui/layout.py`/`pyguara/ui/base.py`):
```python
with UIBuilder(renderer) as ui:
    with ui.box_container(direction=VERTICAL, alignment=CENTER):
        ui.label("Main Menu")
        ui.button("Start Game", on_click=self.start)
        ui.button("Quit", on_click=self.quit)
```
versus today's imperative style (construct each element, call `add_child()` manually).

- Does this fully replace the imperative API, or sit alongside it as opt-in sugar?
  Every current demo (`games/*/scenes.py`) builds UI imperatively today and would need
  to keep working either way.
- How do callbacks (`on_click=self.start`) wire through the builder to the same
  event/action path `UIElement._process_input()` already uses — does the builder just
  become a thin constructor wrapper that still calls today's existing wiring
  underneath, or does it need its own callback-registration mechanism?
- Does the builder need a `Theme`/`UITheme` at construction time, or is theme applied
  after the fact the same as today (`ui/theme.py`'s `get_theme()`/`set_theme()`)?
- Is this substantial enough to warrant a `/prototype` pass — a rough, working builder
  to react to — before finalizing the exact API shape, since "how should it feel to
  use" is the actual core question here, not just "should we have one"?
