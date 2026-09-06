"""Tests for the render pipeline's viewport maths and graph bookkeeping.

Neither had dedicated tests. The viewport is pure arithmetic and needs no GL
context, so its edge cases are cheap to pin down; the graph's pass list is
plain bookkeeping around a mocked context.
"""

from unittest.mock import MagicMock

import pytest

from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.viewport import Viewport

WIDESCREEN = 16 / 9


def make_pass(name: str) -> MagicMock:
    render_pass = MagicMock()
    render_pass.name = name
    render_pass.enabled = True
    return render_pass


class TestViewportBestFit:
    def test_a_matching_window_fills_completely(self) -> None:
        viewport = Viewport.create_best_fit(1920, 1080, WIDESCREEN)

        assert (viewport.x, viewport.y) == (0, 0)
        assert (viewport.width, viewport.height) == (1920, 1080)

    def test_a_too_wide_window_is_pillarboxed(self) -> None:
        viewport = Viewport.create_best_fit(2000, 1000, 1.0)

        assert viewport.height == 1000
        assert viewport.width == 1000
        assert viewport.x == 500, "bars should be split evenly"

    def test_a_too_tall_window_is_letterboxed(self) -> None:
        viewport = Viewport.create_best_fit(1000, 2000, 1.0)

        assert viewport.width == 1000
        assert viewport.height == 1000
        assert viewport.y == 500, "bars should be split evenly"

    def test_the_fitted_viewport_keeps_the_target_ratio(self) -> None:
        for window in ((1920, 1080), (1024, 768), (640, 1000), (3000, 500)):
            viewport = Viewport.create_best_fit(*window, WIDESCREEN)
            assert abs(viewport.aspect_ratio - WIDESCREEN) < 0.01, window

    def test_the_viewport_never_exceeds_the_window(self) -> None:
        for window in ((1920, 1080), (1024, 768), (640, 1000), (3000, 500)):
            viewport = Viewport.create_best_fit(*window, WIDESCREEN)
            assert viewport.width <= window[0], window
            assert viewport.height <= window[1], window


class TestViewportDegenerateInput:
    """A zero-area window is an ordinary transient state -- minimised, or
    mid-resize -- not a programming error. It used to produce a fabricated
    viewport: `create_best_fit(800, 0, 16/9)` returned a 450px-tall viewport at
    y=-225, because the zero guard substituted a window ratio of 0 and that
    fell through to the letterbox branch.
    """

    def test_a_zero_height_window_yields_a_zero_viewport(self) -> None:
        viewport = Viewport.create_best_fit(800, 0, WIDESCREEN)

        assert (viewport.x, viewport.y, viewport.width, viewport.height) == (0, 0, 0, 0)

    def test_a_zero_width_window_yields_a_zero_viewport(self) -> None:
        viewport = Viewport.create_best_fit(0, 600, WIDESCREEN)

        assert (viewport.width, viewport.height) == (0, 0)

    def test_negative_dimensions_yield_a_zero_viewport(self) -> None:
        viewport = Viewport.create_best_fit(-800, -600, WIDESCREEN)

        assert (viewport.width, viewport.height) == (0, 0)

    def test_a_non_positive_aspect_ratio_is_rejected(self) -> None:
        """Unlike a minimised window, this is a caller error -- and the
        letterbox branch divides by it."""
        with pytest.raises(ValueError, match="must be positive"):
            Viewport.create_best_fit(800, 600, 0.0)

        with pytest.raises(ValueError, match="must be positive"):
            Viewport.create_best_fit(800, 600, -1.5)

    def test_fullscreen_passes_the_window_through(self) -> None:
        viewport = Viewport.create_fullscreen(1280, 720)

        assert (viewport.width, viewport.height) == (1280, 720)


class TestRenderGraphPasses:
    def test_passes_are_returned_in_insertion_order(self) -> None:
        graph = RenderGraph(MagicMock(), 800, 600)
        first, second = make_pass("world"), make_pass("ui")
        graph.add_pass(first)
        graph.add_pass(second)

        assert graph.passes == [first, second]

    def test_insert_pass_positions_it(self) -> None:
        graph = RenderGraph(MagicMock(), 800, 600)
        graph.add_pass(make_pass("world"))
        early = make_pass("shadow")
        graph.insert_pass(0, early)

        assert graph.passes[0] is early

    def test_the_returned_list_is_a_snapshot(self) -> None:
        """`passes` handed back the live list, so a caller could empty the
        pipeline without releasing a single pass."""
        graph = RenderGraph(MagicMock(), 800, 600)
        graph.add_pass(make_pass("world"))

        graph.passes.clear()

        assert len(graph.passes) == 1

    def test_get_and_remove_by_name(self) -> None:
        graph = RenderGraph(MagicMock(), 800, 600)
        world = make_pass("world")
        graph.add_pass(world)

        assert graph.get_pass("world") is world
        assert graph.remove_pass("world") is world
        assert graph.get_pass("world") is None

    def test_removing_an_unknown_name_returns_none(self) -> None:
        graph = RenderGraph(MagicMock(), 800, 600)

        assert graph.remove_pass("nope") is None

    def test_a_duplicate_pass_name_is_reported(self, caplog) -> None:
        """Both execute -- the list is the source of truth -- but only the
        first is reachable by name, so the ambiguity is said out loud."""
        import logging

        graph = RenderGraph(MagicMock(), 800, 600)
        graph.add_pass(make_pass("world"))

        with caplog.at_level(logging.WARNING):
            graph.add_pass(make_pass("world"))

        assert "second render pass named 'world'" in caplog.text
        assert len(graph.passes) == 2

    def test_a_unique_name_is_not_reported(self, caplog) -> None:
        import logging

        graph = RenderGraph(MagicMock(), 800, 600)
        graph.add_pass(make_pass("world"))

        with caplog.at_level(logging.WARNING):
            graph.add_pass(make_pass("ui"))

        assert caplog.text == ""


class TestRenderGraphExecution:
    def test_only_enabled_passes_execute(self) -> None:
        graph = RenderGraph(MagicMock(), 800, 600)
        on, off = make_pass("on"), make_pass("off")
        off.enabled = False
        graph.add_pass(on)
        graph.add_pass(off)

        graph.execute()

        assert on.execute.called
        assert not off.execute.called

    def test_passes_execute_in_order(self) -> None:
        graph = RenderGraph(MagicMock(), 800, 600)
        order: list[str] = []
        for name in ("first", "second", "third"):
            render_pass = make_pass(name)
            render_pass.execute.side_effect = lambda _ctx, _graph, n=name: order.append(
                n
            )
            graph.add_pass(render_pass)

        graph.execute()

        assert order == ["first", "second", "third"]

    def test_resize_notifies_every_pass(self) -> None:
        graph = RenderGraph(MagicMock(), 800, 600)
        passes = [make_pass(n) for n in ("a", "b")]
        for render_pass in passes:
            graph.add_pass(render_pass)

        graph.resize(1024, 768)

        for render_pass in passes:
            render_pass.on_resize.assert_called_once_with(1024, 768)

    def test_release_drops_and_releases_every_pass(self) -> None:
        graph = RenderGraph(MagicMock(), 800, 600)
        render_pass = make_pass("world")
        graph.add_pass(render_pass)

        graph.release()

        assert render_pass.release.called
        assert graph.passes == []
