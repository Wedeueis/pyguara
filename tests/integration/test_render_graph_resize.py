"""The render graph follows the window, and overlays draw last.

Two engine-level defects behind one symptom: maximising the window left
the editor drawing its panels into a corner of the screen, with the game's
HUD composited on top of them.

Neither was Studio's. `WindowResizeEvent` was dispatched to its
subscribers -- the UI manager -- and the render graph, which is not a
subscriber, never heard: its framebuffers kept the size they were created
at for the life of the process, and every pass's `on_resize` was dead
code. And an overlay registered as an ordinary pass ran mid-chain, so
`UIRenderer.present()` composited the game's UI over it afterwards.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from typing import Any

import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.graphics.pipeline.render_pass import BaseRenderPass


class _RecordingPass(BaseRenderPass):
    """A pass that records when it ran and what size it was told about."""

    def __init__(self, name: str, order: list[str], *, after_ui: bool = False):
        super().__init__(name, after_ui=after_ui)
        self._order = order
        self.sizes: list[tuple[int, int]] = []

    def execute(self, ctx: Any, graph: Any) -> None:
        self._order.append(self.name)

    def on_resize(self, width: int, height: int) -> None:
        self.sizes.append((width, height))


class TestAfterUiPhase:
    """A pass can declare that it draws on top of the game's UI."""

    def test_the_default_is_the_ordinary_chain(self) -> None:
        assert _RecordingPass("plain", []).after_ui is False

    def test_a_pass_can_opt_in(self) -> None:
        assert _RecordingPass("overlay", [], after_ui=True).after_ui is True

    def test_the_flag_is_read_only_from_outside(self) -> None:
        """It describes where the pass belongs, not a per-frame toggle;
        `enabled` is the switch."""
        overlay = _RecordingPass("overlay", [], after_ui=True)
        with pytest.raises(AttributeError):
            overlay.after_ui = False  # type: ignore[misc]


@pytest.mark.integration
class TestResizePropagation:
    """The graph hears about the window."""

    @pytest.fixture
    def app(self):
        import pygame

        application = create_headless_application()
        yield application
        application.shutdown()
        pygame.quit()

    def test_a_headless_app_has_no_graph_and_does_not_mind(self, app) -> None:
        """The headless backend registers none; resizing must be a no-op
        rather than an attribute error."""
        app._resize_render_output(1920, 1080)

    def test_the_renderers_follow_even_with_no_graph(self, app) -> None:
        """A renderer's size is not the graph's business: a backend that
        draws straight to the window has no graph and still has to know
        how big the window is.

        With `keep_aspect` off, because that is the mode in which the
        render size *is* the window size.
        """
        app._config_manager.config.display.keep_aspect = False

        app._resize_render_output(1920, 1080)

        assert app._world_renderer.width == 1920
        assert app._world_renderer.height == 1080

    def test_keeping_the_aspect_renders_at_the_configured_size(self, app) -> None:
        """Not at the window's. A framebuffer grown to match a bigger
        window is not distorted, but it holds more pixels, and a renderer
        working in pixel coordinates fills them with more world -- so the
        shape would be respected and the framing still would not be."""
        display = app._config_manager.config.display
        display.keep_aspect = True

        app._resize_render_output(1990, 820)

        assert app._world_renderer.width == display.screen_width
        assert app._world_renderer.height == display.screen_height

    def test_a_zero_sized_window_is_ignored(self, app) -> None:
        """Minimising reports zero, and resizing a framebuffer to it would
        fail inside the driver."""
        app._resize_render_output(0, 0)
        app._resize_render_output(-1, 100)


