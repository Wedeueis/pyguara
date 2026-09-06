from unittest.mock import MagicMock

from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.layout import BoxContainer
from pyguara.ui.components.text import Label
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import LayoutDirection, LayoutAlignment
from pyguara.common.types import Vector2


class MockWidget(Widget):
    def render(self, r):
        pass


def test_box_layout_vertical():
    """
    Unit Test: Vertical Box Layout
    Verifies children are stacked vertically.
    """
    container = BoxContainer(
        Vector2(0, 0), Vector2(100, 200), direction=LayoutDirection.VERTICAL, spacing=10
    )

    w1 = MockWidget(Vector2(0, 0), Vector2(50, 20))
    w2 = MockWidget(Vector2(0, 0), Vector2(50, 20))

    container.add_child(w1)
    container.add_child(w2)

    container.layout(MagicMock(spec=UIRenderer))

    # W1 at top (0,0 relative to container)
    assert w1.rect.y == 0

    # W2 below W1 + spacing (20 + 10 = 30)
    assert w2.rect.y == 30


def test_box_layout_horizontal_alignment_center():
    """
    Unit Test: Horizontal Layout with Center Alignment
    Verifies children are centered within the container.
    """
    # Container Width 200
    container = BoxContainer(
        Vector2(0, 0),
        Vector2(200, 50),
        direction=LayoutDirection.HORIZONTAL,
        alignment=LayoutAlignment.CENTER,
        spacing=0,
    )

    # Children total width = 50 + 50 = 100
    w1 = MockWidget(Vector2(0, 0), Vector2(50, 20))
    w2 = MockWidget(Vector2(0, 0), Vector2(50, 20))

    container.add_child(w1)
    container.add_child(w2)

    container.layout(MagicMock(spec=UIRenderer))

    # Total Used = 100
    # Remaining = 100
    # Start Offset = 50

    assert w1.rect.x == 50
    assert w2.rect.x == 100  # 50 + 50


def test_box_layout_measures_children_before_stacking():
    """BoxContainer.layout() must measure() auto-sizing children (e.g. Label)
    before reading their rect for stacking math, not their construction-time
    placeholder size (regression for the render()-time-mutation bug)."""
    container = BoxContainer(
        Vector2(0, 0), Vector2(200, 200), direction=LayoutDirection.VERTICAL, spacing=0
    )

    label1 = Label("short")
    label2 = Label("a much longer label")
    container.add_child(label1)
    container.add_child(label2)

    # Both labels start at their construction-time placeholder size (0, 0) --
    # nothing has ever rendered them yet.
    assert label1.rect.height == 0
    assert label2.rect.height == 0

    renderer = MagicMock(spec=UIRenderer)
    renderer.get_text_size.side_effect = lambda text, size: (len(text) * 8, 20)

    container.layout(renderer)

    # Sibling stacking must reflect the real measured height (20), not the
    # placeholder (0) -- label2 sits directly below label1's real height.
    assert label1.rect.height == 20
    assert label2.rect.y == 20
