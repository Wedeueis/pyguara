"""Theme styling fields that widgets actually consume.

`BorderScheme.radius` was declared, serialized, and set by presets while
reaching **no widget at all** -- a theme could ask for rounded corners and
every widget drew square ones, silently. The protocol and all three UI
renderers already accepted `border_radius`; the only missing link was that
no widget passed it. #49 calls this out as a shipped surface that is
quietly wrong rather than a missing feature.

These tests assert on the call the widget makes to the renderer rather
than on pixels: what went wrong was a value never being *passed*, and a
recording renderer is the shortest path to catching that again.
"""

from __future__ import annotations

import copy
from unittest.mock import MagicMock

import pytest

from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.button import Button
from pyguara.ui.components.checkbox import Checkbox
from pyguara.ui.components.panel import Panel
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.text_input import TextInput
from pyguara.ui.theme import get_theme, set_theme


@pytest.fixture
def rounded_theme():
    """The active theme with a non-zero corner radius, then put back."""
    previous = get_theme()
    theme = copy.deepcopy(previous)
    theme.borders.radius = 8
    set_theme(theme)
    yield theme
    set_theme(previous)


@pytest.fixture
def square_theme():
    """The active theme with radius explicitly 0, then put back."""
    previous = get_theme()
    theme = copy.deepcopy(previous)
    theme.borders.radius = 0
    set_theme(theme)
    yield theme
    set_theme(previous)


def _renderer() -> MagicMock:
    renderer = MagicMock(spec=UIRenderer)
    renderer.get_text_size.return_value = (10, 10)
    return renderer


def _radii(widget) -> list[int]:
    """Every `border_radius` the widget passed to `draw_rect`."""
    renderer = _renderer()
    widget.render(renderer)
    return [
        call.kwargs["border_radius"]
        for call in renderer.draw_rect.call_args_list
        if "border_radius" in call.kwargs
    ]


def _widgets() -> list[tuple[str, object]]:
    """One of each stock widget that draws its own chrome.

    Built fresh per test rather than shared: `UIElement.__init__` resolves
    the theme at construction, so a widget built under one theme would not
    see another.
    """
    return [
        ("Button", Button("ok", Vector2(0, 0))),
        ("Panel", Panel(Vector2(0, 0), Vector2(80, 40))),
        ("Checkbox", Checkbox("on", Vector2(0, 0))),
        ("TextInput", TextInput(Vector2(0, 0))),
        ("ProgressBar", ProgressBar(Vector2(0, 0))),
    ]


@pytest.mark.unit
class TestBorderRadiusReachesWidgets:
    def test_every_stock_widget_passes_the_themes_radius(self, rounded_theme):
        """The regression this file exists for: the field is consumed."""
        for name, widget in _widgets():
            radii = _radii(widget)
            assert radii, f"{name} passed no border_radius at all"
            assert all(r == 8 for r in radii), f"{name} passed {radii}, expected 8s"

    def test_a_zero_radius_keeps_corners_square(self, square_theme):
        """Rendering is unchanged for any theme that does not ask for a
        radius, which is every preset today -- so this is additive."""
        for name, widget in _widgets():
            assert all(r == 0 for r in _radii(widget)), name

    def test_changing_the_theme_restyles_existing_widgets(self, square_theme):
        """`UIElement.theme` resolves live, so a `set_theme()` after
        construction must reach widgets already built."""
        button = Button("ok", Vector2(0, 0))
        assert _radii(button) == [0, 0]

        rounded = copy.deepcopy(square_theme)
        rounded.borders.radius = 12
        set_theme(rounded)

        assert _radii(button) == [12, 12]

    def test_the_progress_fill_stays_square(self, rounded_theme):
        """Deliberate: a rounded fill inside a rounded track leaves a
        visible gap at low values, which is why real progress bars round
        only the track. The track and frame are rounded; the fill is not."""
        bar = ProgressBar(Vector2(0, 0), value=0.5)
        renderer = _renderer()
        bar.render(renderer)

        rounded = [
            c for c in renderer.draw_rect.call_args_list if "border_radius" in c.kwargs
        ]
        assert len(rounded) == 2  # track + frame, not the fill
        assert len(renderer.draw_rect.call_args_list) == 3


