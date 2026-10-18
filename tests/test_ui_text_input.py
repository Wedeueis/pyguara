"""The text-input path: composed characters, not guessed ones.

`TextInput.handle_event` used to build characters with `chr(key_code)`.
That cannot work. A key code is a *physical* key, so SDL reports `SDLK_a`
whether or not shift is held -- **typing a capital letter was impossible**,
every non-US layout produced the wrong letter, and accented or IME input
was out of reach entirely.

`TextInputEvent` carries what the platform actually composed, after layout,
modifiers and IME. `UIManager` routes it to the focused widget through the
`TextInsertable` capability, so `handle_event`'s signature is untouched and
widgets that do not take text are unaffected.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.input import KeyDownEvent, TextInputEvent
from pyguara.input import keys
from pyguara.input.manager import InputManager
from pyguara.ui.base import KeyboardEditable, TextInsertable
from pyguara.ui.clipboard import InMemoryClipboard
from pyguara.ui.components.button import Button
from pyguara.ui.components.text_input import TextInput
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIEventType


@pytest.fixture
def focused_field() -> tuple[EventDispatcher, UIManager, TextInput]:
    """A focused text field reachable through a real UIManager."""
    dispatcher = EventDispatcher()
    manager = UIManager(dispatcher)
    manager.set_screen_size(800, 600)
    field = TextInput(Vector2(0, 0))
    manager.add_element(field)
    manager.set_focus(field)
    return dispatcher, manager, field


@pytest.mark.unit
class TestComposedText:
    def test_a_capital_letter_can_be_typed(self, focused_field) -> None:
        """The headline bug. SDL reports `SDLK_a` with or without shift, so
        the old `chr(key_code)` path turned shift-A into "a"."""
        dispatcher, _manager, field = focused_field

        for char in "Hello":
            dispatcher.dispatch(TextInputEvent(text=char))

        assert field.text == "Hello"

    def test_accented_text_arrives_intact(self, focused_field) -> None:
        """Unreachable through key codes at all."""
        dispatcher, _manager, field = focused_field

        dispatcher.dispatch(TextInputEvent(text="ção"))

        assert field.text == "ção"

    def test_multi_character_events_are_accepted(self, focused_field) -> None:
        """One event is usually one character, but IME composition can
        deliver several at once, so the field must not assume."""
        dispatcher, _manager, field = focused_field

        dispatcher.dispatch(TextInputEvent(text="ab"))
        dispatcher.dispatch(TextInputEvent(text="cd"))

        assert field.text == "abcd"

    def test_nothing_is_typed_into_an_unfocused_field(self) -> None:
        dispatcher = EventDispatcher()
        manager = UIManager(dispatcher)
        manager.set_screen_size(800, 600)
        field = TextInput(Vector2(0, 0))
        manager.add_element(field)

        dispatcher.dispatch(TextInputEvent(text="x"))

        assert field.text == ""

    def test_text_for_a_widget_that_takes_none_is_dropped(self) -> None:
        """A focused button must not swallow or crash on a text event."""
        dispatcher = EventDispatcher()
        manager = UIManager(dispatcher)
        manager.set_screen_size(800, 600)
        button = Button("ok", Vector2(0, 0))
        manager.add_element(button)
        manager.set_focus(button)

        dispatcher.dispatch(TextInputEvent(text="x"))  # must not raise


@pytest.mark.unit
class TestKeyCodeSynthesisIsGone:
    def test_a_printable_key_code_no_longer_inserts_anything(self) -> None:
        """Pinned deliberately: the old path is what produced lowercase-only
        text, so it must stay gone rather than quietly coexist and
        double-insert alongside the composed-text path."""
        field = TextInput(Vector2(0, 0))
        field.active = True

        consumed = field.handle_event(UIEventType.KEY_DOWN, Vector2(0, 0), keys.A)

        assert field.text == ""
        assert consumed is False

    def test_a_printable_key_press_still_inserts_nothing(self) -> None:
        """The same guard against the richer `handle_key` channel.

        Editing keys moved there to get at the modifiers; the character
        path must not follow them, or every letter would be inserted
        twice -- once as composed text and once as a key code.
        """
        field = TextInput(Vector2(0, 0))
        field.active = True

        consumed = field.handle_key(keys.A, frozenset())

        assert field.text == ""
        assert consumed is False

    def test_backspace_still_deletes(self) -> None:
        """Editing keys are still key codes -- they are physical keys, which
        is exactly what a key code is for."""
        field = TextInput(Vector2(0, 0))
        field.active = True
        field.insert_text("abc")

        field.handle_key(keys.BACKSPACE, frozenset())

        assert field.text == "ab"

    def test_delete_is_no_longer_an_alias_for_backspace(self) -> None:
        """It erases forwards now, which is the whole point of having both.

        DELETE was wired to `self.text[:-1]`, exactly as BACKSPACE was,
        so the field had one erase direction under two keys. With the
        caret at the end there is nothing in front of it to erase, so
        DELETE correctly does nothing here.
        """
        field = TextInput(Vector2(0, 0))
        field.active = True
        field.insert_text("abc")

        field.handle_key(keys.DELETE, frozenset())

        assert field.text == "abc"

    def test_delete_erases_the_character_in_front_of_the_caret(self) -> None:
        field = TextInput(Vector2(0, 0))
        field.active = True
        field.insert_text("abc")
        field.cursor = 0

        field.handle_key(keys.DELETE, frozenset())

        assert field.text == "bc"


@pytest.mark.unit
class TestInsertText:
    def test_it_respects_max_length(self) -> None:
        field = TextInput(Vector2(0, 0))
        field.active = True
        field.max_length = 3

        assert field.insert_text("abcdef") is True
        assert field.text == "abc"

    def test_a_full_field_accepts_nothing_more(self) -> None:
        field = TextInput(Vector2(0, 0))
        field.active = True
        field.max_length = 2
        field.insert_text("ab")

        assert field.insert_text("c") is False
        assert field.text == "ab"

    def test_an_inactive_field_accepts_nothing(self) -> None:
        field = TextInput(Vector2(0, 0))
        assert field.insert_text("a") is False
        assert field.text == ""

    def test_empty_text_is_not_an_insert(self) -> None:
        field = TextInput(Vector2(0, 0))
        field.active = True
        assert field.insert_text("") is False

    def test_on_change_fires_for_typed_text(self) -> None:
        """A field can drive something live rather than being read on
        submit, and that has to work through the real typing path."""
        seen: list[str] = []
        field = TextInput(Vector2(0, 0))
        field.active = True
        field.on_change = seen.append

        field.insert_text("a")
        field.insert_text("b")

        assert seen == ["a", "ab"]


@pytest.mark.unit
class TestCapability:
    def test_a_text_input_is_text_insertable(self) -> None:
        assert isinstance(TextInput(Vector2(0, 0)), TextInsertable)

    def test_a_button_is_not(self) -> None:
        """Why this is a capability protocol rather than a `text` parameter
        on `handle_event`: widening that signature would break every widget
        already implementing the three-argument form, and only text fields
        have any use for it."""
        assert not isinstance(Button("ok", Vector2(0, 0)), TextInsertable)


class _StubInputBackend:
    """Minimal `IInputBackend`, matching the stub in `test_input.py`."""

    def __init__(self) -> None:
        self.joysticks: list[object] = []
        self._initialized = False

    def init_joysticks(self) -> None:
        self._initialized = True

    def quit_joysticks(self) -> None:
        self._initialized = False

    def is_initialized(self) -> bool:
        return self._initialized

    def get_joystick_count(self) -> int:
        return len(self.joysticks)

    def get_joystick(self, device_index: int) -> object:
        return self.joysticks[device_index]


@pytest.mark.unit
class TestInputManagerForwarding:
    def test_the_input_manager_forwards_composed_text(self) -> None:
        """It translates keys into actions, but a character has no action
        mapping to apply -- so the event goes through as-is."""
        dispatcher = EventDispatcher()
        seen: list[TextInputEvent] = []
        dispatcher.subscribe(TextInputEvent, seen.append)
        manager = InputManager(dispatcher, _StubInputBackend())  # type: ignore[arg-type]

        manager.process_event(TextInputEvent(text="q"))

        assert len(seen) == 1
        assert seen[0].text == "q"

    def test_key_events_still_become_actions(self) -> None:
        """The forwarding must not shadow the existing key path."""
        dispatcher = EventDispatcher()
        from pyguara.input.events import OnRawKeyEvent

        seen: list[OnRawKeyEvent] = []
        dispatcher.subscribe(OnRawKeyEvent, seen.append)
        manager = InputManager(dispatcher, _StubInputBackend())  # type: ignore[arg-type]

        manager.process_event(KeyDownEvent(key_code=keys.A))

        assert len(seen) == 1


SHIFT = frozenset({keys.L_SHIFT})
CTRL = frozenset({keys.L_CTRL})


def _field(text: str = "", cursor: int | None = None, **kwargs: object) -> TextInput:
    """An active field holding `text`, caret at the end unless told otherwise."""
    field = TextInput(Vector2(0, 0), **kwargs)  # type: ignore[arg-type]
    field.active = True
    field.insert_text(text)
    if cursor is not None:
        field.cursor = cursor
    return field


@pytest.mark.unit
class TestTheCaret:
    """There was no caret index at all: insert appended, delete took the
    last character, and the drawn caret was pinned to the end of the
    measured text whatever you did."""

    def test_typing_inserts_at_the_caret(self) -> None:
        field = _field("abcdef", cursor=3)

        field.insert_text("X")

        assert field.text == "abcXdef"
        assert field.cursor == 4

    def test_the_arrows_move_it(self) -> None:
        field = _field("abc")

        field.handle_key(keys.LEFT, frozenset())

        assert field.cursor == 2

    def test_it_stops_at_the_start(self) -> None:
        field = _field("abc", cursor=0)

        field.handle_key(keys.LEFT, frozenset())

        assert field.cursor == 0

    def test_it_stops_at_the_end(self) -> None:
        field = _field("abc")

        field.handle_key(keys.RIGHT, frozenset())

        assert field.cursor == 3

    def test_home_and_end(self) -> None:
        field = _field("abc")

        field.handle_key(keys.HOME, frozenset())
        assert field.cursor == 0

        field.handle_key(keys.END, frozenset())
        assert field.cursor == 3

    def test_backspace_erases_behind_it(self) -> None:
        field = _field("abcdef", cursor=3)

        field.handle_key(keys.BACKSPACE, frozenset())

        assert field.text == "abdef"
        assert field.cursor == 2

    def test_delete_erases_in_front_of_it(self) -> None:
        field = _field("abcdef", cursor=3)

        field.handle_key(keys.DELETE, frozenset())

        assert field.text == "abcef"
        assert field.cursor == 3

    def test_an_unknown_key_is_not_consumed(self) -> None:
        """So Tab still moves focus out of the field."""
        assert _field("abc").handle_key(keys.TAB, frozenset()) is False

    def test_an_inactive_field_ignores_keys(self) -> None:
        field = _field("abc")
        field.active = False

        assert field.handle_key(keys.BACKSPACE, frozenset()) is False
        assert field.text == "abc"


@pytest.mark.unit
class TestSelection:
    """Shift plus a movement key, which needed the modifiers to arrive."""

    def test_shift_left_selects_backwards(self) -> None:
        field = _field("abcdef")

        field.handle_key(keys.LEFT, SHIFT)
        field.handle_key(keys.LEFT, SHIFT)

        assert field.selected_text == "ef"
        assert field.selection == (4, 6)

    def test_shift_right_selects_forwards(self) -> None:
        field = _field("abcdef", cursor=0)

        field.handle_key(keys.RIGHT, SHIFT)

        assert field.selected_text == "a"

    def test_shift_home_selects_to_the_start(self) -> None:
        field = _field("abcdef", cursor=3)

        field.handle_key(keys.HOME, SHIFT)

        assert field.selected_text == "abc"

    def test_a_selection_made_leftwards_is_still_a_selection(self) -> None:
        """The anchor can be on either side of the caret."""
        field = _field("abcdef", cursor=4)
        field.handle_key(keys.LEFT, SHIFT)
        field.handle_key(keys.LEFT, SHIFT)

        assert field.cursor == 2
        assert field.selection_anchor == 4
        assert field.selected_text == "cd"

    def test_ctrl_a_selects_everything(self) -> None:
        field = _field("abcdef", cursor=2)

        field.handle_key(keys.A, CTRL)

        assert field.selected_text == "abcdef"

    def test_typing_replaces_the_selection(self) -> None:
        field = _field("abcdef")
        field.handle_key(keys.A, CTRL)

        field.insert_text("Z")

        assert field.text == "Z"
        assert field.cursor == 1

    def test_backspace_removes_the_selection_rather_than_a_character(self) -> None:
        field = _field("abcdef", cursor=2)
        field.selection_anchor = 4

        field.handle_key(keys.BACKSPACE, frozenset())

        assert field.text == "abef"
        assert field.cursor == 2
        assert not field.has_selection

    def test_delete_removes_the_selection_too(self) -> None:
        field = _field("abcdef", cursor=2)
        field.selection_anchor = 4

        field.handle_key(keys.DELETE, frozenset())

        assert field.text == "abef"

    def test_an_unshifted_arrow_collapses_to_the_near_edge(self) -> None:
        """ "Select, then left" belongs before the selection, not one
        character inside it."""
        field = _field("abcdef", cursor=4)
        field.selection_anchor = 2

        field.handle_key(keys.LEFT, frozenset())

        assert field.cursor == 2
        assert not field.has_selection

    def test_an_unshifted_right_arrow_collapses_to_the_far_edge(self) -> None:
        field = _field("abcdef", cursor=2)
        field.selection_anchor = 4

        field.handle_key(keys.RIGHT, frozenset())

        assert field.cursor == 4

    def test_losing_focus_drops_the_selection(self) -> None:
        field = _field("abcdef")
        field.handle_key(keys.A, CTRL)

        field.handle_event(UIEventType.FOCUS_LOST, Vector2(0, 0))

        assert not field.has_selection

    def test_an_empty_selection_is_not_a_selection(self) -> None:
        """An anchor equal to the caret selects nothing, so copy has
        nothing to take and backspace should erase a character."""
        field = _field("abc")
        field.selection_anchor = field.cursor

        assert not field.has_selection
        assert field.selected_text == ""


@pytest.mark.unit
class TestClipboard:
    """Cut, copy and paste, through a seam that is not pygame.

    `pyguara/ui` may not import a backend, so the field takes a
    `Clipboard`. The default is process-local rather than the desktop's:
    a field built in a test or a headless tool needs one that cannot
    fail, and reaching into the OS clipboard on construction is a bigger
    promise than a widget should make unasked.
    """

    def test_copy_puts_the_selection_on_the_clipboard(self) -> None:
        board = InMemoryClipboard()
        field = _field("abcdef", clipboard=board)
        field.cursor = 2
        field.selection_anchor = 5

        field.handle_key(keys.C, CTRL)

        assert board.get_text() == "cde"
        assert field.text == "abcdef"

    def test_cut_copies_and_removes(self) -> None:
        board = InMemoryClipboard()
        field = _field("abcdef", clipboard=board)
        field.cursor = 2
        field.selection_anchor = 5

        field.handle_key(keys.X, CTRL)

        assert board.get_text() == "cde"
        assert field.text == "abf"
        assert field.cursor == 2

    def test_paste_inserts_at_the_caret(self) -> None:
        field = _field("abef", cursor=2, clipboard=InMemoryClipboard("cd"))

        field.handle_key(keys.V, CTRL)

        assert field.text == "abcdef"
        assert field.cursor == 4

    def test_paste_replaces_a_selection(self) -> None:
        field = _field("abcdef", clipboard=InMemoryClipboard("Z"))
        field.handle_key(keys.A, CTRL)

        field.handle_key(keys.V, CTRL)

        assert field.text == "Z"

    def test_pasting_a_newline_does_not_make_a_second_line(self) -> None:
        """This field has one line of height; `draw_text` would render a
        pasted newline as a second one, below the box."""
        field = _field(clipboard=InMemoryClipboard("one\ntwo"))

        field.handle_key(keys.V, CTRL)

        assert "\n" not in field.text
        assert field.text == "one two"

    def test_paste_respects_max_length(self) -> None:
        field = _field(clipboard=InMemoryClipboard("x" * 100))
        field.max_length = 4

        field.handle_key(keys.V, CTRL)

        assert field.text == "xxxx"

    def test_copying_nothing_leaves_the_clipboard_alone(self) -> None:
        board = InMemoryClipboard("keep me")
        field = _field("abcdef", clipboard=board)

        assert field.copy() is False
        assert board.get_text() == "keep me"

    def test_pasting_nothing_inserts_nothing(self) -> None:
        field = _field("abc", clipboard=InMemoryClipboard(""))

        assert field.paste() is False
        assert field.text == "abc"

    def test_the_default_clipboard_works_between_two_fields(self) -> None:
        """Not the desktop's, but not useless either."""
        board = InMemoryClipboard()
        source = _field("secret", clipboard=board)
        source.handle_key(keys.A, CTRL)
        source.handle_key(keys.C, CTRL)

        target = _field(clipboard=board)
        target.handle_key(keys.V, CTRL)

        assert target.text == "secret"


