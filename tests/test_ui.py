from unittest.mock import MagicMock
from pyguara.ui.base import UIElement, UIElementState
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIEventType
from pyguara.common.types import Vector2
from pyguara.input.events import OnMouseEvent


from typing import Any


class MockWidget(UIElement):
    def render(self, renderer: Any) -> None:
        pass


def test_ui_element_hit_test() -> None:
    # 100x100 box at 0,0
    elem = MockWidget(Vector2(0, 0), Vector2(100, 100))

    # Hit
    assert elem.handle_event(UIEventType.MOUSE_MOVE, Vector2(50, 50))
    assert elem.state == UIElementState.HOVERED

    # Miss
    assert not elem.handle_event(UIEventType.MOUSE_MOVE, Vector2(150, 150))
    # State returns to normal on miss
    # Note: State may still be HOVERED if checked immediately after


def test_ui_hierarchy_bubbling() -> None:
    # Parent 200x200
    parent = MockWidget(Vector2(0, 0), Vector2(200, 200))
    # Child 50x50 inside parent
    child = MockWidget(Vector2(10, 10), Vector2(50, 50))
    parent.add_child(child)

    # Click on Child
    assert parent.handle_event(UIEventType.MOUSE_DOWN, Vector2(20, 20), 1)

    # Child should be pressed
    assert child.state == UIElementState.PRESSED
    # Parent should NOT be pressed (child consumed it)
    assert parent.state != UIElementState.PRESSED


def test_ui_manager_routing(event_dispatcher: Any) -> None:
    manager = UIManager(event_dispatcher)

    elem = MockWidget(Vector2(0, 0), Vector2(100, 100))
    manager.add_element(elem)

    # Simulate Engine Event
    evt = OnMouseEvent(position=(50, 50), is_motion=True)
    # Dispatcher calls handler directly in sync mode or via queue
    # We call the handler directly to test logic
    manager._on_mouse_event(evt)

    assert elem.state == UIElementState.HOVERED


def test_click_callback() -> None:
    elem = MockWidget(Vector2(0, 0), Vector2(100, 100))

    callback = MagicMock()
    elem.on_click = callback

    # Sequence: Down -> Up inside
    elem.handle_event(UIEventType.MOUSE_DOWN, Vector2(50, 50), 1)
    elem.handle_event(UIEventType.MOUSE_UP, Vector2(50, 50), 1)

    callback.assert_called_once_with(elem)
