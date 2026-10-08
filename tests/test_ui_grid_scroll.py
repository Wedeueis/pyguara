"""Grid layout, the scroll viewport, and automatic layout invalidation."""

from unittest.mock import MagicMock

import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.input import MouseWheelEvent
from pyguara.graphics.backends.headless_renderer import HeadlessUIRenderer
from pyguara.graphics.protocols import UIRenderer
from pyguara.input.events import OnMouseEvent
from pyguara.ui.base import Scrollable, UIElement
from pyguara.ui.layout import (
    BoxContainer,
    GridContainer,
    ScrollContainer,
)
from pyguara.ui.manager import UIManager
from pyguara.ui.types import LayoutAlignment, LayoutDirection


class Slot(UIElement):
    """A fixed-size leaf that records whether it was drawn."""

    def __init__(self, width: int = 40, height: int = 40, name: str = "slot") -> None:
        super().__init__(Vector2(0, 0), Vector2(width, height))
        self.name = name
        self.drawn = False
        self.focusable = True

    def render(self, renderer: UIRenderer) -> None:
        self.drawn = True
        renderer.draw_rect(self.rect, Color(255, 255, 255))


def _renderer() -> HeadlessUIRenderer:
    return HeadlessUIRenderer()


# -- GridContainer --


def test_children_flow_left_to_right_and_wrap():
    grid = GridContainer(Vector2(0, 0), Vector2(300, 300), columns=3, spacing=10)
    slots = [Slot(name=str(i)) for i in range(5)]
    for slot in slots:
        grid.add_child(slot)

    grid.layout(Rect(0, 0, 300, 300), _renderer())

    # (300 - 2*10) / 3 = 93 per column.
    assert [s.rect.x for s in slots[:3]] == [0, 103, 206]
    assert [s.rect.y for s in slots[:3]] == [0, 0, 0]
    assert slots[3].rect.x == 0
    assert slots[3].rect.y == slots[0].rect.height + 10


def test_stretch_fills_each_cell_because_that_is_what_a_slot_grid_means():
    grid = GridContainer(Vector2(0, 0), Vector2(300, 300), columns=3, spacing=0)
    slot = Slot(width=10, height=10)
    grid.add_child(slot)

    grid.layout(Rect(0, 0, 300, 300), _renderer())

    assert slot.rect.width == 100


def test_without_stretch_each_child_keeps_its_size_and_is_centred():
    grid = GridContainer(
        Vector2(0, 0),
        Vector2(300, 300),
        columns=3,
        spacing=0,
        alignment=LayoutAlignment.CENTER,
    )
    slot = Slot(width=10, height=10)
    grid.add_child(slot)

    grid.layout(Rect(0, 0, 300, 300), _renderer())

    assert slot.rect.width == 10
    assert slot.rect.x == 45  # (100 - 10) // 2


def test_a_row_is_as_tall_as_its_tallest_child():
    grid = GridContainer(Vector2(0, 0), Vector2(300, 300), columns=2, spacing=0)
    short, tall, next_row = Slot(height=20), Slot(height=80), Slot(height=20)
    for slot in (short, tall, next_row):
        grid.add_child(slot)

    grid.layout(Rect(0, 0, 300, 300), _renderer())

    assert next_row.rect.y == 80


def test_a_fixed_row_height_makes_square_slots_regardless_of_content():
    grid = GridContainer(
        Vector2(0, 0), Vector2(300, 300), columns=2, spacing=0, row_height=64
    )
    tall, next_row = Slot(height=200), Slot()
    grid.add_child(tall)
    grid.add_child(Slot())
    grid.add_child(next_row)

    grid.layout(Rect(0, 0, 300, 300), _renderer())

    assert tall.rect.height == 64
    assert next_row.rect.y == 64


def test_zero_columns_is_refused_rather_than_dividing_by_zero():
    with pytest.raises(ValueError, match="at least 1 column"):
        GridContainer(Vector2(0, 0), Vector2(100, 100), columns=0)