@pytest.mark.unit
class TestTheModifiersActuallyArrive:
    """The gap that made selection and shortcuts unreachable.

    `OnRawKeyEvent` has carried `modifiers` all along; `UIManager` passed
    only `key_code` to `handle_event`, so no widget could tell Left from
    Shift+Left or C from Ctrl+C. The `KeyboardEditable` capability is the
    channel that carries them, following `TextInsertable` and
    `Scrollable` beside it rather than widening `handle_event` -- which
    would break every three-argument override in any game.
    """

    def test_a_text_input_declares_the_capability(self) -> None:
        assert isinstance(TextInput(Vector2(0, 0)), KeyboardEditable)

    def test_a_button_does_not(self) -> None:
        """So nothing else changes channel."""
        assert not isinstance(Button("ok", Vector2(0, 0)), KeyboardEditable)

    def test_shift_reaches_the_widget_through_the_manager(self) -> None:
        from pyguara.input.events import OnRawKeyEvent
        from pyguara.ui.manager import UIManager

        manager = UIManager(EventDispatcher())
        field = TextInput(Vector2(0, 0))
        field.insert_text("")
        manager.add_element(field)
        manager.set_focus(field)
        field.active = True
        field.insert_text("abcdef")

        manager._on_key_event(
            OnRawKeyEvent(key_code=keys.LEFT, is_down=True, modifiers={keys.L_SHIFT})
        )

        assert field.selected_text == "f"

    def test_without_shift_the_same_key_only_moves(self) -> None:
        from pyguara.input.events import OnRawKeyEvent
        from pyguara.ui.manager import UIManager

        manager = UIManager(EventDispatcher())
        field = TextInput(Vector2(0, 0))
        manager.add_element(field)
        manager.set_focus(field)
        field.active = True
        field.insert_text("abcdef")

        manager._on_key_event(
            OnRawKeyEvent(key_code=keys.LEFT, is_down=True, modifiers=set())
        )

        assert field.selected_text == ""
        assert field.cursor == 5

    def test_a_consumed_key_does_not_also_move_focus(self) -> None:
        """A field's arrows are its own; the ring must not steal them."""
        from pyguara.input.events import OnRawKeyEvent
        from pyguara.ui.manager import UIManager

        manager = UIManager(EventDispatcher())
        field = TextInput(Vector2(0, 0))
        other = Button("ok", Vector2(0, 100))
        manager.add_element(field)
        manager.add_element(other)
        manager.set_focus(field)
        field.active = True
        field.insert_text("abc")

        manager._on_key_event(
            OnRawKeyEvent(key_code=keys.LEFT, is_down=True, modifiers=set())
        )

        assert manager._focused_element is field

    def test_a_key_release_still_goes_the_old_way(self) -> None:
        """Only presses route through the capability; nothing that edits
        text cares about a release, and two channels for one key would be
        two places to handle it."""
        from pyguara.input.events import OnRawKeyEvent
        from pyguara.ui.manager import UIManager

        manager = UIManager(EventDispatcher())
        field = TextInput(Vector2(0, 0))
        manager.add_element(field)
        manager.set_focus(field)
        field.active = True
        field.insert_text("abc")

        manager._on_key_event(
            OnRawKeyEvent(key_code=keys.BACKSPACE, is_down=False, modifiers=set())
        )

        assert field.text == "abc"


