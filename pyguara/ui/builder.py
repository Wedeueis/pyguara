"""Declarative construction of UI trees.

Opt-in sugar over the imperative API, not a replacement for it. Every demo
in this repository builds its UI by constructing elements and calling
`add_child()`, and all of that keeps working untouched -- the builder
*is* those calls, with the parent threaded through a context manager
instead of a local variable:

```python
with UIBuilder(ui_manager) as ui:
    with ui.box(Vector2(80, 288), Vector2(260, 220), spacing=14) as column:
        ui.label("Main Menu", font_size=44)
        ui.button("Start Game", on_click=self._on_start)
        ui.button("Quit", on_click=self._on_quit)

ui_manager.set_focus(column.children[0])
```

Three things it deliberately does *not* do, settled when the architecture
was decided rather than discovered here:

- **No callback mechanism of its own.** `UIElement.on_click` is a bare
  attribute that every demo assigns after construction; `on_click=` here
  does exactly that assignment and nothing more.
- **No theme wiring.** `UIElement.__init__` calls `get_theme()`
  unconditionally, so an element themes itself the moment it exists,
  builder or not.
- **No fixed widget vocabulary.** The factory methods below cover the
  engine's own components, but a game's custom elements are the normal
  case -- `guara_falcao` builds its screens out of `BevelPanel`,
  `BevelButton` and `Scrim`. `add()` and `nest()` take any `UIElement`
  subclass and keep its type, so a builder is never the reason a custom
  widget cannot be used.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import TracebackType
from typing import Any, TypeVar

from pyguara.common.types import Color, Vector2
from pyguara.ui.base import UIElement
from pyguara.ui.components.button import Button
from pyguara.ui.components.canvas import Canvas
from pyguara.ui.components.checkbox import Checkbox
from pyguara.ui.components.image import Image
from pyguara.ui.components.navbar import NavBar
from pyguara.ui.components.panel import Panel
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.slider import Slider
from pyguara.ui.components.text import Label
from pyguara.ui.components.text_input import TextInput
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import (
    LayoutAlignment,
    LayoutDirection,
    TextAlign,
    UILayer,
)

# Shared by `UIBuilder.add()` and `nest()`, which are methods on a
# non-generic class, so this stays a module-level TypeVar. `_Nested[E]`
# declares its own `E` -- a PEP 695 type parameter is scoped to the class
# or function that declares it, and cannot be shared between several, so
# a TypeVar used from more than one scope is still the right spelling.
E = TypeVar("E", bound=UIElement)

# Children of a container are positioned by its layout pass, so a nested
# element's own position is overwritten before it is ever drawn. Defaulting
# to the origin keeps that noise out of the call.
_ORIGIN = Vector2(0, 0)


class UIBuilderError(RuntimeError):
    """Raised when a builder is used in a way that cannot be meant."""


class _Nested[E: UIElement]:
    """Makes an already-attached element the parent for a `with` block.

    Deliberately a class rather than a `@contextmanager` generator. The
    element is attached by the factory that created this, *before* any
    `with` -- so `ui.panel(...)` on its own still adds a childless panel,
    rather than silently adding nothing.

    A generator-based version also made correctness depend on reference
    counting: calling `__enter__()` without a matching `__exit__()` left
    the parent stack pushed until the unreferenced generator happened to be
    collected, at which point `GeneratorExit` ran its `finally` and popped
    it. Whether a tree came out right then depended on when the garbage
    collector ran.
    """

    __slots__ = ("_builder", "_element")

    def __init__(self, builder: UIBuilder, element: E) -> None:
        """Initialize the scope.

        Args:
            builder: The builder whose parent stack to push and pop.
            element: The already-attached element to descend into.
        """
        self._builder = builder
        self._element = element

    def __enter__(self) -> E:
        """Make the element the current parent.

        Returns:
            The element, so `with ui.box(...) as column` binds it.
        """
        self._builder._push(self._element)
        return self._element

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Restore the previous parent, even if the block raised."""
        self._builder._pop(self._element)


