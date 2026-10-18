"""Keyboard input component."""

from collections.abc import Callable

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.input import keys
from pyguara.ui.clipboard import Clipboard, InMemoryClipboard
from pyguara.ui.components.widget import Widget
from pyguara.ui.text_layout import caret_index_at
from pyguara.ui.types import UIEventType

PADDING = 5
"""Pixels between the field's border and its text, on every side."""

BLINK_SECONDS = 0.53
"""How long the caret spends shown, then hidden.

The rate most desktop toolkits settle on. Fast enough to read as a
cursor, slow enough not to be a strobe.
"""

_SHIFT = frozenset({keys.L_SHIFT, keys.R_SHIFT})
_CTRL = frozenset({keys.L_CTRL, keys.R_CTRL})


class TextInput(Widget):
    """An editable text field with a caret, a selection and a clipboard.

    It had none of those. `insert_text` appended, so typing in the middle
    of a value was impossible; DELETE was aliased to BACKSPACE, so there
    was only one direction to erase in; and the caret was drawn from the
    measured width of the whole string, which pinned it to the end
    whatever you did. There were no arrows, no Home or End, no selection
    and no clipboard, in 136 lines that read as a finished widget.

    The IME foundation was already right and is unchanged: composed text
    arrives through `insert_text()` from `TextInputEvent` rather than
    being guessed from a key code, so accented and non-US input works.
    What is added sits beside it.

    Attributes:
        cursor: Where the caret sits, as an index between characters, so
            `0` is before the first and `len(text)` is after the last.
        selection_anchor: The other end of the selection, or None when
            there is no selection. The selected range is whatever lies
            between it and `cursor`, in either order -- selecting
            leftwards is as ordinary as selecting rightwards.
    """

    def __init__(
        self,
        position: Vector2,
        width: int = 200,
        placeholder: str = "",
        clipboard: Clipboard | None = None,
    ) -> None:
        """Initialize the text input.

        Args:
            position: Top-left corner.
            width: Field width in pixels.
            placeholder: Faint text shown while the field is empty.
            clipboard: Where cut and copied text goes. Defaults to an
                `InMemoryClipboard`, which is process-local: copy between
                two fields in the same game and it works, copy from the
                browser and it does not. Pass
                `pyguara.input.backends.PygameClipboard` for the real
                one. The default is the smaller promise on purpose -- a
                field constructed in a test or a headless tool needs a
                clipboard that cannot fail.
        """
        super().__init__(position, Vector2(width, 30))
        self.focusable = True
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.max_length = 32
        self.cursor = 0
        self.selection_anchor: int | None = None
        self.font_size = 16

        self._clipboard: Clipboard = clipboard or InMemoryClipboard()
        self._blink = 0.0
        self._dragging = False
        self._scroll = 0
        # Hit-testing a click needs to measure text, and a mouse event
        # carries no renderer. The last one to draw this field is kept
        # for that. Before the first frame there is nothing to measure
        # with, and a click then puts the caret at the end of the text --
        # which is where it already was.
        self._renderer: UIRenderer | None = None

        # Fired on every accepted edit, so a field can drive something live
        # rather than being read once on submit.
        self.on_change: Callable[[str], None] | None = None

    # --- selection ------------------------------------------------------

    @property
    def has_selection(self) -> bool:
        """Whether any characters are selected."""
        return (
            self.selection_anchor is not None and self.selection_anchor != self.cursor
        )

    @property
    def selection(self) -> tuple[int, int]:
        """The selected range as `(start, end)`, ordered, possibly empty."""
        if self.selection_anchor is None:
            return (self.cursor, self.cursor)
        return (
            min(self.cursor, self.selection_anchor),
            max(self.cursor, self.selection_anchor),
        )

    @property
    def selected_text(self) -> str:
        """The selected characters, or `""`."""
        start, end = self.selection
        return self.text[start:end]

    def select_all(self) -> None:
        """Select the whole value and put the caret at its end."""
        self.selection_anchor = 0
        self.cursor = len(self.text)

    def clear_selection(self) -> None:
        """Drop the selection, leaving the caret where it is."""
        self.selection_anchor = None

    def _place_cursor(self, index: int, *, extend: bool) -> None:
        """Move the caret, extending or collapsing the selection.

        Args:
            index: Where to put it; clamped into the text.
            extend: True to keep the far end of the selection anchored,
                which is what shift does.
        """
        index = max(0, min(index, len(self.text)))
        if extend:
            if self.selection_anchor is None:
                self.selection_anchor = self.cursor
        else:
            self.selection_anchor = None
        self.cursor = index
        self._show_caret()

    def _delete_selection(self) -> bool:
        """Remove the selected characters.

        Returns:
            True if anything was removed.
        """
        if not self.has_selection:
            return False
        start, end = self.selection
        self.selection_anchor = None
        self.cursor = start
        self._replace(self.text[:start] + self.text[end:])
        return True

    # --- editing --------------------------------------------------------

    def insert_text(self, text: str) -> bool:
        """Insert composed text at the caret, replacing any selection.

        This is the path real typing takes. It receives the characters the
        platform produced -- after layout, modifiers and IME composition --
        rather than a key code this widget has to guess a character from.

        It used to append, which made typing anywhere but the end of the
        value impossible.

        Args:
            text: The composed text, usually one character.

        Returns:
            True if anything was inserted, so a caller can tell whether the
            event was consumed.
        """
        if not self.active or not text:
            return False
        self._delete_selection()
        room = self.max_length - len(self.text)
        if room <= 0:
            return False
        addition = text[:room]
        at = self.cursor
        self._replace(self.text[:at] + addition + self.text[at:])
        self.cursor = at + len(addition)
        self._show_caret()
        return True

    def set_text(self, text: str) -> None:
        """Replace the contents, firing `on_change` if they differ.

        The caret and selection are reset, because an index into the old
        value means nothing in the new one.

        Args:
            text: The new contents, truncated to `max_length`.
        """
        trimmed = text[: self.max_length]
        self.selection_anchor = None
        self.cursor = min(self.cursor, len(trimmed))
        if trimmed == self.text:
            return
        self.cursor = len(trimmed)
        self._replace(trimmed)

    def _replace(self, text: str) -> None:
        """Set the value without touching the caret, and notify.

        Args:
            text: The new contents, already truncated.
        """
        if text == self.text:
            return
        self.text = text
        self.cursor = min(self.cursor, len(text))
        self.invalidate_layout()
        if self.on_change is not None:
            self.on_change(text)

    # --- clipboard ------------------------------------------------------

    def copy(self) -> bool:
        """Put the selection on the clipboard.

        Returns:
            True if there was a selection to copy.
        """
        if not self.has_selection:
            return False
        self._clipboard.set_text(self.selected_text)
        return True

    def cut(self) -> bool:
        """Copy the selection and remove it.

        Returns:
            True if there was a selection to cut.
        """
        if not self.copy():
            return False
        self._delete_selection()
        return True

    def paste(self) -> bool:
        """Insert the clipboard's text, replacing any selection.

        Newlines are flattened to spaces: this is a single-line field, and
        a pasted newline would otherwise reach `draw_text`, which renders
        it as a second line the field has no height for.

        Returns:
            True if anything was inserted.
        """
        pasted = self._clipboard.get_text()
        if not pasted:
            return False
        return self.insert_text(
            pasted.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        )

    # --- keyboard -------------------------------------------------------

    def handle_key(self, key_code: int, modifiers: frozenset[int]) -> bool:
        """Edit in response to a key press.

        Implements `pyguara.ui.base.KeyboardEditable`, which exists so
        that the modifiers reach here at all: `UIManager` had them on the
        event and dropped them, so Shift+Left was indistinguishable from
        Left and Ctrl+C from C.

        Args:
            key_code: The physical key.
            modifiers: Key codes of the modifiers held.

        Returns:
            True if the key was consumed. Returning False for an unknown
            key is what lets Tab still move the focus out of the field.
        """
        if not self.active:
            return False

        shift = bool(modifiers & _SHIFT)
        ctrl = bool(modifiers & _CTRL)

        if ctrl:
            if key_code == keys.A:
                self.select_all()
                return True
            if key_code == keys.C:
                self.copy()
                return True
            if key_code == keys.X:
                self.cut()
                return True
            if key_code == keys.V:
                self.paste()
                return True
            return False

        if key_code == keys.LEFT:
            self._arrow(-1, shift)
            return True
        if key_code == keys.RIGHT:
            self._arrow(1, shift)
            return True
        if key_code == keys.HOME:
            self._place_cursor(0, extend=shift)
            return True
        if key_code == keys.END:
            self._place_cursor(len(self.text), extend=shift)
            return True
        if key_code == keys.BACKSPACE:
            self._erase(-1)
            return True
        if key_code == keys.DELETE:
            self._erase(1)
            return True
        return False

    def _arrow(self, step: int, shift: bool) -> None:
        """Move the caret one character, or collapse a selection.

        Args:
            step: -1 for left, 1 for right.
            shift: True to extend the selection instead of collapsing it.
        """
        if self.has_selection and not shift:
            # An unshifted arrow against a selection collapses to its
            # near edge rather than moving from the caret, which is what
            # every editor does and what makes "select, then left" put you
            # before the selection instead of one character inside it.
            start, end = self.selection
            self._place_cursor(start if step < 0 else end, extend=False)
            return
        self._place_cursor(self.cursor + step, extend=shift)

    def _erase(self, direction: int) -> None:
        """Delete the selection, or one character.

        DELETE used to be aliased to BACKSPACE, so the two were one key.

        Args:
            direction: -1 to erase before the caret, 1 to erase after.
        """
        if self._delete_selection():
            self._show_caret()
            return
        at = self.cursor
        if direction < 0:
            if at == 0:
                return
            self._replace(self.text[: at - 1] + self.text[at:])
            self.cursor = at - 1
        else:
            if at >= len(self.text):
                return
            self._replace(self.text[:at] + self.text[at + 1 :])
            self.cursor = at
        self._show_caret()

    # --- mouse ----------------------------------------------------------

    def handle_event(
        self, event_type: UIEventType, position: Vector2, key_code: int = 0
    ) -> bool:
        """Handle focus and mouse selection.

        Key presses arrive through `handle_key` instead; see
        `KeyboardEditable`.
        """
        if event_type == UIEventType.MOUSE_DOWN:
            inside = self._contains(position)
            self.active = inside
            if inside:
                self._dragging = True
                self._place_cursor(self._index_at(position.x), extend=False)
                return True
            self.clear_selection()
            return False

        if event_type == UIEventType.MOUSE_MOVE and self._dragging:
            # Not gated on being inside: a drag that leaves the field
            # should keep selecting to its edge, which is what the clamp
            # in `caret_index_at` is for.
            self._place_cursor(self._index_at(position.x), extend=True)
            return True

        if event_type == UIEventType.MOUSE_UP and self._dragging:
            self._dragging = False
            return True

        if event_type == UIEventType.FOCUS_GAINED:
            self.active = True
            self._show_caret()
            return True

        if event_type == UIEventType.FOCUS_LOST:
            self.active = False
            self._dragging = False
            self.clear_selection()
            return True

        return False

    def _contains(self, position: Vector2) -> bool:
        """Whether `position` is inside the field.

        Args:
            position: A point in screen coordinates.

        Returns:
            True if inside.
        """
        return (
            self.rect.x <= position.x <= self.rect.x + self.rect.width
            and self.rect.y <= position.y <= self.rect.y + self.rect.height
        )

    def _index_at(self, screen_x: float) -> int:
        """Resolve a screen x coordinate to a caret index.

        Args:
            screen_x: A point in screen coordinates.

        Returns:
            An index in `0..len(text)`; the end of the text when this
            field has not been drawn yet and so has nothing to measure
            with.
        """
        renderer = self._renderer
        if renderer is None:
            return len(self.text)
        offset = int(screen_x - self.rect.x - PADDING + self._scroll)
        return caret_index_at(
            self.text,
            offset,
            lambda prefix: renderer.get_text_size(prefix, self.font_size)[0],
        )

    # --- frame ----------------------------------------------------------

    def update(self, dt: float) -> None:
        """Advance the caret blink.

        Args:
            dt: Seconds since the last rendered frame.
        """
        super().update(dt)
        self._blink += dt

    def _show_caret(self) -> None:
        """Restart the blink cycle showing, so an edit is never invisible."""
        self._blink = 0.0

    @property
    def caret_visible(self) -> bool:
        """Whether the caret is in the shown half of its blink cycle."""
        return int(self._blink / BLINK_SECONDS) % 2 == 0

    def render(self, renderer: UIRenderer) -> None:
        """Render the box, the selection, the text and the caret."""
        self._renderer = renderer
        colors = self.theme.colors
        # A field is cut into the surface; the focus ring is what says it
        # is taking keystrokes, rather than the accent colour standing in.
        border_color = colors.focus_ring if self.active else colors.edge_strong
        radius = self.theme.borders.radius
        renderer.draw_rect(self.rect, colors.surface_inset, border_radius=radius)
        renderer.draw_rect(self.rect, border_color, width=1, border_radius=radius)

        showing_placeholder = not self.text
        display_text = self.text if self.text else self.placeholder
        color = colors.text_body if self.text else colors.text_faint

        inner = Rect(
            self.rect.x + 1,
            self.rect.y + 1,
            max(0, self.rect.width - 2),
            max(0, self.rect.height - 2),
        )
        self._update_scroll(renderer)
        renderer.push_clip(inner)
        try:
            text_x = self.rect.x + PADDING - self._scroll
            text_y = self.rect.y + PADDING
            if self.active and self.has_selection and not showing_placeholder:
                self._draw_selection(renderer, text_x, text_y)
            renderer.draw_text(
                display_text, Vector2(text_x, text_y), color, self.font_size
            )
            if self.active and self.caret_visible:
                caret_x = text_x + self._width_to(renderer, self.cursor)
                renderer.draw_line(
                    Vector2(caret_x, self.rect.y + PADDING),
                    Vector2(caret_x, self.rect.y + self.rect.height - PADDING),
                    colors.text_body,
                )
        finally:
            renderer.pop_clip()

    def _draw_selection(
        self, renderer: UIRenderer, text_x: float, text_y: float
    ) -> None:
        """Fill the selected range behind the text.

        Args:
            renderer: The renderer to draw with.
            text_x: Where the text starts, already scrolled.
            text_y: The text's top edge.
        """
        start, end = self.selection
        left = text_x + self._width_to(renderer, start)
        right = text_x + self._width_to(renderer, end)
        _, height = renderer.get_text_size("", self.font_size)
        renderer.draw_rect(
            Rect(int(left), int(text_y), int(right - left), height),
            self._selection_color(),
            width=0,
        )

    def _selection_color(self) -> Color:
        """Derive the selection highlight from the theme's focus ring.

        Translucent rather than opaque, so the text stays legible through
        it -- the alternative is picking a second colour the theme does
        not define and having it clash with whichever preset is active.
        """
        ring = self.theme.colors.focus_ring
        return Color(ring.r, ring.g, ring.b, 90)

    def _width_to(self, renderer: UIRenderer, index: int) -> int:
        """Pixel width of the text up to `index`.

        Args:
            renderer: The renderer to measure with.
            index: A caret index.

        Returns:
            The width in pixels.
        """
        return int(renderer.get_text_size(self.text[:index], self.font_size)[0])

    def _update_scroll(self, renderer: UIRenderer) -> None:
        """Scroll horizontally so the caret stays inside the box.

        Without this the caret simply leaves the widget as soon as the
        value is longer than the field, which makes every key that moves
        it look broken.

        Args:
            renderer: The renderer to measure with.
        """
        visible = max(0, int(self.rect.width) - 2 * PADDING)
        caret = self._width_to(renderer, self.cursor)
        total = self._width_to(renderer, len(self.text))
        if caret - self._scroll > visible:
            self._scroll = caret - visible
        if caret - self._scroll < 0:
            self._scroll = caret
        # Never leave blank space on the right while text sits off to the
        # left: deleting from the end should pull the value back into view.
        self._scroll = max(0, min(self._scroll, max(0, total - visible)))
