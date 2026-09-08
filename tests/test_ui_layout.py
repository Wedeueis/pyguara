from unittest.mock import MagicMock

from pyguara.common.types import Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.text import Label
from pyguara.ui.components.widget import Widget
from pyguara.ui.layout import BoxContainer
from pyguara.ui.types import LayoutAlignment, LayoutDirection

SCREEN = Rect(0, 0, 800, 600)


class MockWidget(Widget):
    def render(self, r):
        pass


def _renderer():
    return MagicMock(spec=UIRenderer)


def test_box_layout_vertical():
    """Vertical Box Layout stacks children top to bottom with spacing."""
    container = BoxContainer(
        Vector2(0, 0), Vector2(100, 200), direction=LayoutDirection.VERTICAL, spacing=10
    )

    w1 = MockWidget(Vector2(0, 0), Vector2(50, 20))
    w2 = MockWidget(Vector2(0, 0), Vector2(50, 20))

    container.add_child(w1)
    container.add_child(w2)

    container.layout(SCREEN, _renderer())

    # W1 at top (0,0 relative to container)
    assert w1.rect.y == 0

    # W2 below W1 + spacing (20 + 10 = 30)
    assert w2.rect.y == 30


def test_box_layout_horizontal_alignment_center():
    """Horizontal layout with CENTER alignment centres the child run."""
    container = BoxContainer(
        Vector2(0, 0),
        Vector2(200, 50),
        direction=LayoutDirection.HORIZONTAL,
        alignment=LayoutAlignment.CENTER,
        spacing=0,
    )

    w1 = MockWidget(Vector2(0, 0), Vector2(50, 20))
    w2 = MockWidget(Vector2(0, 0), Vector2(50, 20))

    container.add_child(w1)
    container.add_child(w2)

    container.layout(SCREEN, _renderer())

    # Total used = 100, remaining = 100, start offset = 50
    assert w1.rect.x == 50
    assert w2.rect.x == 100


def test_box_layout_measures_children_before_stacking():
    """layout() must measure() auto-sizing children (e.g. Label) before it
    reads their rect for stacking, not their construction-time placeholder."""
    container = BoxContainer(
        Vector2(0, 0), Vector2(200, 200), direction=LayoutDirection.VERTICAL, spacing=0
    )

    label1 = Label("short")
    label2 = Label("a much longer label")
    container.add_child(label1)
    container.add_child(label2)

    assert label1.rect.height == 0
    assert label2.rect.height == 0

    renderer = _renderer()
    renderer.get_text_size.side_effect = lambda text, size: (len(text) * 8, 20)

    container.layout(SCREEN, renderer)

    assert label1.rect.height == 20
    assert label2.rect.y == 20


def test_box_layout_skips_hidden_children_in_stacking_and_render():
    """A hidden child takes no space in the stack and is not drawn."""
    container = BoxContainer(
        Vector2(0, 0), Vector2(100, 200), direction=LayoutDirection.VERTICAL, spacing=10
    )
    top = MockWidget(Vector2(0, 0), Vector2(50, 20))
    hidden = MockWidget(Vector2(0, 0), Vector2(50, 20))
    hidden.visible = False
    bottom = MockWidget(Vector2(0, 0), Vector2(50, 20))
    for c in (top, hidden, bottom):
        container.add_child(c)

    container.layout(SCREEN, _renderer())

    # `bottom` sits directly under `top` (+spacing); the hidden widget is
    # not counted.
    assert bottom.rect.y == 30

    drawn = []
    for c in (top, hidden, bottom):
        c.render = lambda r, c=c: drawn.append(c)
    container.render(_renderer())
    assert drawn == [top, bottom]


def test_box_layout_stretch_fills_cross_axis():
    """STRETCH alignment makes each child fill the container's cross axis."""
    container = BoxContainer(
        Vector2(10, 10),
        Vector2(120, 300),
        direction=LayoutDirection.VERTICAL,
        alignment=LayoutAlignment.STRETCH,
        spacing=0,
    )
    a = MockWidget(Vector2(0, 0), Vector2(30, 20))
    b = MockWidget(Vector2(0, 0), Vector2(80, 20))
    container.add_child(a)
    container.add_child(b)

    container.layout(SCREEN, _renderer())

    for child in (a, b):
        assert child.rect.x == 10
        assert child.rect.width == 120


def test_box_layout_applies_own_constraints_then_stacks():
    """A container with constraints resolves its own rect against the
    available rect before positioning children inside it."""
    from pyguara.ui.constraints import create_centered_constraints

    container = BoxContainer(
        Vector2(0, 0), Vector2(100, 100), direction=LayoutDirection.VERTICAL, spacing=0
    )
    container.constraints = create_centered_constraints(
        width_percent=0.5, height_percent=0.5
    )
    child = MockWidget(Vector2(0, 0), Vector2(20, 20))
    container.add_child(child)

    container.layout(SCREEN, _renderer())

    # 50% of 800x600 -> 400x300, centred -> origin (200, 150).
    assert (container.rect.x, container.rect.y) == (200, 150)
    assert (container.rect.width, container.rect.height) == (400, 300)
    # Child stacked at the container's (post-constraint) top.
    assert child.rect.y == 150


def test_nested_box_containers_resolve():
    """A BoxContainer nested in another gets its own children stacked."""
    outer = BoxContainer(
        Vector2(0, 0), Vector2(200, 400), direction=LayoutDirection.VERTICAL, spacing=0
    )
    inner = BoxContainer(
        Vector2(0, 0), Vector2(200, 100), direction=LayoutDirection.VERTICAL, spacing=5
    )
    leaf1 = MockWidget(Vector2(0, 0), Vector2(20, 10))
    leaf2 = MockWidget(Vector2(0, 0), Vector2(20, 10))
    inner.add_child(leaf1)
    inner.add_child(leaf2)
    outer.add_child(MockWidget(Vector2(0, 0), Vector2(20, 30)))
    outer.add_child(inner)

    outer.layout(SCREEN, _renderer())

    # inner is the 2nd child of outer: y = 30 (first child height) + 0 spacing
    assert inner.rect.y == 30
    # leaf1/leaf2 stacked inside inner, starting at inner's y
    assert leaf1.rect.y == 30
    assert leaf2.rect.y == 45  # 30 + 10 + 5 spacing