def test_an_invisible_child_takes_no_cell():
    grid = GridContainer(Vector2(0, 0), Vector2(300, 300), columns=2, spacing=0)
    hidden, after = Slot(), Slot()
    grid.add_child(hidden)
    grid.add_child(after)
    hidden.visible = False

    grid.layout(Rect(0, 0, 300, 300), _renderer())

    assert after.rect.x == 0


def test_padding_shrinks_the_cells():
    from pyguara.ui.constraints import Padding

    grid = GridContainer(Vector2(0, 0), Vector2(300, 300), columns=2, spacing=0)
    grid.padding = Padding(left=10, right=10, top=10, bottom=10)
    slot = Slot()
    grid.add_child(slot)

    grid.layout(Rect(0, 0, 300, 300), _renderer())

    assert slot.rect.x == 10
    assert slot.rect.width == 140  # (300 - 20) / 2


def test_a_container_in_a_cell_lays_out_against_its_cell():
    grid = GridContainer(Vector2(0, 0), Vector2(400, 400), columns=2, spacing=0)
    box = BoxContainer(
        Vector2(0, 0), Vector2(10, 10), direction=LayoutDirection.VERTICAL, spacing=0
    )
    inner = Slot()
    box.add_child(inner)
    grid.add_child(Slot())
    grid.add_child(box)

    grid.layout(Rect(0, 0, 400, 400), _renderer())

    assert box.rect.x == 200
    assert inner.rect.y == box.rect.y


def test_content_height_reports_the_extent_not_the_window():
    grid = GridContainer(Vector2(0, 0), Vector2(100, 50), columns=1, spacing=0)
    for _ in range(4):
        grid.add_child(Slot(height=40))

    grid.layout(Rect(0, 0, 100, 50), _renderer())

    assert grid.content_height() == 160


# -- ScrollContainer --


def _scroll_with_rows(rows: int, row_height: int = 40, window: int = 100):
    """A viewport holding `rows` leaf rows directly, already laid out."""
    scroll = ScrollContainer(Vector2(0, 0), Vector2(100, window), scroll_speed=20.0)
    slots = [Slot(height=row_height, name=str(i)) for i in range(rows)]
    for slot in slots:
        scroll.add_child(slot)
    scroll.layout(Rect(0, 0, 100, window), _renderer())
    return scroll, slots


def test_content_taller_than_the_window_can_scroll():
    scroll, _ = _scroll_with_rows(10)

    assert scroll.content_extent == 400
    assert scroll.max_offset == 300


def test_content_that_fits_cannot_scroll():
    scroll, _ = _scroll_with_rows(2)

    assert scroll.max_offset == 0
    assert scroll.scroll_by(0, -1) is False


def test_a_wheel_notch_away_from_the_user_scrolls_down():
    """Getting this backwards is the single most noticeable bug a scroll
    view can have."""
    scroll, _ = _scroll_with_rows(10)

    assert scroll.scroll_by(0, -1) is True

    assert scroll.offset == 20.0


def test_scrolling_moves_the_children_so_clicks_land_where_the_pixels_are():
    """Translating at draw time would leave every rect unscrolled, so
    clicking the fifth slot would select the second."""
    scroll, slots = _scroll_with_rows(10)
    before = slots[5].rect.y

    scroll.scroll_by(0, -2)
    scroll.layout(Rect(0, 0, 100, 100), _renderer())

    # Two notches at 20 px is 40 px, one row: row 1 now sits where row 0 was.
    assert slots[5].rect.y == before - 40
    assert scroll.hit_test(Vector2(50, 10)) is slots[1]


