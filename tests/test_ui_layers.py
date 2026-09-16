"""Layers, focus state and value callbacks in the UI system.

Three gaps that only show up once a screen has more than one thing on it:

- `UIManager` held one flat list with **no removal API**, so every demo in
  the repository cleared its private `_root_elements`, and a HUD rebuilt
  mid-game jumped in front of the pause menu over it.
- `UIElementState.FOCUSED` and `DISABLED` were read by `Button`, `Checkbox`
  and the design-system components but never assigned, so Tab moved the
  focus ring invisibly.
- `Slider`, `Checkbox` and `TextInput` had no `on_change`, so an options
  screen had to poll every control every frame.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer
from pyguara.input import keys
from pyguara.input.events import OnMouseEvent, OnRawKeyEvent
from pyguara.ui.components.button import Button
from pyguara.ui.components.checkbox import Checkbox
from pyguara.ui.components.panel import Panel
from pyguara.ui.components.slider import Slider
from pyguara.ui.components.text import Label
from pyguara.ui.components.text_input import TextInput
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIElementState, UIEventType, UILayer


@pytest.fixture
def manager() -> UIManager:
    ui = UIManager(EventDispatcher())
    ui.set_screen_size(800, 600)
    return ui


@pytest.fixture
def renderer() -> Any:
    r = MagicMock(spec=UIRenderer)
    r.get_text_size.return_value = (40, 16)
    return r


def _button(name: str = "b", x: int = 0, y: int = 0) -> Button:
    return Button(name, Vector2(x, y), Vector2(100, 40))


class TestLayerOrdering:
    def test_a_higher_layer_renders_last(
        self, manager: UIManager, renderer: Any
    ) -> None:
        """Later means on top, and the HUD must stay under the overlay."""
        hud = _button("hud")
        overlay = _button("overlay")
        manager.add_element(overlay, UILayer.OVERLAY)
        manager.add_element(hud, UILayer.HUD)

        assert manager.elements() == [hud, overlay]

    def test_within_a_layer_order_is_insertion_order(self, manager: UIManager) -> None:
        first, second = _button("1"), _button("2")
        manager.add_element(first, UILayer.HUD)
        manager.add_element(second, UILayer.HUD)

        assert manager.elements(UILayer.HUD) == [first, second]

    def test_rebuilding_a_lower_layer_does_not_jump_it_forward(
        self, manager: UIManager
    ) -> None:
        """The regression a flat list could not avoid."""
        overlay = _button("overlay")
        manager.add_element(_button("old hud"), UILayer.HUD)
        manager.add_element(overlay, UILayer.OVERLAY)

        manager.clear(UILayer.HUD)
        fresh_hud = _button("new hud")
        manager.add_element(fresh_hud, UILayer.HUD)

        assert manager.elements() == [fresh_hud, overlay]

    def test_the_default_layer_is_content(self, manager: UIManager) -> None:
        element = _button()
        manager.add_element(element)

        assert manager.elements(UILayer.CONTENT) == [element]


class TestHitTesting:
    def test_the_top_layer_takes_the_click(self, manager: UIManager) -> None:
        """Overlapping elements: the overlay eats it, the HUD does not."""
        hud, overlay = _button("hud"), _button("overlay")
        clicks: list[str] = []
        hud.on_click = lambda _el: clicks.append("hud")
        overlay.on_click = lambda _el: clicks.append("overlay")
        manager.add_element(hud, UILayer.HUD)
        manager.add_element(overlay, UILayer.OVERLAY)

        for is_down in (True, False):
            manager._on_mouse_event(
                OnMouseEvent(
                    position=(10, 10), button=1, is_down=is_down, is_motion=False
                )
            )

        assert clicks == ["overlay"]


class TestRemoval:
    def test_remove_element_takes_it_out(self, manager: UIManager) -> None:
        element = _button()
        manager.add_element(element, UILayer.HUD)

        assert manager.remove_element(element) is True
        assert manager.elements() == []

    def test_removing_something_absent_reports_it(self, manager: UIManager) -> None:
        assert manager.remove_element(_button()) is False

    def test_clear_without_a_layer_empties_everything(self, manager: UIManager) -> None:
        manager.add_element(_button(), UILayer.HUD)
        manager.add_element(_button(), UILayer.OVERLAY)

        manager.clear()

        assert manager.elements() == []

    def test_clearing_drops_the_focus_it_held(self, manager: UIManager) -> None:
        """A focused element that no longer exists would wedge the ring."""
        element = _button()
        manager.add_element(element, UILayer.OVERLAY)
        manager.set_focus(element)

        manager.clear()

        assert manager.focused_element is None


class TestFocusRingIsModal:
    def test_the_ring_is_the_topmost_layer_that_has_one(
        self, manager: UIManager
    ) -> None:
        """Tab inside an options panel must not wander into the HUD."""
        hud = _button("hud")
        overlay = _button("overlay")
        manager.add_element(hud, UILayer.HUD)
        manager.add_element(overlay, UILayer.OVERLAY)

        assert manager.focus_ring() == [overlay]

    def test_it_falls_through_layers_with_nothing_focusable(
        self, manager: UIManager
    ) -> None:
        hud = _button("hud")
        manager.add_element(hud, UILayer.HUD)
        manager.add_element(Label("decoration", Vector2(0, 0)), UILayer.OVERLAY)

        assert manager.focus_ring() == [hud]


class TestFocusIsVisible:
    def test_focusing_sets_the_state(self, manager: UIManager) -> None:
        """The state every component already drew and nothing ever set."""
        element = _button()
        manager.add_element(element)

        manager.set_focus(element)

        assert element.state == UIElementState.FOCUSED

    def test_losing_focus_restores_the_resting_state(self, manager: UIManager) -> None:
        first, second = _button("1"), _button("2")
        manager.add_element(first)
        manager.add_element(second)

        manager.set_focus(first)
        manager.set_focus(second)

        assert first.state == UIElementState.NORMAL
        assert second.state == UIElementState.FOCUSED

    def test_a_focused_button_shows_the_focus_ring_colour(
        self, manager: UIManager
    ) -> None:
        """With `visible=True` -- what Tab/arrow traversal passes. A plain
        `set_focus()` (a click, a screen pre-focusing on build) does not,
        which `TestFocusVisibility` below covers."""
        element = _button()
        manager.add_element(element)

        manager.set_focus(element, visible=True)

        assert element.border_color() == element.theme.colors.focus_ring

    def test_hovering_a_focused_element_then_leaving_returns_to_focused(
        self, manager: UIManager
    ) -> None:
        """Focus outlives a hover -- it is a different kind of state."""
        element = _button("b", 0, 0)
        manager.add_element(element)
        manager.set_focus(element)

        element.handle_event(UIEventType.MOUSE_MOVE, Vector2(10, 10))
        element.handle_event(UIEventType.MOUSE_MOVE, Vector2(500, 500))

        assert element.state == UIElementState.FOCUSED

    def test_disabling_dims_it(self) -> None:
        element = _button()

        element.set_enabled(False)

        assert element.state == UIElementState.DISABLED


class TestKeyboardActivation:
    @pytest.mark.parametrize("key", [keys.RETURN, keys.SPACE], ids=["enter", "space"])
    def test_the_focused_element_activates(self, manager: UIManager, key: int) -> None:
        """Without this the ring could move but never choose."""
        element = _button()
        fired: list[str] = []
        element.on_click = lambda _el: fired.append("clicked")
        manager.add_element(element)
        manager.set_focus(element)

        manager._on_key_event(
            OnRawKeyEvent(key_code=key, is_down=True, modifiers=set())
        )

        assert fired == ["clicked"]

    def test_a_disabled_element_does_not_activate(self, manager: UIManager) -> None:
        element = _button()
        fired: list[str] = []
        element.on_click = lambda _el: fired.append("clicked")
        manager.add_element(element)
        manager.set_focus(element)
        element.set_enabled(False)

        manager._on_key_event(
            OnRawKeyEvent(key_code=keys.RETURN, is_down=True, modifiers=set())
        )

        assert fired == []


class TestValueCallbacks:
    def test_a_slider_reports_a_change_once(self) -> None:
        slider = Slider(Vector2(0, 0), width=100)
        seen: list[float] = []
        slider.on_change = seen.append

        slider.set_value(0.5)
        slider.set_value(0.5)

        assert seen == [0.5]

    def test_a_slider_clamps_to_its_range(self) -> None:
        slider = Slider(Vector2(0, 0), width=100, min_val=0.0, max_val=1.0)

        slider.set_value(4.0)

        assert slider.value == 1.0

    def test_a_checkbox_reports_a_toggle(self) -> None:
        box = Checkbox("Vsync", Vector2(0, 0))
        seen: list[bool] = []
        box.on_change = seen.append

        box.toggle()
        box.set_checked(True)

        assert seen == [True]

    def test_a_text_input_reports_each_edit(self) -> None:
        field = TextInput(Vector2(0, 0))
        seen: list[str] = []
        field.on_change = seen.append

        field.set_text("ab")
        field.set_text("ab")

        assert seen == ["ab"]


class TestLabelInvalidatesLayout:
    def test_changing_the_text_marks_the_layout_stale(
        self, manager: UIManager, renderer: Any
    ) -> None:
        """A counter going from 9 to 10 is a different width."""
        label = Label("9", Vector2(0, 0))
        manager.add_element(label)
        manager.render(renderer)  # clears the dirty flag

        label.set_text("10")

        assert manager._layout_dirty is True

    def test_setting_the_same_text_does_not(
        self, manager: UIManager, renderer: Any
    ) -> None:
        label = Label("9", Vector2(0, 0))
        manager.add_element(label)
        manager.render(renderer)

        label.set_text("9")

        assert manager._layout_dirty is False


class TestFocusVisibility:
    """The focus ring paints only when the keyboard put it there.

    Before this, the ring painted whenever an element held focus at all --
    including a mouse click, and a screen pre-focusing its first button on
    build so Tab has somewhere to start. Either one put a bright outline on
    a button nobody navigated to, which read as a stray highlight rather
    than a focus indicator.
    """

    def test_set_focus_defaults_to_invisible(self, manager: UIManager) -> None:
        element = _button()
        manager.add_element(element)

        manager.set_focus(element)

        assert element.state == UIElementState.FOCUSED
        assert element.focus_visible is False

    def test_a_mouse_click_focuses_without_a_ring(self, manager: UIManager) -> None:
        element = _button()
        manager.add_element(element)

        for is_down in (True, False):
            manager._on_mouse_event(
                OnMouseEvent(
                    position=(10, 10), button=1, is_down=is_down, is_motion=False
                )
            )

        assert manager.focused_element is element
        assert element.focus_visible is False

    def test_tab_traversal_shows_the_ring(self, manager: UIManager) -> None:
        element = _button()
        manager.add_element(element)

        manager._on_key_event(
            OnRawKeyEvent(key_code=keys.TAB, is_down=True, modifiers=set())
        )

        assert manager.focused_element is element
        assert element.focus_visible is True

    def test_arrow_traversal_shows_the_ring_too(self, manager: UIManager) -> None:
        element = _button()
        manager.add_element(element)

        manager._on_key_event(
            OnRawKeyEvent(key_code=keys.DOWN, is_down=True, modifiers=set())
        )

        assert element.focus_visible is True

    def test_losing_focus_clears_visibility(self, manager: UIManager) -> None:
        first, second = _button("1"), _button("2")
        manager.add_element(first)
        manager.add_element(second)

        manager.set_focus(first, visible=True)
        manager.set_focus(second)

        assert first.focus_visible is False

    def test_reselecting_the_same_element_still_updates_visibility(
        self, manager: UIManager
    ) -> None:
        """Tab with only one focusable thing on screen re-selects it --
        the ring still has to appear, even though nothing else changed."""
        element = _button()
        manager.add_element(element)
        manager.set_focus(element)  # invisible

        manager.set_focus(element, visible=True)

        assert element.focus_visible is True

    def test_clicking_a_button_inside_a_container_focuses_the_button(
        self, manager: UIManager
    ) -> None:
        """The regression: a click used to focus the ROOT (the container
        the click bubbled up through), not the button actually hit."""
        from pyguara.ui.layout import BoxContainer

        container = BoxContainer(Vector2(0, 0), Vector2(200, 200))
        button = _button("inside", 10, 10)
        container.add_child(button)
        manager.add_element(container)

        for is_down in (True, False):
            manager._on_mouse_event(
                OnMouseEvent(
                    position=(20, 20), button=1, is_down=is_down, is_motion=False
                )
            )

        assert manager.focused_element is button

    def test_a_click_on_a_decorative_child_focuses_nothing(
        self, manager: UIManager
    ) -> None:
        """A click landing on a non-focusable label inside a panel must
        not focus the label, and must not focus the panel either -- the
        original bug, where the ROOT the click bubbled up through got
        focused regardless of what was actually under the cursor."""
        panel = Panel(Vector2(0, 0), Vector2(200, 100))
        label = Label("decoration", Vector2(10, 10))
        panel.add_child(label)
        manager.add_element(panel)

        for is_down in (True, False):
            manager._on_mouse_event(
                OnMouseEvent(
                    position=(15, 15), button=1, is_down=is_down, is_motion=False
                )
            )

        assert manager.focused_element is None
