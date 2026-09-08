"""UIManager drives the layout pass and honours a live theme swap.

These are the integration checks the older UI suite lacked: every existing
test exercised a widget, a constraint, or a container in isolation, so two
defects -- constraints that were never applied at runtime, and a theme
snapshotted per element at construction -- sat under a green suite.
"""

from unittest.mock import MagicMock

from pyguara.common.types import Color, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.window import WindowResizeEvent
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.components.button import Button
from pyguara.ui.constraints import create_centered_constraints, create_fill_constraints
from pyguara.ui.manager import UIManager
from pyguara.ui.theme import UITheme, set_theme
from pyguara.ui.theme_presets import Themes


class Box(UIElement):
    def render(self, renderer: UIRenderer) -> None:
        for child in self.children:
            if child.visible:
                child.render(renderer)


def _manager(width: int = 800, height: int = 600) -> UIManager:
    mgr = UIManager(EventDispatcher())
    mgr.set_screen_size(width, height)
    return mgr


def test_manager_applies_root_constraints_on_render() -> None:
    """A constrained root is positioned against the screen rect by the
    manager's own layout pass -- no manual apply_layout()/layout() call."""
    mgr = _manager()
    root = Box(Vector2(0, 0), Vector2(10, 10))
    root.constraints = create_fill_constraints(margin=20)
    mgr.add_element(root)

    mgr.render(MagicMock(spec=UIRenderer))

    assert (root.rect.x, root.rect.y) == (20, 20)
    assert (root.rect.width, root.rect.height) == (760, 560)


def test_manager_applies_nested_constraints() -> None:
    """Constraints on a child resolve against the parent's content rect."""
    mgr = _manager()
    parent = Box(Vector2(0, 0), Vector2(400, 400))
    parent.constraints = create_fill_constraints()
    child = Box(Vector2(0, 0), Vector2(10, 10))
    child.constraints = create_centered_constraints(
        width_percent=0.5, height_percent=0.5
    )
    parent.add_child(child)
    mgr.add_element(parent)

    mgr.render(MagicMock(spec=UIRenderer))

    # parent fills 800x600; child is 50% centred -> 400x300 at (200, 150).
    assert (child.rect.width, child.rect.height) == (400, 300)
    assert (child.rect.x, child.rect.y) == (200, 150)


def test_layout_pass_is_dirty_gated() -> None:
    """Layout runs when something changed, not on every render."""
    mgr = _manager()
    root = Box(Vector2(0, 0), Vector2(10, 10))
    root.constraints = create_fill_constraints()
    mgr.add_element(root)

    r = MagicMock(spec=UIRenderer)
    mgr.render(r)  # dirty from add_element -> lays out
    assert root.rect.width == 800

    # Manually stomp the rect; a plain re-render must NOT re-run layout.
    root.rect.width = 1
    mgr.render(r)
    assert root.rect.width == 1

    # invalidate_layout() re-arms the pass.
    mgr.invalidate_layout()
    mgr.render(r)
    assert root.rect.width == 800


def test_resize_event_relayouts() -> None:
    """A WindowResizeEvent updates the screen rect and re-lays out."""
    dispatcher = EventDispatcher()
    mgr = UIManager(dispatcher)
    mgr.set_screen_size(800, 600)
    root = Box(Vector2(0, 0), Vector2(10, 10))
    root.constraints = create_fill_constraints()
    mgr.add_element(root)
    mgr.render(MagicMock(spec=UIRenderer))
    assert root.rect.width == 800

    dispatcher.dispatch(WindowResizeEvent(width=1024, height=768))
    mgr.render(MagicMock(spec=UIRenderer))
    assert (root.rect.width, root.rect.height) == (1024, 768)


def test_layout_skipped_without_screen_size(caplog) -> None:
    """With no screen size yet, a constrained tree is left alone and warns."""
    mgr = UIManager(EventDispatcher())  # no set_screen_size()
    root = Box(Vector2(5, 5), Vector2(10, 10))
    root.constraints = create_fill_constraints()
    mgr.add_element(root)

    mgr.render(MagicMock(spec=UIRenderer))

    assert (root.rect.x, root.rect.width) == (5, 10)  # untouched
    assert any("screen size unknown" in r.message for r in caplog.records)


def test_theme_swap_reskins_existing_element() -> None:
    """set_theme() after a widget is built changes what it renders with."""
    original = UITheme()
    set_theme(original)
    try:
        btn = Button("OK", Vector2(0, 0))
        assert btn.theme.colors.primary == original.colors.primary

        set_theme(Themes.CYBERPUNK)
        assert btn.theme.colors.primary == Color(255, 0, 255)

        r = MagicMock(spec=UIRenderer)
        r.get_text_size.return_value = (10, 10)
        btn.render(r)
        # First draw_rect is the background, in the new theme's primary.
        first_fill = r.draw_rect.call_args_list[0]
        assert first_fill.args[1] == Color(255, 0, 255)
    finally:
        set_theme(original)


def test_theme_presets_are_copies() -> None:
    """Mutating a preset does not corrupt it for the next reader."""
    Themes.DARK.colors.primary = Color(1, 2, 3)
    assert Themes.DARK.colors.primary != Color(1, 2, 3)