def test_a_nested_child_is_translated_too():
    """Leaving a grandchild behind is how a scrolled list hit-tests against
    where it used to be."""
    scroll = ScrollContainer(Vector2(0, 0), Vector2(100, 100), scroll_speed=20.0)
    box = BoxContainer(
        Vector2(0, 0),
        Vector2(100, 400),
        direction=LayoutDirection.VERTICAL,
        spacing=0,
    )
    slots = [Slot(height=40) for _ in range(10)]
    for slot in slots:
        box.add_child(slot)
    scroll.add_child(box)
    scroll.layout(Rect(0, 0, 100, 100), _renderer())
    assert box.rect.y == 0

    scroll.scroll_by(0, -1)
    scroll.layout(Rect(0, 0, 100, 100), _renderer())

    assert box.rect.y == -20
    assert slots[0].rect.y == -20
    assert scroll.hit_test(Vector2(50, 30)) is slots[1]


def test_a_box_container_inside_gets_the_whole_content_slot():
    """It arranges itself in there; the viewport does not try to space or
    align anything itself."""
    scroll = ScrollContainer(Vector2(0, 0), Vector2(100, 100))
    box = BoxContainer(Vector2(0, 0), Vector2(10, 250))
    scroll.add_child(box)

    scroll.layout(Rect(0, 0, 100, 100), _renderer())

    assert box.rect.x == 0
    assert box.rect.width == 100
    assert box.rect.height == 250
    assert scroll.content_extent == 250


def test_laying_out_twice_does_not_drift():
    """An element without constraints keeps its own rect, so a viewport
    that merely translated what it found would translate it again next
    frame and walk the contents off screen."""
    scroll, slots = _scroll_with_rows(10)
    scroll.scroll_by(0, -3)

    scroll.layout(Rect(0, 0, 100, 100), _renderer())
    once = [slot.rect.y for slot in slots]
    scroll.layout(Rect(0, 0, 100, 100), _renderer())

    assert [slot.rect.y for slot in slots] == once


def test_the_offset_is_clamped_to_both_ends():
    scroll, _ = _scroll_with_rows(10)

    scroll.offset = -500
    assert scroll.offset == 0.0

    scroll.offset = 99999
    assert scroll.offset == 300.0


def test_scroll_to_end_goes_to_the_bottom():
    scroll, _ = _scroll_with_rows(10)

    scroll.scroll_to_end()

    assert scroll.offset == scroll.max_offset


def test_shrinking_content_re_clamps_rather_than_leaving_a_blank_viewport():
    """A filtered inventory or a cleared log leaves the offset past an end
    that no longer exists."""
    scroll, slots = _scroll_with_rows(10)
    scroll.scroll_to_end()
    assert scroll.offset == 300.0

    for slot in slots[2:]:
        slot.visible = False
    scroll.layout(Rect(0, 0, 100, 100), _renderer())

    assert scroll.offset == 0.0
    assert scroll.max_offset == 0


def test_an_empty_viewport_has_no_extent():
    scroll = ScrollContainer(Vector2(0, 0), Vector2(100, 100))

    scroll.layout(Rect(0, 0, 100, 100), _renderer())

    assert scroll.content_extent == 0
    assert scroll.max_offset == 0


def test_a_horizontal_viewport_scrolls_sideways():
    scroll = ScrollContainer(
        Vector2(0, 0), Vector2(100, 50), scroll_speed=10.0, horizontal=True
    )
    slots = [Slot(width=40, height=40) for _ in range(10)]
    for slot in slots:
        scroll.add_child(slot)
    scroll.layout(Rect(0, 0, 100, 50), _renderer())

    assert scroll.content_extent == 400
    assert scroll.scroll_by(-1, 0) is True
    scroll.layout(Rect(0, 0, 100, 50), _renderer())

    assert scroll.offset == 10.0
    assert slots[0].rect.x == -10


def test_rendering_clips_to_the_viewport():
    scroll, _ = _scroll_with_rows(10)
    renderer = MagicMock(spec=UIRenderer)

    scroll.render(renderer)

    renderer.push_clip.assert_called_once_with(scroll.rect)
    renderer.pop_clip.assert_called_once()