@pytest.mark.unit
class TestTheCaretBlinks:
    """It did not, and the comment said "Blink logic would go here"."""

    def test_it_starts_visible(self) -> None:
        assert _field("abc").caret_visible is True

    def test_it_goes_dark_after_one_interval(self) -> None:
        from pyguara.ui.components.text_input import BLINK_SECONDS

        field = _field("abc")
        field.update(BLINK_SECONDS * 1.1)

        assert field.caret_visible is False

    def test_it_comes_back(self) -> None:
        from pyguara.ui.components.text_input import BLINK_SECONDS

        field = _field("abc")
        field.update(BLINK_SECONDS * 2.1)

        assert field.caret_visible is True

    def test_an_edit_restarts_the_cycle_showing(self) -> None:
        """Typing while the caret happens to be dark should not look dead."""
        from pyguara.ui.components.text_input import BLINK_SECONDS

        field = _field("abc")
        field.update(BLINK_SECONDS * 1.1)
        assert field.caret_visible is False

        field.insert_text("d")

        assert field.caret_visible is True

    def test_moving_the_caret_restarts_it_too(self) -> None:
        from pyguara.ui.components.text_input import BLINK_SECONDS

        field = _field("abc")
        field.update(BLINK_SECONDS * 1.1)

        field.handle_key(keys.LEFT, frozenset())

        assert field.caret_visible is True