class UIBuilder:
    """Builds a UI tree, tracking the current parent on a stack.

    Single use: build one tree, mount it, discard the builder. Demos
    rebuild their menus from scratch on every `on_resume()`, so reuse would
    buy nothing and a half-reset builder is a worse failure than a clear
    error.
    """

    def __init__(
        self,
        manager: UIManager | None = None,
        *,
        layer: int = UILayer.CONTENT,
    ) -> None:
        """Initialize the builder.

        Args:
            manager: Mounted into on a clean exit from the `with` block.
                `None` builds a detached tree, which `roots` hands back for
                the caller to place itself.
            layer: The `UILayer` roots are mounted at. Override per subtree
                with `layer()`.
        """
        self._manager = manager
        self._layer = layer
        self._stack: list[UIElement] = []
        # Roots paired with the layer in force when each was created, so a
        # backdrop and a content root can come out of one builder.
        self._roots: list[tuple[UIElement, int]] = []
        self._entered = False
        self._finished = False

    # -- lifecycle ----------------------------------------------------

    def __enter__(self) -> UIBuilder:
        """Open the builder.

        Returns:
            This builder.

        Raises:
            UIBuilderError: If it has already been used.
        """
        if self._finished:
            raise UIBuilderError(
                "This UIBuilder has already been used. Build a new one per "
                "tree -- they are single-use on purpose."
            )
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the builder, mounting the tree if the block succeeded.

        A tree built by a block that raised is **not** mounted: half a menu
        on screen is harder to diagnose than no menu, and the exception
        already says what went wrong.
        """
        self._finished = True
        self._stack.clear()
        if exc_type is None and self._manager is not None:
            self.mount(self._manager)

    @property
    def roots(self) -> list[UIElement]:
        """The top-level elements built, in creation order."""
        return [root for root, _layer in self._roots]

    @property
    def current(self) -> UIElement | None:
        """The element children are currently being added to, if any."""
        return self._stack[-1] if self._stack else None

    def mount(self, manager: UIManager | None = None, layer: int | None = None) -> None:
        """Add every root to `manager`, each at the layer it was built under.

        Called automatically on a clean exit when the builder was given a
        manager. Call it directly to place a detached tree later.

        Args:
            manager: The manager to add to. Defaults to the one this
                builder was constructed with.
            layer: Overrides every root's recorded layer.

        Raises:
            UIBuilderError: If no manager was given here or at construction.
        """
        target = manager if manager is not None else self._manager
        if target is None:
            raise UIBuilderError(
                "mount() needs a UIManager, either here or passed to "
                "UIBuilder(...). Use `roots` to place the tree by hand."
            )
        for root, root_layer in self._roots:
            target.add_element(root, layer if layer is not None else root_layer)

    # -- structure ----------------------------------------------------

    @contextmanager
    def layer(self, layer: int) -> Iterator[UIBuilder]:
        """Build roots at `layer` for the duration of the block.

        Only roots carry a layer -- a child is drawn by its parent, so the
        layer of a nested element means nothing. Lets one builder produce a
        backdrop scrim and a content panel, as `guara_falcao`'s title
        screen does.

        Args:
            layer: The `UILayer` for roots created inside the block.

        Yields:
            This builder.
        """
        previous = self._layer
        self._layer = layer
        try:
            yield self
        finally:
            self._layer = previous

    def add(
        self, element: E, *, on_click: Callable[[UIElement], None] | None = None
    ) -> E:
        """Attach an already-constructed element at the current position.

        The escape hatch that keeps the builder open to a game's own
        widgets: anything deriving from `UIElement` goes in, and its
        concrete type comes back out.

        Args:
            element: The element to attach.
            on_click: Assigned to `element.on_click` if given.

        Returns:
            `element`, unchanged apart from its parent and `on_click`.

        Raises:
            UIBuilderError: If the builder is closed, or the element
                already belongs to another parent.
        """
        self._check_open()
        if element.parent is not None:
            raise UIBuilderError(
                f"{type(element).__name__} already has a parent "
                f"({type(element.parent).__name__}). An element belongs to "
                "one tree; build a second element instead of re-attaching."
            )
        if on_click is not None:
            element.on_click = on_click

        if self._stack:
            self._stack[-1].add_child(element)
        else:
            self._roots.append((element, self._layer))
        return element

    def nest(self, element: E) -> _Nested[E]:
        """Attach `element` now, and offer it as the parent for a block.

        The container counterpart to `add()`, and how a custom container --
        a themed panel, a bespoke layout -- gets children through the
        builder.

        The attachment happens here, not on `__enter__`, so a container
        used without a `with` block is still added (childless) rather than
        silently dropped.

        Args:
            element: The container to attach.

        Returns:
            A context manager that descends into `element`.
        """
        self.add(element)
        return _Nested(self, element)

    # -- containers ---------------------------------------------------

    def box(
        self,
        position: Vector2 = _ORIGIN,
        size: Vector2 = _ORIGIN,
        *,
        direction: LayoutDirection = LayoutDirection.VERTICAL,
        alignment: LayoutAlignment = LayoutAlignment.START,
        spacing: int = 5,
    ) -> _Nested[BoxContainer]:
        """Open a `BoxContainer` that stacks its children linearly.

        Args:
            position: Top-left corner.
            size: Width and height.
            direction: Main axis.
            alignment: Distribution along the main axis.
            spacing: Gap between children in pixels.

        Returns:
            A context manager yielding the `BoxContainer`.
        """
        return self.nest(
            BoxContainer(
                position,
                size,
                direction=direction,
                alignment=alignment,
                spacing=spacing,
            )
        )

    def panel(
        self,
        position: Vector2 = _ORIGIN,
        size: Vector2 = _ORIGIN,
        *,
        color: Color | None = None,
        border_width: int = 1,
    ) -> _Nested[Panel]:
        """Open a `Panel` as a container.

        Args:
            position: Top-left corner.
            size: Width and height.
            color: Background colour, or the theme's.
            border_width: Border thickness in pixels.

        Returns:
            A context manager yielding the `Panel`.
        """
        return self.nest(Panel(position, size, color=color, border_width=border_width))

    def navbar(self, width: int, height: int = 50) -> _Nested[NavBar]:
        """Open a `NavBar`, a horizontal bar container.

        Args:
            width: Bar width in pixels.
            height: Bar height in pixels.

        Returns:
            A context manager yielding the `NavBar`.
        """
        return self.nest(NavBar(width, height))

    def canvas(
        self,
        position: Vector2 = _ORIGIN,
        size: Vector2 = _ORIGIN,
        *,
        bg_color: Color | None = None,
    ) -> _Nested[Canvas]:
        """Open a `Canvas` for free-form drawing.

        Args:
            position: Top-left corner.
            size: Width and height.
            bg_color: Background colour, if any.

        Returns:
            A context manager yielding the `Canvas`.
        """
        return self.nest(Canvas(position, size, bg_color=bg_color))

    # -- leaves -------------------------------------------------------

    def label(
        self,
        text: str,
        position: Vector2 = _ORIGIN,
        *,
        font_size: int = 16,
        color: Color | None = None,
        width: float | None = None,
        align: TextAlign = TextAlign.LEFT,
    ) -> Label:
        """Add a text label.

        Args:
            text: The text to draw.
            position: Top-left corner.
            font_size: Point size.
            color: Text colour, or the theme's.
            width: Box width to align within. Centring text needs this --
                without a width there is nothing to centre against.
            align: Horizontal alignment inside `width`.

        Returns:
            The `Label`.
        """
        return self.add(
            Label(
                text,
                position,
                font_size=font_size,
                color=color,
                width=width,
                align=align,
            )
        )

    def button(
        self,
        text: str,
        position: Vector2 = _ORIGIN,
        size: Vector2 | None = None,
        *,
        on_click: Callable[[UIElement], None] | None = None,
    ) -> Button:
        """Add a button.

        Args:
            text: The label on the button.
            position: Top-left corner.
            size: Width and height. Defaults to `Button`'s own default.
            on_click: Called with the button when it is clicked.

        Returns:
            The `Button`.
        """
        button = (
            Button(text, position) if size is None else Button(text, position, size)
        )
        return self.add(button, on_click=on_click)

    def checkbox(
        self,
        label: str,
        position: Vector2 = _ORIGIN,
        *,
        checked: bool = False,
        on_change: Callable[[bool], None] | None = None,
    ) -> Checkbox:
        """Add a checkbox.

        Args:
            label: Text beside the box.
            position: Top-left corner.
            checked: Initial state.
            on_change: Called with the new state when it is toggled.

        Returns:
            The `Checkbox`.
        """
        checkbox = self.add(Checkbox(label, position, checked=checked))
        if on_change is not None:
            checkbox.on_change = on_change
        return checkbox

    def slider(
        self,
        position: Vector2 = _ORIGIN,
        *,
        width: int = 150,
        min_val: float = 0.0,
        max_val: float = 1.0,
        step: float = 0.0,
        show_value: bool = False,
        on_change: Callable[[float], None] | None = None,
    ) -> Slider:
        """Add a slider.

        Args:
            position: Top-left corner.
            width: Track width in pixels.
            min_val: Lowest value.
            max_val: Highest value.
            step: Quantisation, or 0 for continuous.
            show_value: Draw the current value beside the track.
            on_change: Called with the new value as it moves.

        Returns:
            The `Slider`.
        """
        slider = self.add(
            Slider(
                position,
                width=width,
                min_val=min_val,
                max_val=max_val,
                step=step,
                show_value=show_value,
            )
        )
        if on_change is not None:
            slider.on_change = on_change
        return slider

    def text_input(
        self,
        position: Vector2 = _ORIGIN,
        *,
        width: int = 200,
        placeholder: str = "",
        on_change: Callable[[str], None] | None = None,
    ) -> TextInput:
        """Add a single-line text field.

        Args:
            position: Top-left corner.
            width: Field width in pixels.
            placeholder: Shown while the field is empty.
            on_change: Called with the text as it changes.

        Returns:
            The `TextInput`.
        """
        field = self.add(TextInput(position, width=width, placeholder=placeholder))
        if on_change is not None:
            field.on_change = on_change
        return field

    def progress_bar(
        self,
        position: Vector2 = _ORIGIN,
        size: Vector2 | None = None,
        *,
        value: float = 0.5,
        fill_color: Color | None = None,
        bg_color: Color | None = None,
    ) -> ProgressBar:
        """Add a progress bar.

        Args:
            position: Top-left corner.
            size: Width and height. Defaults to `ProgressBar`'s own.
            value: Fill fraction, 0..1.
            fill_color: Filled portion's colour, or the theme's.
            bg_color: Track colour, or the theme's.

        Returns:
            The `ProgressBar`.
        """
        bar = (
            ProgressBar(position, value=value, fill_color=fill_color, bg_color=bg_color)
            if size is None
            else ProgressBar(
                position,
                size,
                value=value,
                fill_color=fill_color,
                bg_color=bg_color,
            )
        )
        return self.add(bar)

    def image(
        self,
        texture: Any,
        position: Vector2 = _ORIGIN,
        size: Vector2 = _ORIGIN,
        *,
        color: Color | None = None,
    ) -> Image:
        """Add an image.

        Args:
            texture: The backend texture to draw.
            position: Top-left corner.
            size: Width and height.
            color: Tint, if any.

        Returns:
            The `Image`.
        """
        return self.add(Image(texture, position, size, color=color))

    # -- internals ----------------------------------------------------

    def _push(self, element: UIElement) -> None:
        """Make `element` the parent for subsequent additions.

        Args:
            element: The container being entered.
        """
        self._stack.append(element)

    def _pop(self, element: UIElement) -> None:
        """Leave `element`, restoring the previous parent.

        Tolerates a stack already unwound by `__exit__` -- a `with` block
        left by an exception that also ended the builder would otherwise
        pop an empty list.

        Args:
            element: The container being left.
        """
        if self._stack and self._stack[-1] is element:
            self._stack.pop()

    def _check_open(self) -> None:
        """Raise unless the builder is inside its `with` block.

        Raises:
            UIBuilderError: If it was never entered, or already exited.
        """
        if self._finished:
            raise UIBuilderError(
                "This UIBuilder is closed. Elements added after the `with` "
                "block would never be mounted."
            )
        if not self._entered:
            raise UIBuilderError(
                "Use UIBuilder in a `with` block -- that is what mounts the "
                "tree and keeps the parent stack honest."
            )
