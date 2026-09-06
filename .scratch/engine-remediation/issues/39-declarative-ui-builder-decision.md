# Decide on a declarative builder API for UI hierarchies

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
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

## Resolution

Architecture settled without needing a prototype (verified against actual code, not
assumed):

- **Opt-in sugar, coexisting indefinitely — not a full replace.** All 9 demos build
  UI imperatively today; a full replace would add "migrate 9 demos" scope to a
  purely ergonomic change (no bug being fixed), overlapping the map's separate,
  larger **Demo migration** fog. This engine-remediation effort stays focused on
  that distinction.
- **Callbacks need no new mechanism.** `UIElement.on_click` is a bare
  `Optional[Callable]` attribute, assigned post-construction identically in every
  demo today (`btn.on_click = self._on_start_click`) — `Button` doesn't even accept
  it as a constructor argument. The builder just does the same assignment
  immediately after constructing each element; pure passthrough.
- **Theme needs no wiring at all.** `UIElement.__init__` already calls `get_theme()`
  unconditionally — every element themes itself the instant it's constructed,
  builder or not.

**The one open question — DSL syntax ergonomics ("does this feel good to use")** —
isn't a decision the codebase's current state can answer; it's a design question
about a not-yet-built interface. Spun off as a `/prototype` ticket rather than
decided in the abstract: [Prototype the declarative UI builder
API](49-prototype-ui-builder.md).