@pytest.mark.integration
class TestResizeReachesTheGraph:
    """With a real graph, a resize reaches every framebuffer and pass."""

    @pytest.fixture
    def app(self, isolated_gl_ctx):
        """A headless app with a hand-built graph standing in for the GL one.

        `isolated_gl_ctx`, not a hand-rolled `create_standalone_context()`:
        creating one makes it current and releasing it leaves *no* context
        current, so the session-scoped `gl_ctx` every other GL test shares
        starts failing with `cannot create renderbuffer` from a fixture
        that looks unrelated. Doing it by hand here broke fifteen tests in
        `test_perf_gl.py`, which is exactly what that fixture's docstring
        warns about.
        """
        import pygame

        from pyguara.graphics.pipeline.graph import RenderGraph

        application = create_headless_application()
        graph = RenderGraph(isolated_gl_ctx, 800, 600)
        application._render_graph = graph
        application._container.register_instance(RenderGraph, graph)

        yield application

        graph.release()
        application.shutdown()
        pygame.quit()

    def test_resizing_resizes_the_framebuffers(self, app) -> None:
        """They kept their original size for the life of the process."""
        app._config_manager.config.display.keep_aspect = False
        graph = app._render_graph
        graph.fbo_manager.get_or_create("world")
        assert graph.fbo_manager.width == 800

        app._resize_render_output(1920, 1080)

        assert graph.fbo_manager.width == 1920
        assert graph.fbo_manager.height == 1080

    def test_keeping_the_aspect_letterboxes_instead(self, app) -> None:
        """The framebuffers stay at the configured resolution and the
        image is scaled into the largest rectangle of that shape the
        window holds. The leftover is the bars."""
        display = app._config_manager.config.display
        display.keep_aspect = True
        graph = app._render_graph

        app._resize_render_output(1990, 820)

        assert graph.fbo_manager.width == display.screen_width
        assert graph.fbo_manager.height == display.screen_height
        assert graph.window_size == (1990, 820)
        x, y, width, height = graph.screen_rect
        assert (width, height) != (1990, 820), "nothing was letterboxed"
        assert x > 0 and y == 0, "a wide window gets bars at the sides"
        assert width + 2 * x == pytest.approx(1990, abs=2)
        aspect = display.screen_width / display.screen_height
        assert width / height == pytest.approx(aspect, abs=0.01)

    def test_a_window_of_the_configured_shape_gets_no_bars(self, app) -> None:
        """Doubling a 16:9 window is still 16:9, and a letterbox that
        appeared anyway would be a black frame around nothing."""
        display = app._config_manager.config.display
        display.keep_aspect = True
        width = display.screen_width * 2
        height = display.screen_height * 2

        app._resize_render_output(width, height)

        assert app._render_graph.screen_rect == (0, 0, width, height)

    def test_resizing_tells_every_pass_the_window_size(self, app) -> None:
        """`BaseRenderPass.on_resize` was documented and never called.

        The *window* size, not the render size: a pass that draws straight
        to the screen -- the editor's chrome -- fills the window, and only
        the game is letterboxed inside it.
        """
        recorder = _RecordingPass("recorder", [])
        app._render_graph.add_pass(recorder)

        app._resize_render_output(1990, 820)

        assert recorder.sizes == [(1990, 820)]

    def test_the_renderers_are_resized_too(self, app) -> None:
        """The other half of the symptom. The graph's framebuffers grew
        and the renderers did not, so the world kept being drawn at the
        old size and stretched across the new one."""
        app._config_manager.config.display.keep_aspect = False

        app._resize_render_output(1990, 820)

        assert app._world_renderer.width == 1990
        assert app._world_renderer.height == 820

    def test_an_unchanged_size_does_no_work(self, app) -> None:
        """A window event fires for a move as well as a resize, and
        reallocating every framebuffer for one would be a visible stall."""
        app._config_manager.config.display.keep_aspect = False
        recorder = _RecordingPass("recorder", [])
        app._render_graph.add_pass(recorder)

        app._resize_render_output(800, 600)

        assert recorder.sizes == []


@pytest.mark.integration
class TestDrawOrder:
    """An `after_ui` pass runs after the game's UI is composited."""

    @pytest.fixture
    def app(self, isolated_gl_ctx):
        """A headless app with a graph, on a context of this test's own."""
        import pygame

        from pyguara.graphics.pipeline.graph import RenderGraph

        application = create_headless_application()
        graph = RenderGraph(isolated_gl_ctx, 320, 240)
        application._render_graph = graph

        yield application

        graph.release()
        application.shutdown()
        pygame.quit()

    def _record(self, app) -> list[str]:
        """Instrument the frame so every stage appends its name."""
        order: list[str] = []

        app._render_graph.add_pass(_RecordingPass("chain", order))
        app._render_graph.add_pass(_RecordingPass("overlay", order, after_ui=True))

        app._scene_manager.render = lambda *a, **k: None  # type: ignore[method-assign]
        app._ui_manager.render = lambda *a, **k: order.append("ui_draw")  # type: ignore[method-assign]
        app._ui_renderer.present = lambda: order.append("ui_present")  # type: ignore[method-assign]
        app._window.present = lambda: None  # type: ignore[method-assign]
        return order

    def test_the_overlay_runs_after_the_ui_is_composited(self, app) -> None:
        """Mid-chain, the game's HUD composites over the editor -- which
        reads as the editor being behind the game."""
        order = self._record(app)

        app._render_with_graph(1.0)

        assert order.index("chain") < order.index("ui_present")
        assert order.index("ui_present") < order.index("overlay")

    def test_an_ordinary_pass_still_runs_before_the_ui(self, app) -> None:
        order = self._record(app)

        app._render_with_graph(1.0)

        assert order.index("chain") < order.index("ui_draw")

    def test_a_disabled_overlay_does_not_run(self, app) -> None:
        order = self._record(app)
        overlay = app._render_graph.get_pass("overlay")
        assert overlay is not None
        overlay.enabled = False

        app._render_with_graph(1.0)

        assert "overlay" not in order
