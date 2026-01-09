from pyguara.ui.layout import BoxContainer
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

    container.layout()

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

    container.layout()

    # Total Used = 100
    # Remaining = 100
    # Start Offset = 50

    assert w1.rect.x == 50
    assert w2.rect.x == 100  # 50 + 50