@pytest.mark.unit
class TestBorderWidthStillApplies:
    def test_radius_does_not_displace_the_border_width(self, rounded_theme):
        """Both come from `BorderScheme`; wiring one must not drop the
        other."""
        button = Button("ok", Vector2(0, 0))
        renderer = _renderer()
        button.render(renderer)

        widths = [c.kwargs.get("width") for c in renderer.draw_rect.call_args_list]
        assert rounded_theme.borders.width in widths


@pytest.fixture
def shadow_theme():
    """The active theme with shadows on, then put back."""
    previous = get_theme()
    theme = copy.deepcopy(previous)
    theme.shadows.enabled = True
    theme.shadows.offset_x = 3
    theme.shadows.offset_y = 4
    set_theme(theme)
    yield theme
    set_theme(previous)


@pytest.mark.unit
class TestShadowSchemeReachesWidgets:
    def test_shadows_are_off_by_default(self):
        """Every preset leaves them off, so a widget costs nothing until a
        theme opts in -- and default rendering is unchanged."""
        previous = get_theme()
        try:
            theme = copy.deepcopy(previous)
            theme.shadows.enabled = False
            set_theme(theme)

            renderer = _renderer()
            Button("ok", Vector2(10, 10)).render(renderer)

            # Face + border only; no third rect underneath them.
            assert len(renderer.draw_rect.call_args_list) == 2
        finally:
            set_theme(previous)

    def test_a_raised_widget_casts_a_shadow_when_enabled(self, shadow_theme):
        renderer = _renderer()
        Button("ok", Vector2(10, 20)).render(renderer)

        first = renderer.draw_rect.call_args_list[0]
        rect, color = first.args[0], first.args[1]
        assert (rect.x, rect.y) == (13, 24)  # offset by (3, 4)
        assert color == shadow_theme.shadows.color

    def test_the_shadow_is_drawn_under_the_face(self, shadow_theme):
        """Drawn first, so the widget's own face covers the overlap."""
        renderer = _renderer()
        panel = Panel(Vector2(0, 0), Vector2(60, 30))
        panel.render(renderer)

        shadow, face = renderer.draw_rect.call_args_list[:2]
        assert shadow.args[1] == shadow_theme.shadows.color
        assert face.args[0].x == 0  # the face itself, un-offset

    def test_recessed_widgets_do_not_cast_shadows(self, shadow_theme):
        """A text field, a progress track and a checkbox box are inset into
        the surface; a shadow would claim a depth they do not have."""
        for widget in (
            TextInput(Vector2(0, 0)),
            ProgressBar(Vector2(0, 0)),
            Checkbox("on", Vector2(0, 0)),
        ):
            renderer = _renderer()
            widget.render(renderer)
            colors = [c.args[1] for c in renderer.draw_rect.call_args_list]
            assert shadow_theme.shadows.color not in colors, type(widget).__name__

    def test_the_shadow_follows_the_corner_radius(self, shadow_theme):
        """A square shadow under a rounded face would show at the corners."""
        rounded = copy.deepcopy(shadow_theme)
        rounded.borders.radius = 6
        set_theme(rounded)

        renderer = _renderer()
        Button("ok", Vector2(0, 0)).render(renderer)

        assert renderer.draw_rect.call_args_list[0].kwargs["border_radius"] == 6

    def test_blur_is_declared_but_consumed_nowhere(self):
        """Pinned deliberately, not aspirationally. A soft shadow is not
        reachable through the renderer's rectangle primitives, so `blur`
        stays documented-as-unconsumed rather than silently ignored. If a
        layered approximation ever lands, this test should fail and be
        rewritten -- that is the point of it."""
        previous = get_theme()
        try:
            theme = copy.deepcopy(previous)
            theme.shadows.enabled = True
            theme.shadows.blur = 12
            set_theme(theme)

            renderer = _renderer()
            Button("ok", Vector2(0, 0)).render(renderer)

            # One shadow rect, regardless of blur: no layered falloff.
            shadow_calls = [
                c
                for c in renderer.draw_rect.call_args_list
                if c.args[1] == theme.shadows.color
            ]
            assert len(shadow_calls) == 1
        finally:
            set_theme(previous)
