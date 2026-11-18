"""A letterboxed game letterboxes its UI and its mouse too.

With `display.keep_aspect` (the default) the world renders at the
configured size and is scaled into the window. The game's UI was drawn
straight to the window in window pixels, so resizing left the menu at its
old pixel size and position over a scaled background, and a click was
tested against window pixels the UI never used.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from typing import Any

import numpy as np
import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.common.types import Color, Rect
from pyguara.events.input import MouseButtonEvent, MouseMotionEvent

_DESIGN = (64, 48)
_RED = Color(255, 0, 0, 255)


def _headless(design: tuple[int, int] = _DESIGN) -> Any:
    application = create_headless_application()
    display = application._config_manager.config.display
    display.screen_width, display.screen_height = design
    display.keep_aspect = True
    return application


@pytest.mark.integration
class TestTheUiIsLetterboxed:
    """The UI lands where the world does, at the world's scale."""

    @pytest.fixture
    def app(self, wgpu_frame):
        import pygame

        from pyguara.graphics.backends.wgpu.ui_renderer import WgpuUIRenderer
        from pyguara.graphics.pipeline.device import WgpuDevice
        from pyguara.graphics.pipeline.graph import RenderGraph
        from pyguara.graphics.pipeline.passes.final_pass import FinalPass

        application = _headless()
        frame = wgpu_frame(*_DESIGN)
        graph = RenderGraph(WgpuDevice(frame), *_DESIGN)
        graph.add_pass(FinalPass(input_fbo_name="world"))
        application._render_graph = graph
        application._ui_renderer = WgpuUIRenderer(frame)
        application._scene_manager.render = lambda *a, **k: None  # type: ignore[method-assign]
        # The whole design area, in red, through the UI.
        application._ui_manager.render = lambda ui: ui.draw_rect(  # type: ignore[method-assign]
            Rect(0, 0, *_DESIGN), _RED
        )
        yield application, frame

        graph.release()
        application.shutdown()
        pygame.quit()

    def _red_rows_and_columns(self, frame: Any, window: tuple[int, int]) -> Any:
        frame.gpu.end_frame()
        pixels = np.frombuffer(frame.gpu.read_pixels(), dtype=np.uint8)
        image = pixels.reshape(window[1], window[0], 4)[..., :3].astype(int)
        red = (image[..., 0] > 200) & (image[..., 1] < 60) & (image[..., 2] < 60)
        rows = np.flatnonzero(red.any(axis=1))
        columns = np.flatnonzero(red.any(axis=0))
        return rows, columns

    def test_a_tall_window_puts_the_ui_between_the_bars(self, app) -> None:
        """Reported as menu buttons drawn over the title after the window
        was made taller: the background moved down and scaled, the UI did
        not."""
        application, frame = app
        window = (64, 96)
        application._resize_render_output(*window)
        x, y, width, height = application._render_graph.screen_rect
        assert (x, y, width, height) == (0, 24, 64, 48)

        application._render_with_graph(1.0)
        rows, columns = self._red_rows_and_columns(frame, window)

        assert rows.size, "the UI drew nothing"
        assert (rows[0], rows[-1]) == (y, y + height - 1)
        assert (columns[0], columns[-1]) == (x, x + width - 1)

    def test_a_bigger_window_scales_the_ui_with_the_world(self, app) -> None:
        """Doubled, the design area fills the doubled window -- the UI
        did not grow, and kept to the top-left quarter."""
        application, frame = app
        window = (128, 96)
        application._resize_render_output(*window)

        application._render_with_graph(1.0)
        rows, columns = self._red_rows_and_columns(frame, window)

        assert (rows[0], rows[-1]) == (0, 95)
        assert (columns[0], columns[-1]) == (0, 127)


@pytest.mark.integration
class TestTheMouseIsLetterboxed:
    """The game reads the cursor in the pixels its UI is laid out in."""

    @pytest.fixture
    def app(self):
        """A graph on a recording device: the letterbox is the graph's."""
        import pygame

        from pyguara.graphics.pipeline.graph import RenderGraph
        from tests.recording_device import RecordingDevice

        application = _headless()
        application._render_graph = RenderGraph(RecordingDevice(), *_DESIGN)
        seen: list[Any] = []
        application._input_manager.process_event = seen.append  # type: ignore[method-assign]
        yield application, seen
        application.shutdown()
        pygame.quit()

    def _deliver(self, application: Any, event: Any) -> None:
        application._window.poll_events = lambda: [event]  # type: ignore[method-assign]
        application._process_input(0.0)

    def test_a_click_is_mapped_into_the_game(self, app) -> None:
        """Window (64, 96) letterboxes the 64x48 game at y 24; the centre
        of the window is the centre of the game."""
        application, seen = app
        application._resize_render_output(64, 96)

        self._deliver(application, MouseButtonEvent(button=1, x=32, y=48, is_down=True))

        assert seen[-1].pos == (32, 24)
        assert seen[-1].button == 1 and seen[-1].is_down

    def test_a_scaled_window_scales_the_motion(self, app) -> None:
        application, seen = app
        application._resize_render_output(128, 96)

        self._deliver(application, MouseMotionEvent(x=127, y=95, rel_x=10, rel_y=-4))

        assert seen[-1].pos == (63, 47)
        assert (seen[-1].rel_x, seen[-1].rel_y) == (5, -2)

    def test_a_cursor_on_a_bar_is_outside_the_game(self, app) -> None:
        """Not clamped onto its edge, where it would hover the widget
        nearest the bar."""
        application, seen = app
        application._resize_render_output(64, 96)

        self._deliver(application, MouseMotionEvent(x=10, y=5, rel_x=0, rel_y=0))

        assert seen[-1].y < 0

    def test_without_a_letterbox_the_cursor_is_untouched(self, app) -> None:
        application, seen = app
        application._config_manager.config.display.keep_aspect = False
        application._resize_render_output(200, 100)

        event = MouseButtonEvent(button=1, x=150, y=70, is_down=False)
        self._deliver(application, event)

        assert seen[-1] is event

    def test_with_no_graph_the_cursor_is_untouched(self, app) -> None:
        """The pygame backend draws at the render size from the window's
        corner without scaling, so its cursor is already in game pixels."""
        application, seen = app
        application._resize_render_output(64, 96)
        application._render_graph = None

        event = MouseButtonEvent(button=1, x=32, y=48, is_down=True)
        self._deliver(application, event)

        assert seen[-1] is event
