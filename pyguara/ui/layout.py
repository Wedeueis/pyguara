"""Layout containers."""

from pyguara.common.types import Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.types import LayoutAlignment, LayoutDirection


class BoxContainer(UIElement):
    """Stacks children linearly with alignment support."""

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        direction: LayoutDirection = LayoutDirection.VERTICAL,
        alignment: LayoutAlignment = LayoutAlignment.START,
        spacing: int = 5,
    ) -> None:
        """Initialize the layout container."""
        super().__init__(position, size)
        self.direction = direction
        self.alignment = alignment
        self.spacing = spacing

    def render(self, renderer: UIRenderer) -> None:
        """Render children."""
        # Containers usually don't render themselves, just children
        # But we could draw a debug background here if needed
        for child in self.children:
            if child.visible:
                child.render(renderer)

    def layout(self, available_rect: Rect, renderer: UIRenderer) -> None:
        """Recalculate child positions based on alignment and direction.

        Overrides `UIElement.layout`: the container first resolves its own
        rect (its `constraints` against `available_rect`, if any), then
        measures every visible child and stacks them along `direction`,
        distributing free space per `alignment` on the main axis and either
        centring or stretching them on the cross axis. Nested containers are
        laid out recursively afterwards.

        Args:
            available_rect: The rectangle this container may occupy.
            renderer: Passed to each visible child's `measure()` before its
                size is read, so text-sized children stack correctly.
        """
        self.measure(renderer)
        if self.constraints:
            self.rect = self.constraints.apply(self.rect, available_rect)

        visible_children = [c for c in self.children if c.visible]
        if not visible_children:
            return

        is_vertical = self.direction == LayoutDirection.VERTICAL

        # 1. Measure children, then sum the space they need on the main axis.
        for child in visible_children:
            child.measure(renderer)

        total_size = sum(
            child.rect.height if is_vertical else child.rect.width
            for child in visible_children
        )
        total_size += self.spacing * (len(visible_children) - 1)

        # 2. Distribute free space on the main axis per alignment.
        container_main = self.rect.height if is_vertical else self.rect.width
        start_offset = 0
        if self.alignment == LayoutAlignment.CENTER:
            start_offset = (container_main - total_size) // 2
        elif self.alignment == LayoutAlignment.END:
            start_offset = container_main - total_size

        # 3. Position children.
        current_x = self.rect.x + (0 if is_vertical else start_offset)
        current_y = self.rect.y + (start_offset if is_vertical else 0)
        stretch = self.alignment == LayoutAlignment.STRETCH

        for child in visible_children:
            if is_vertical:
                child.rect.y = current_y
                current_y += child.rect.height + self.spacing
                if stretch:
                    child.rect.x = self.rect.x
                    child.rect.width = self.rect.width
                else:
                    child.rect.x = (
                        self.rect.x + (self.rect.width - child.rect.width) // 2
                    )
            else:
                child.rect.x = current_x
                current_x += child.rect.width + self.spacing
                if stretch:
                    child.rect.y = self.rect.y
                    child.rect.height = self.rect.height
                else:
                    child.rect.y = (
                        self.rect.y + (self.rect.height - child.rect.height) // 2
                    )

        # 4. Recurse into children that have their own subtree, so a nested
        #    container stacks its own children against the slot it was just
        #    given.
        for child in visible_children:
            if child.children:
                child.layout(child.rect, renderer)


