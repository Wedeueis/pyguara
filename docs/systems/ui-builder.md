# Declarative UI Builder

`UIBuilder` builds a UI tree the way the imperative API builds one, with the
parent threaded through a `with` block instead of a local variable. It is
**opt-in sugar, not a replacement**: every screen already written against
`add_child()` keeps working untouched, and the builder produces an
indistinguishable tree.

```python
from pyguara.common.types import Vector2
from pyguara.ui import UIBuilder

with UIBuilder(ui_manager) as ui:
    with ui.box(Vector2(270, 288), Vector2(260, 220), spacing=14) as column:
        ui.label("Main Menu", font_size=44)
        ui.button("Start Game", size=Vector2(260, 52), on_click=self._on_start)
        ui.button("Quit", size=Vector2(260, 52), on_click=self._on_quit)

ui_manager.set_focus(column.children[0])
```

The same screen, written by hand, is what the builder above expands to:

```python
column = BoxContainer(Vector2(270, 288), Vector2(260, 220), spacing=14)
title = Label("Main Menu", Vector2(0, 0), font_size=44)
column.add_child(title)
start = Button("Start Game", Vector2(0, 0), Vector2(260, 52))
start.on_click = self._on_start
column.add_child(start)
quit_button = Button("Quit", Vector2(0, 0), Vector2(260, 52))
quit_button.on_click = self._on_quit
column.add_child(quit_button)
ui_manager.add_element(column, UILayer.CONTENT)
```

## What it does not do

- **No callback mechanism of its own.** `UIElement.on_click` is a bare
  attribute, so `on_click=` is that same assignment and nothing more. The
  function you pass is the function stored.
- **No theme wiring.** `UIElement.__init__` calls `get_theme()`
  unconditionally, so an element themes itself the moment it exists.
- **No fixed widget vocabulary.** See [Custom widgets](#custom-widgets).

## Mounting

A builder given a `UIManager` mounts its roots when the `with` block ends:

```python
with UIBuilder(ui_manager) as ui:        # mounted on exit
    ...
```

Without one it builds a detached tree, which `roots` hands back:

```python
with UIBuilder() as ui:
    ...
for root in ui.roots:
    ...                                   # place it yourself
ui.mount(ui_manager)                      # or mount it later
```

A block that **raises mounts nothing**. Half a menu on screen is harder to
diagnose than no menu, and the exception already says what went wrong.

Only top-level elements are roots -- a nested element is drawn by its parent.

### Layers

Roots mount at the builder's layer (`UILayer.CONTENT` by default).
`layer()` scopes a different one, so one builder can produce a backdrop and
its content:

```python
with UIBuilder(ui_manager) as ui:
    with ui.layer(UILayer.BACKDROP):
        ui.add(Scrim(800, 600, strength=0.32))
    with ui.box(...) as column:
        ...
```

## Custom widgets

A game's own elements are the normal case, not the exception --
`guara_falcao` builds its screens out of `BevelPanel`, `BevelButton` and
`Scrim`. `add()` takes any `UIElement` and returns it with its own type
intact; `nest()` does the same and descends into it:

```python
with UIBuilder(ui_manager) as ui:
    with ui.nest(BevelPanel(Vector2(140, 96), Vector2(520, 132))) as plate:
        ui.label("GUARÁ & FALCÃO", font_size=44, width=520, align=TextAlign.CENTER)
    with ui.box(Vector2(270, 288), Vector2(260, 220), spacing=14):
        ui.add(BevelButton("Play", Vector2(0, 0)), on_click=self._on_play)
```

A container factory **attaches its element when it is called**, not when the
`with` block is entered, so `ui.panel(...)` on its own adds a childless
panel rather than silently adding nothing.

## Factories

| Containers | Leaves |
| --- | --- |
| `box()`, `panel()`, `navbar()`, `canvas()` | `label()`, `button()`, `checkbox()`, `slider()`, `text_input()`, `progress_bar()`, `image()` |
| `nest(element)` — any element | `add(element)` — any element |

Positions default to the origin: a child's position is overwritten by its
container's layout pass before it is ever drawn, so passing one is noise.
Sizes default to the component's own default where it has one.

`checkbox()`, `slider()` and `text_input()` take `on_change`; everything
clickable takes `on_click`.

## Errors

`UIBuilderError` is raised when a builder is used in a way that cannot be
meant, rather than quietly producing a tree nobody will see:

- adding before the `with` block, or after it
- reusing a builder (they are single-use; build one tree each)
- `mount()` with no manager anywhere
- attaching an element that already has a parent, which would silently
  remove it from the tree it is already in
