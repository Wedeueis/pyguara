"""The editor owns the whole window, not the game's frame inside it.

With `display.keep_aspect` the game renders at its configured size and the
render graph letterboxes it into the window, whatever shape the window is
dragged to. The editor is not the game. Under ModernGL it inherited the
letterbox's viewport and every panel was squeezed into it -- on a 2000x876
window, a horizontal scale of 0.73: compressed text, and the round sun in
the Viewport panel drawn as an ellipse taller than wide.

On wgpu there is no viewport to inherit -- each ImGui command clips itself
-- but the same three things decide it: the editor draws to the window's
own target, laid out for the window's size, and clears the window rather
than the frame. `test_attach.py`'s whole-window scenario checks the pixels.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("imgui_bundle")

from pyguara.studio.imgui_pass import ImGuiPass  # noqa: E402

WINDOW = (1990, 820)
"""A window whose shape is not the configured one, so there are bars."""

GAME_FRAME = 4
"""Some offscreen target the graph left current: where the game was drawn."""


class FakeGpu:
    """The native frame's calls the pass makes, recorded in order."""

    def __init__(self) -> None:
        self.current = GAME_FRAME
        self.calls: list[tuple[Any, ...]] = []

    def set_target(self, target: int) -> None:
        self.current = target
        self.calls.append(("set_target", target))

    def clear_target(self, *rgba: float) -> None:
        self.calls.append(("clear", self.current, rgba))


class RecordingLayer:
    """An editor layer that records the size it was asked to draw at."""

    def __init__(self, gpu: FakeGpu) -> None:
        self.gpu = gpu
        self.rendered: list[tuple[int, int]] = []
        self.target_while_drawing: list[int] = []

    def render(self, width: int, height: int, dt: float | None = None) -> None:
        self.rendered.append((width, height))
        self.target_while_drawing.append(self.gpu.current)

    def release(self) -> None: ...


def _pass(
    clear: tuple[float, float, float] | None = None,
) -> tuple[Any, Any, FakeGpu]:
    """Build a pass over a fake graph whose frame has the game's target current."""
    gpu = FakeGpu()
    layer = RecordingLayer(gpu)
    render_pass = ImGuiPass(layer, *WINDOW, clear_colour=clear)  # type: ignore[arg-type]
    graph = SimpleNamespace(device=SimpleNamespace(frame=SimpleNamespace(gpu=gpu)))
    return render_pass, graph, gpu


@pytest.mark.unit
class TestTheEditorGetsTheWholeWindow:
    def test_it_draws_to_the_window(self) -> None:
        """Target 0 is the window; the graph may have left another current."""
        render_pass, graph, _ = _pass()

        render_pass.execute(graph)

        assert render_pass.layer.target_while_drawing == [0]

    def test_the_layer_is_laid_out_for_the_window(self) -> None:
        render_pass, graph, _ = _pass()

        render_pass.execute(graph)

        assert render_pass.layer.rendered == [WINDOW]

    def test_the_clear_covers_the_window_not_the_frame(self) -> None:
        """Studio disables the final blit, so nothing else writes the
        window: without the clear it would hold last frame's contents."""
        render_pass, graph, gpu = _pass(clear=(0.1, 0.1, 0.12))

        render_pass.execute(graph)

        assert ("clear", 0, (0.1, 0.1, 0.12, 1.0)) in gpu.calls

    def test_no_clear_colour_clears_nothing(self) -> None:
        render_pass, graph, gpu = _pass()

        render_pass.execute(graph)

        assert not [call for call in gpu.calls if call[0] == "clear"]


@pytest.mark.unit
class TestDisabled:
    def test_a_disabled_pass_draws_nothing(self) -> None:
        render_pass, graph, gpu = _pass()
        render_pass.enabled = False

        render_pass.execute(graph)

        assert render_pass.layer.rendered == []
        assert gpu.calls == []


@pytest.mark.unit
class TestResize:
    def test_the_window_size_is_what_follows(self) -> None:
        """`on_resize` is fed the window size, not the render size: only
        the game is letterboxed inside it."""
        render_pass, graph, _ = _pass()

        render_pass.on_resize(3440, 1440)
        render_pass.execute(graph)

        assert render_pass.layer.rendered == [(3440, 1440)]