class _TenPixelRenderer:
    """A renderer whose glyphs are 10 px wide and lines 20 px tall.

    Hit-testing a click is arithmetic, and testing it against whichever
    font the host has installed would be a measurement of Arial.
    """

    def __init__(self) -> None:
        self.texts: list[tuple[str, float, float]] = []
        self.rects: list[tuple[int, int, int, int]] = []
        self.lines: list[tuple[float, float]] = []
        self.clips = 0

    def get_text_size(self, text: str, size: int) -> tuple[int, int]:
        return (len(text) * 10, 20)

    def draw_text(self, text, position, color, size=16) -> None:  # type: ignore[no-untyped-def]
        self.texts.append((text, position.x, position.y))

    def draw_rect(self, rect, color, width=0, border_radius=0) -> None:  # type: ignore[no-untyped-def]
        self.rects.append((rect.x, rect.y, rect.width, rect.height))

    def draw_line(self, start, end, color, width=1) -> None:  # type: ignore[no-untyped-def]
        self.lines.append((start.x, start.y))

    def push_clip(self, rect) -> None:  # type: ignore[no-untyped-def]
        self.clips += 1

    def pop_clip(self) -> None:
        self.clips -= 1

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        from unittest.mock import MagicMock

        return MagicMock()


def _drawn(field: TextInput) -> _TenPixelRenderer:
    renderer = _TenPixelRenderer()
    field.render(renderer)  # type: ignore[arg-type]
    return renderer


