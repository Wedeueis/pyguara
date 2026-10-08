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
from pyguara.ui.base import TextInsertable
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

    def test_backspace_still_deletes(self) -> None:
        """Editing keys are still key codes -- they are physical keys, which
        is exactly what a key code is for."""
        field = TextInput(Vector2(0, 0))
        field.active = True
        field.insert_text("abc")

        field.handle_event(UIEventType.KEY_DOWN, Vector2(0, 0), keys.BACKSPACE)

        assert field.text == "ab"

    def test_delete_behaves_as_backspace(self) -> None:
        field = TextInput(Vector2(0, 0))
        field.active = True
        field.insert_text("abc")

        field.handle_event(UIEventType.KEY_DOWN, Vector2(0, 0), keys.DELETE)

        assert field.text == "ab"


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
