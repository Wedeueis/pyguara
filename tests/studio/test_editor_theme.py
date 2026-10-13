"""The editor's theme and UI scale.

The scale is the part worth testing. Every size in an ImGui style is in
pixels and the built-in font is a 13px bitmap meant for a debug overlay,
so an editor comfortable at 1280 wide is a squint at 4K -- which is how it
was reported. The rebuild-then-scale approach is also easy to get subtly
wrong: `scale_all_sizes` multiplies the style it is called on, so scaling
an already-scaled style compounds.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.di.container import DIContainer  # noqa: E402
from pyguara.editor.layer import EditorLayer  # noqa: E402
from pyguara.editor.theme import (  # noqa: E402
    MAX_SCALE,
    MIN_SCALE,
    apply_theme,
    scale_for,
)


@pytest.fixture
def gui() -> Iterator[None]:
    """An ImGui context with no renderer and no GL."""
    context = imgui.create_context()
    imgui.set_current_context(context)
    yield
    imgui.destroy_context(context)


class TestScaleFor:
    """Deriving a scale from the window."""

    @pytest.mark.parametrize(
        ("width", "height", "expected"),
        [
            (1280, 720, 1.0),
            (1600, 900, 1.0),
            (1920, 1080, 1.25),
            (2560, 1440, 1.75),
            (3840, 2160, 2.5),
        ],
    )
    def test_known_resolutions(self, width: int, height: int, expected: float) -> None:
        assert scale_for(width, height) == expected

    def test_1080p_scales_up(self) -> None:
        """The reported case. An exact 1.125 falls out of the maths here,
        and `round` is banker's rounding -- it would go *down* to 1.0,
        which is the problem rather than the fix."""
        assert scale_for(1920, 1080) > 1.0

    def test_it_never_shrinks(self) -> None:
        """Below 1.0 the font stops being legible, and a small window
        wants fewer panels rather than smaller text."""
        for width, height in ((800, 600), (640, 480), (320, 240)):
            assert scale_for(width, height) == MIN_SCALE

    def test_it_is_clamped_at_the_top(self) -> None:
        assert scale_for(20000, 20000) == MAX_SCALE

    def test_a_degenerate_window_is_safe(self) -> None:
        """Minimising reports zero, and dividing by it would raise."""
        assert scale_for(0, 0) == MIN_SCALE
        assert scale_for(-1, 100) == MIN_SCALE

    def test_a_wide_short_window_is_not_scaled_by_width_alone(self) -> None:
        """An ultrawide at 1080 tall has no more vertical room than a
        1080p screen, and scaling by width would cost it rows."""
        assert scale_for(3440, 1080) <= scale_for(3440, 1440)

    def test_it_steps_rather_than_drifting(self) -> None:
        """So dragging a window across a monitor boundary does not reflow
        the layout on every pixel."""
        values = {scale_for(width, 1080) for width in range(1800, 2000, 10)}
        assert len(values) <= 2


class TestTheme:
    """The palette applies."""

    def test_it_applies_to_the_current_style(self, gui: None) -> None:
        apply_theme()
        style = imgui.get_style()
        assert style.frame_rounding > 0.0
        assert style.window_rounding > 0.0

    def test_it_is_a_dark_theme(self, gui: None) -> None:
        apply_theme()
        background = imgui.get_style().color_(imgui.Col_.window_bg.value)
        assert background.x < 0.3 and background.y < 0.3 and background.z < 0.3

    def test_text_contrasts_with_the_background(self, gui: None) -> None:
        apply_theme()
        style = imgui.get_style()
        text = style.color_(imgui.Col_.text.value)
        background = style.color_(imgui.Col_.window_bg.value)
        assert text.x - background.x > 0.5

    def test_applying_twice_is_idempotent(self, gui: None) -> None:
        """It is re-applied on every scale change, from scratch."""
        apply_theme()
        first = imgui.get_style().frame_rounding
        apply_theme()
        assert imgui.get_style().frame_rounding == first


class TestLayerScaling:
    """The layer applies the scale, once per change."""

    def test_the_first_frame_sets_a_scale(self, gui: None) -> None:
        layer = EditorLayer(DIContainer())
        try:
            assert layer.ui_scale == 0.0
            layer.build_frame(1920, 1080, dt=1 / 60)
            assert layer.ui_scale == 1.25
        finally:
            layer.release()

    def test_scaling_does_not_compound(self, gui: None) -> None:
        """`scale_all_sizes` multiplies the style it is called on, so a
        style scaled twice is scaled by the square. The theme is rebuilt
        from scratch before each application."""
        layer = EditorLayer(DIContainer())
        try:
            layer.build_frame(1920, 1080, dt=1 / 60)
            imgui.set_current_context(layer._context)
            once = imgui.get_style().frame_rounding

            for _ in range(5):
                layer.build_frame(1920, 1080, dt=1 / 60)
            imgui.set_current_context(layer._context)
            assert imgui.get_style().frame_rounding == once
        finally:
            layer.release()

    def test_returning_to_a_size_returns_to_its_scale(self, gui: None) -> None:
        layer = EditorLayer(DIContainer())
        try:
            layer.build_frame(1920, 1080, dt=1 / 60)
            imgui.set_current_context(layer._context)
            at_1080p = imgui.get_style().frame_rounding

            layer.build_frame(3840, 2160, dt=1 / 60)
            layer.build_frame(1920, 1080, dt=1 / 60)
            imgui.set_current_context(layer._context)
            assert imgui.get_style().frame_rounding == at_1080p
        finally:
            layer.release()

    def test_the_font_is_scaled_too(self, gui: None) -> None:
        """`font_scale_main`, not the removed `io.font_global_scale`:
        ImGui 1.92 rebuilds the atlas at the new size rather than
        stretching a 13px bitmap."""
        layer = EditorLayer(DIContainer())
        try:
            layer.build_frame(3840, 2160, dt=1 / 60)
            imgui.set_current_context(layer._context)
            assert imgui.get_style().font_scale_main == 2.5
        finally:
            layer.release()