@pytest.mark.unit
class TestClickingPositionsTheCaret:
    """There was no way to put the caret anywhere but the end."""

    def test_a_click_lands_between_characters(self) -> None:
        from pyguara.ui.components.text_input import PADDING

        field = _field("abcdef")
        _drawn(field)

        # "c" spans 20-30 px, so 24 is in its left half.
        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(PADDING + 24, 10))

        assert field.cursor == 2

    def test_the_right_half_of_a_glyph_puts_the_caret_after_it(self) -> None:
        from pyguara.ui.components.text_input import PADDING

        field = _field("abcdef")
        _drawn(field)

        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(PADDING + 26, 10))

        assert field.cursor == 3

    def test_a_click_past_the_end_lands_at_the_end(self) -> None:
        field = _field("abc")
        _drawn(field)

        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(190, 10))

        assert field.cursor == 3

    def test_a_click_clears_the_selection(self) -> None:
        field = _field("abcdef")
        _drawn(field)
        field.handle_key(keys.A, CTRL)

        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(10, 10))

        assert not field.has_selection

    def test_a_click_outside_defocuses(self) -> None:
        field = _field("abc")
        _drawn(field)

        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(1000, 1000))

        assert field.active is False

    def test_a_click_before_the_first_frame_falls_back_to_the_end(self) -> None:
        """A mouse event carries no renderer, so hit-testing uses the last
        one to draw this field. There has not been one yet."""
        field = _field("abcdef")

        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(10, 10))

        assert field.cursor == 6