class GridContainer(UIElement):
    """Lays children out in a fixed number of columns, row by row.

    What `BoxContainer` cannot do: an inventory, an ability bar, a crafting
    grid. Children flow left to right and wrap, so adding one never
    requires rewriting the layout.

    Column width is uniform -- the content width split `columns` ways, minus
    spacing -- because that is what a slot grid means. Row height is the
    tallest child in that row, or `row_height` when the grid wants square
    cells regardless of content.
    """

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        columns: int,
        spacing: int = 5,
        row_height: int | None = None,
        alignment: LayoutAlignment = LayoutAlignment.STRETCH,
    ) -> None:
        """Initialise the grid.

        Args:
            position: Top-left corner.
            size: The grid's own size.
            columns: How many cells per row. At least 1.
            spacing: Gap between cells, both horizontally and vertically --
                one value, like `BoxContainer.spacing`, because a grid with
                different gaps on each axis does not read as a grid.
            row_height: Fixed height for every row, for square slots. None
                sizes each row to its tallest child.
            alignment: `STRETCH` (the default) fills each cell, which is
                what a slot grid wants. Anything else keeps every child's
                measured size and centres it in its cell.

        Raises:
            ValueError: If `columns` is below 1. A zero would divide by
                zero computing the column width, and a negative would
                produce rows that never advance.
        """
        super().__init__(position, size)
        if columns < 1:
            raise ValueError(f"GridContainer needs at least 1 column, got {columns}.")
        self.columns = columns
        self.spacing = spacing
        self.row_height = row_height
        self.alignment = alignment

    def render(self, renderer: UIRenderer) -> None:
        """Render the visible children.

        Args:
            renderer: The UI renderer.
        """
        for child in self.children:
            if child.visible:
                child.render(renderer)

    def layout(self, available_rect: Rect, renderer: UIRenderer) -> None:
        """Place each visible child in its cell, wrapping every `columns`.

        Args:
            available_rect: The rectangle this grid may occupy.
            renderer: Passed to each child's `measure()` before its size is
                read, so a text-sized child reports its real height and the
                row it is in is tall enough for it.
        """
        self.measure(renderer)
        if self.constraints:
            self.rect = self.constraints.apply(self.rect, available_rect)

        visible_children = [child for child in self.children if child.visible]
        if not visible_children:
            return

        content = self.get_content_rect()
        total_spacing = self.spacing * (self.columns - 1)
        column_width = max(0, (content.width - total_spacing) // self.columns)

        for child in visible_children:
            child.measure(renderer)

        stretch = self.alignment == LayoutAlignment.STRETCH
        row_top = content.y

        for row_start in range(0, len(visible_children), self.columns):
            row = visible_children[row_start : row_start + self.columns]
            height = (
                self.row_height
                if self.row_height is not None
                else max(child.rect.height for child in row)
            )

            for column, child in enumerate(row):
                cell_x = content.x + column * (column_width + self.spacing)
                if stretch:
                    child.rect.x = cell_x
                    child.rect.y = row_top
                    child.rect.width = column_width
                    child.rect.height = height
                else:
                    child.rect.x = cell_x + (column_width - child.rect.width) // 2
                    child.rect.y = row_top + (height - child.rect.height) // 2

            row_top += height + self.spacing

        # Recurse, so a container in a cell stacks its own children against
        # the cell it was just given -- same as BoxContainer.
        for child in visible_children:
            if child.children:
                child.layout(child.rect, renderer)

    def content_height(self) -> int:
        """Total height the laid-out rows occupy, ignoring this grid's own.

        What a `ScrollContainer` needs to know how far it may scroll: the
        grid's `rect.height` is the window it was given, not the extent of
        what is in it.

        Returns:
            Height in pixels, 0 when nothing is visible.
        """
        visible_children = [child for child in self.children if child.visible]
        if not visible_children:
            return 0
        top = min(child.rect.y for child in visible_children)
        bottom = max(child.rect.y + child.rect.height for child in visible_children)
        return bottom - top


class ScrollContainer(UIElement):
    """A viewport that clips its contents and scrolls them.

    An inventory grid or a message log holds more than fits. This is the
    window: children are laid out at their full extent, shifted by the
    scroll offset, and clipped to this element's rect so the part outside
    is not drawn.

    **Children are shifted during layout, not during render.** Translating
    at draw time would leave every child's `rect` at its unscrolled
    position, so hit-testing would land on whatever used to be under the
    cursor -- clicking the fifth inventory slot and getting the second.
    Moving the rects means the click, the hover and the pixels all agree,
    which is the only arrangement that does not need a second coordinate
    space nobody remembers to convert through.

    Implements `base.Scrollable`, so `UIManager` routes the wheel here when
    the cursor is anywhere inside -- including over a button in the list,
    since it walks *up* from whatever it hit.
    """

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        scroll_speed: float = 30.0,
        horizontal: bool = False,
    ) -> None:
        """Initialise the viewport.

        Args:
            position: Top-left corner.
            size: The viewport's size -- the window, not the content.
            scroll_speed: Pixels per wheel notch.
            horizontal: Scroll sideways instead of vertically. A viewport
                scrolls one axis: two axes at once needs two scrollbars and
                a drag affordance, which is a different widget.
        """
        super().__init__(position, size)
        self.scroll_speed = scroll_speed
        self.horizontal = horizontal
        self._offset = 0.0
        self._content_extent = 0

    @property
    def offset(self) -> float:
        """How far the contents are scrolled, in pixels. Never negative."""
        return self._offset

    @offset.setter
    def offset(self, value: float) -> None:
        """Scroll to an absolute position, clamped to the scrollable range.

        Args:
            value: The new offset in pixels.
        """
        clamped = max(0.0, min(float(value), float(self.max_offset)))
        if clamped != self._offset:
            self._offset = clamped
            self.invalidate_layout()

    @property
    def max_offset(self) -> int:
        """The furthest this viewport can scroll.

        Zero when the contents fit, which is what makes `scroll_by()`
        return False and hand the wheel back to whatever is underneath.
        """
        window = self.rect.width if self.horizontal else self.rect.height
        return max(0, self._content_extent - window)

    @property
    def content_extent(self) -> int:
        """The size of the contents along the scrolling axis, as last laid out."""
        return self._content_extent

    def scroll_by(self, dx: float, dy: float) -> bool:
        """Scroll by a wheel delta.

        Wheel `y` is positive *away* from the user, which is a request to
        move the content down and therefore the offset up -- hence the
        negation. Getting this backwards is the single most noticeable bug
        a scroll view can have.

        Args:
            dx: Horizontal notches.
            dy: Vertical notches.

        Returns:
            True if the offset moved. False when already at an end, so the
            manager keeps walking up and the page behind a list that cannot
            scroll still does.
        """
        notches = dx if self.horizontal else dy
        if notches == 0:
            return False

        before = self._offset
        self.offset = self._offset - notches * self.scroll_speed
        return self._offset != before

    def scroll_to_end(self) -> None:
        """Scroll fully to the bottom (or right).

        What a message log wants after appending: the newest line is the
        one worth seeing.
        """
        self.offset = self.max_offset

    def render(self, renderer: UIRenderer) -> None:
        """Draw the children, clipped to this viewport.

        The clip is popped in a `finally`: a child that raises mid-draw
        would otherwise leave the clip set and silently truncate the rest
        of the frame, which looks like a rendering bug a long way from its
        cause.

        Args:
            renderer: The UI renderer.
        """
        renderer.push_clip(self.rect)
        try:
            for child in self.children:
                if child.visible:
                    child.render(renderer)
        finally:
            renderer.pop_clip()

    def layout(self, available_rect: Rect, renderer: UIRenderer) -> None:
        """Stack the children along the scroll axis, then shift by the offset.

        The viewport **places its own children**, like `BoxContainer` does,
        rather than letting them keep whatever position they were
        constructed with. That is what makes the layout idempotent: an
        element without constraints keeps its own `rect`, so a viewport
        that merely translated whatever it found would translate it *again*
        next frame, and the contents would walk a little further off screen
        on every one. Recomputing from the content origin cannot drift.

        They stack with no spacing and stretch across the cross axis, which
        is what a list or a grid in a viewport wants. Put a `BoxContainer`
        or `GridContainer` inside for spacing or columns; it gets the whole
        content slot and arranges itself in it.

        Args:
            available_rect: The rectangle this viewport may occupy.
            renderer: Passed through to the children.
        """
        self.measure(renderer)
        if self.constraints:
            self.rect = self.constraints.apply(self.rect, available_rect)

        content = self.get_content_rect()
        visible_children = [child for child in self.children if child.visible]
        if not visible_children:
            self._content_extent = 0
            return

        axis_origin = content.x if self.horizontal else content.y
        cursor = axis_origin
        for child in visible_children:
            child.measure(renderer)
            if self.horizontal:
                child.rect.x = cursor
                child.rect.y = content.y
                child.rect.height = content.height
                cursor += child.rect.width
            else:
                child.rect.x = content.x
                child.rect.y = cursor
                child.rect.width = content.width
                cursor += child.rect.height
            child.layout(child.rect, renderer)

        self._content_extent = max(0, cursor - axis_origin)

        # Re-clamp: the contents may have shrunk since the last frame -- a
        # filtered inventory, a cleared log -- leaving the offset past an
        # end that no longer exists, and a blank viewport the user cannot
        # scroll back from.
        self._offset = max(0.0, min(self._offset, float(self.max_offset)))

        if self._offset:
            shift = -int(self._offset)
            for child in visible_children:
                _translate_subtree(
                    child,
                    shift if self.horizontal else 0,
                    0 if self.horizontal else shift,
                )


def _translate_subtree(element: UIElement, dx: int, dy: int) -> None:
    """Move an element and every descendant by a pixel offset.

    The whole subtree, not just the element: a button inside a container
    inside a scroll view has its own rect, and leaving it behind is how a
    scrolled list ends up hit-testing against where it used to be.

    Args:
        element: The subtree root.
        dx: Horizontal pixels.
        dy: Vertical pixels.
    """
    element.rect.x += dx
    element.rect.y += dy
    for child in element.children:
        _translate_subtree(child, dx, dy)
