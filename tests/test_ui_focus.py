"""Tests for UI focus traversal.

A UI you cannot Tab through is incomplete, and every future menu hits it.
These run headless: the ring is derived from the element tree, not from
geometry, so none of this needs a renderer or a window.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input import keys
from pyguara.input.events import OnRawKeyEvent
from pyguara.ui.base import UIElement
from pyguara.ui.components.button import Button
from pyguara.ui.components.text import Label
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIEventType


class Spy(UIElement):
    """A focusable element that records what it was asked to handle."""

    def __init__(self, consume: bool = False) -> None:
        super().__init__(Vector2(0, 0), Vector2(10, 10))
        self.focusable = True
        self.consume = consume
        self.seen: list[int] = []

    def render(self, renderer) -> None:  # pragma: no cover - never drawn
        pass

    def _process_input(
        self, event_type: UIEventType, position: Vector2, button: int
    ) -> bool:
        if event_type == UIEventType.KEY_DOWN:
            self.seen.append(button)
            return self.consume
        return False


def press(manager: UIManager, key_code: int, *modifiers: int) -> None:
    """Dispatch a key-down followed by its key-up."""
    manager._dispatcher.dispatch(
        OnRawKeyEvent(key_code=key_code, is_down=True, modifiers=set(modifiers))
    )
    manager._dispatcher.dispatch(
        OnRawKeyEvent(key_code=key_code, is_down=False, modifiers=set(modifiers))
    )


def manager_with(*elements: UIElement) -> UIManager:
    """A manager holding `elements` as roots."""
    manager = UIManager(EventDispatcher())
    for element in elements:
        manager.add_element(element)
    return manager


class TestFocusRing:
    def test_only_focusable_elements_are_in_the_ring(self) -> None:
        """A label or a layout box is not a stop on the Tab ring."""
        button = Button("ok", Vector2(0, 0))
        label = Label("title", Vector2(0, 0))
        manager = manager_with(label, button)

        assert manager.focus_ring() == [button]

    def test_interactive_widgets_are_focusable_by_default(self) -> None:
        from pyguara.ui.components.checkbox import Checkbox
        from pyguara.ui.components.slider import Slider
        from pyguara.ui.components.text_input import TextInput

        widgets = [
            Button("ok", Vector2(0, 0)),
            Checkbox("on", Vector2(0, 0)),
            Slider(Vector2(0, 0)),
            TextInput(Vector2(0, 0)),
        ]

        assert all(widget.focusable for widget in widgets)

    def test_the_ring_walks_children_depth_first(self) -> None:
        """Declaration order, which is the order a reader's eye takes --
        no geometry involved."""
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        container = BoxContainer(Vector2(0, 0), Vector2(100, 100))
        container.add_child(first)
        container.add_child(second)
        outside = Button("c", Vector2(0, 0))

        manager = manager_with(container, outside)

        assert manager.focus_ring() == [first, second, outside]

    def test_a_hidden_element_is_skipped(self) -> None:
        hidden, shown = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        hidden.visible = False

        assert manager_with(hidden, shown).focus_ring() == [shown]

    def test_a_disabled_element_is_skipped(self) -> None:
        disabled, shown = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        disabled.enabled = False

        assert manager_with(disabled, shown).focus_ring() == [shown]

    def test_a_hidden_container_takes_its_children_with_it(self) -> None:
        """A collapsed panel's contents must not be reachable by Tab just
        because they still exist."""
        child = Button("a", Vector2(0, 0))
        container = BoxContainer(Vector2(0, 0), Vector2(100, 100))
        container.add_child(child)
        container.visible = False

        assert manager_with(container).focus_ring() == []


class TestTraversal:
    def test_focus_next_enters_the_ring_when_nothing_is_focused(self) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)

        assert manager.focus_next() is first

    def test_focus_previous_enters_at_the_end(self) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)

        assert manager.focus_previous() is second

    def test_focus_next_advances_and_wraps(self) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)

        manager.set_focus(second)

        assert manager.focus_next() is first

    def test_focus_previous_wraps_backwards(self) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)

        manager.set_focus(first)

        assert manager.focus_previous() is second

    def test_traversal_with_nothing_focusable_focuses_nothing(self) -> None:
        manager = manager_with(Label("title", Vector2(0, 0)))

        assert manager.focus_next() is None
        assert manager.focused_element is None

    def test_focus_on_an_element_that_left_the_ring_re_enters_it(self) -> None:
        """Focusing something and then hiding it must not strand traversal
        on an element that is no longer reachable."""
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)
        manager.set_focus(first)
        first.visible = False

        assert manager.focus_next() is second

    def test_focus_change_notifies_both_elements(self) -> None:
        """`set_focus` already dispatched FOCUS_LOST/GAINED; traversal goes
        through it rather than assigning the field."""
        first, second = Spy(), Spy()
        manager = manager_with(first, second)

        manager.focus_next()
        manager.focus_next()

        assert first.state is not None
        assert manager.focused_element is second


class TestKeyboardDefaults:
    def test_tab_moves_focus_forward(self) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)

        press(manager, keys.TAB)
        press(manager, keys.TAB)

        assert manager.focused_element is second

    def test_shift_tab_moves_focus_back(self) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)
        manager.set_focus(second)

        press(manager, keys.TAB, keys.L_SHIFT)

        assert manager.focused_element is first

    @pytest.mark.parametrize("key", [keys.DOWN, keys.RIGHT])
    def test_forward_arrows_move_focus_forward(self, key: int) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)
        manager.set_focus(first)

        press(manager, key)

        assert manager.focused_element is second

    @pytest.mark.parametrize("key", [keys.UP, keys.LEFT])
    def test_backward_arrows_move_focus_back(self, key: int) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)
        manager.set_focus(second)

        press(manager, key)

        assert manager.focused_element is first

    def test_the_focused_element_sees_the_key_first(self) -> None:
        spy = Spy()
        manager = manager_with(spy)
        manager.set_focus(spy)

        press(manager, keys.TAB)

        assert spy.seen == [keys.TAB]

    def test_a_consumed_key_does_not_also_traverse(self) -> None:
        """What lets a text input keep its arrow keys for the caret while
        the same keys still traverse a row of buttons."""
        consumer, other = Spy(consume=True), Spy()
        manager = manager_with(consumer, other)
        manager.set_focus(consumer)

        press(manager, keys.RIGHT)

        assert manager.focused_element is consumer

    def test_an_unconsumed_key_traverses(self) -> None:
        passive, other = Spy(consume=False), Spy()
        manager = manager_with(passive, other)
        manager.set_focus(passive)

        press(manager, keys.RIGHT)

        assert manager.focused_element is other

    def test_an_unrelated_key_does_not_move_focus(self) -> None:
        first, second = Button("a", Vector2(0, 0)), Button("b", Vector2(0, 0))
        manager = manager_with(first, second)
        manager.set_focus(first)

        press(manager, keys.SPACE)

        assert manager.focused_element is first

    def test_traversal_fires_once_per_press_not_on_release(self) -> None:
        """A key-down and its key-up are one press; moving on both would
        skip every other element."""
        elements = [Button(str(i), Vector2(0, 0)) for i in range(3)]
        manager = manager_with(*elements)

        press(manager, keys.TAB)

        assert manager.focused_element is elements[0]

    def test_tab_works_with_nothing_focused_yet(self) -> None:
        """The first Tab into a fresh menu is the common case."""
        first = Button("a", Vector2(0, 0))
        manager = manager_with(first, Button("b", Vector2(0, 0)))

        press(manager, keys.TAB)

        assert manager.focused_element is first