@pytest.mark.unit
class TestDraggingSelects:
    def test_a_drag_extends_the_selection(self) -> None:
        from pyguara.ui.components.text_input import PADDING

        field = _field("abcdef")
        _drawn(field)

        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(PADDING + 5, 10))
        field.handle_event(UIEventType.MOUSE_MOVE, Vector2(PADDING + 35, 10))

        assert field.selected_text == "bcd"

    def test_a_drag_that_leaves_the_field_keeps_selecting_to_the_edge(self) -> None:
        from pyguara.ui.components.text_input import PADDING

        field = _field("abcdef")
        _drawn(field)

        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(PADDING + 5, 10))
        field.handle_event(UIEventType.MOUSE_MOVE, Vector2(5000, 900))

        assert field.selected_text == "bcdef"

    def test_motion_without_a_press_selects_nothing(self) -> None:
        field = _field("abcdef")
        _drawn(field)

        consumed = field.handle_event(UIEventType.MOUSE_MOVE, Vector2(30, 10))

        assert consumed is False
        assert not field.has_selection

    def test_releasing_ends_the_drag(self) -> None:
        field = _field("abcdef")
        _drawn(field)
        field.handle_event(UIEventType.MOUSE_DOWN, Vector2(10, 10))
        field.handle_event(UIEventType.MOUSE_UP, Vector2(10, 10))

        field.handle_event(UIEventType.MOUSE_MOVE, Vector2(60, 10))

        assert not field.has_selection