def test_the_clip_is_popped_even_when_a_child_raises():
    """Otherwise the clip stays set and silently truncates the rest of the
    frame, a long way from the cause."""
    scroll, slots = _scroll_with_rows(3)
    renderer = MagicMock(spec=UIRenderer)

    def explode(_renderer):
        raise RuntimeError("a widget's own bug")

    slots[0].render = explode

    with pytest.raises(RuntimeError):
        scroll.render(renderer)

    renderer.pop_clip.assert_called_once()


def test_a_scroll_container_is_a_scrollable():
    assert isinstance(ScrollContainer(Vector2(0, 0), Vector2(10, 10)), Scrollable)


# -- Wheel routing through UIManager --


def _manager_with_scroll():
    dispatcher = EventDispatcher()
    manager = UIManager(dispatcher)
    manager.set_screen_size(400, 300)
    scroll, slots = _scroll_with_rows(10)
    manager.add_element(scroll)
    return dispatcher, manager, scroll, slots


def test_the_wheel_reaches_a_viewport_under_the_cursor():
    dispatcher, _manager, scroll, _ = _manager_with_scroll()
    dispatcher.dispatch(
        OnMouseEvent(position=(50, 50), button=0, is_down=False, is_motion=True)
    )

    dispatcher.dispatch(MouseWheelEvent(x=0.0, y=-1.0))

    assert scroll.offset == 20.0


def test_the_wheel_over_a_button_inside_a_list_still_scrolls_the_list():
    """It walks *up* from whatever it hit, which is what every UI toolkit
    does and what a player expects."""
    dispatcher, _manager, scroll, slots = _manager_with_scroll()
    # x=50 lands on the slot itself; BoxContainer centres a non-stretch
    # child on the cross axis, so a 40-wide slot in a 100-wide box starts
    # at x=30.
    dispatcher.dispatch(
        OnMouseEvent(position=(50, 20), button=0, is_down=False, is_motion=True)
    )
    assert scroll.hit_test(Vector2(50, 20)) is slots[0]

    dispatcher.dispatch(MouseWheelEvent(x=0.0, y=-1.0))

    assert scroll.offset == 20.0


def test_the_wheel_outside_the_viewport_does_nothing():
    dispatcher, _manager, scroll, _ = _manager_with_scroll()
    dispatcher.dispatch(
        OnMouseEvent(position=(350, 250), button=0, is_down=False, is_motion=True)
    )

    dispatcher.dispatch(MouseWheelEvent(x=0.0, y=-1.0))

    assert scroll.offset == 0.0


def test_a_zero_delta_is_ignored():
    dispatcher, _manager, scroll, _ = _manager_with_scroll()
    dispatcher.dispatch(
        OnMouseEvent(position=(50, 50), button=0, is_down=False, is_motion=True)
    )

    dispatcher.dispatch(MouseWheelEvent(x=0.0, y=0.0))

    assert scroll.offset == 0.0


# -- Automatic layout invalidation --


def test_hiding_an_element_invalidates_the_layout():
    """`element.visible = False` silently left a gap until something else
    happened to invalidate -- #49's P3 row."""
    dispatcher = EventDispatcher()
    manager = UIManager(dispatcher)
    manager.set_screen_size(400, 300)
    box = BoxContainer(Vector2(0, 0), Vector2(100, 100))
    slot = Slot()
    box.add_child(slot)
    manager.add_element(box)
    manager.render(_renderer())
    assert not manager._layout_dirty

    slot.visible = False

    assert manager._layout_dirty


def test_setting_visible_to_the_same_value_invalidates_nothing():
    dispatcher = EventDispatcher()
    manager = UIManager(dispatcher)
    manager.set_screen_size(400, 300)
    slot = Slot()
    manager.add_element(slot)
    manager.render(_renderer())

    slot.visible = True

    assert not manager._layout_dirty


def test_showing_a_hidden_element_invalidates_too():
    dispatcher = EventDispatcher()
    manager = UIManager(dispatcher)
    manager.set_screen_size(400, 300)
    slot = Slot()
    slot.visible = False
    manager.add_element(slot)
    manager.render(_renderer())

    slot.visible = True

    assert manager._layout_dirty