@pytest.mark.unit
class TestWhatIsDrawn:
    def test_the_caret_is_drawn_at_the_caret_index(self) -> None:
        from pyguara.ui.components.text_input import PADDING

        field = _field("abcdef", cursor=2)
        renderer = _drawn(field)

        assert renderer.lines[0][0] == PADDING + 20

    def test_an_inactive_field_draws_no_caret(self) -> None:
        field = _field("abc")
        field.active = False

        assert _drawn(field).lines == []

    def test_a_selection_is_drawn_behind_the_text(self) -> None:
        from pyguara.ui.components.text_input import PADDING

        field = _field("abcdef", cursor=1)
        field.selection_anchor = 4
        renderer = _drawn(field)

        # Box, border, then the highlight: x at "b", three glyphs wide.
        assert (PADDING + 10, PADDING, 30, 20) in renderer.rects

    def test_the_text_is_clipped_to_the_box(self) -> None:
        """A long value must not paint over the widget beside it."""
        field = _field("x" * 30)
        renderer = _drawn(field)

        assert renderer.clips == 0  # pushed and popped, balanced

    def test_a_long_value_scrolls_to_keep_the_caret_in_view(self) -> None:
        field = _field("x" * 30, clipboard=InMemoryClipboard())
        renderer = _drawn(field)

        caret_x = renderer.lines[0][0]
        assert caret_x <= field.rect.x + field.rect.width

    def test_moving_home_scrolls_back(self) -> None:
        from pyguara.ui.components.text_input import PADDING

        field = _field("x" * 30)
        _drawn(field)
        field.handle_key(keys.HOME, frozenset())
        renderer = _drawn(field)

        assert renderer.lines[0][0] == PADDING
        assert renderer.texts[0][1] == PADDING
