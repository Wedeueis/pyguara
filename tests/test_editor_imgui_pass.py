"""The editor owns the whole window, not the game's frame inside it.

`ctx.screen.viewport` means *where the game's frame goes*: with
`display.keep_aspect` the render graph narrows it to the letterbox, so the
game and its HUD land inside their own frame whatever shape the window is
dragged to. The editor is not the game. It inherited that viewport, and
every panel was squeezed into the letterbox along with it.

Measured on the report this exists for: a 2000x876 window gives a 16:9
letterbox 1557px wide, so the editor was drawn at a horizontal scale of
0.73 -- compressed text, and the round sun in the Viewport panel drawn as
an ellipse taller than wide. An ultrawide display makes it worse: at 21:9
more than a quarter of the window is bars.

The viewport is put back afterwards, because the game's own UI composites
after the graph runs and belongs inside the letterbox rather than spilling
onto the bars.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from typing import Any

import pytest

pytest.importorskip("imgui_bundle")

from pyguara.editor.imgui_pass import ImGuiPass  # noqa: E402

WINDOW = (1990, 820)
"""A window whose shape is not the configured one, so there are bars."""

LETTERBOX = (266, 0, 1457, 820)
"""Where a 16:9 game lands inside it."""


class FakeScreen:
    """A default framebuffer that records what was asked of it."""

    def __init__(self, viewport: tuple[int, int, int, int]) -> None:
        self.viewport = viewport
        self.viewports: list[tuple[int, int, int, int]] = []
        self.cleared: list[tuple[int, int, int, int]] = []

    def use(self) -> None:
        self.viewports.append(self.viewport)

    def clear(self, *colour: float) -> None:
        self.cleared.append(self.viewport)


class FakeContext:
    """Just the one attribute the pass reaches for."""

    def __init__(self, screen: Any) -> None:
        self.screen = screen


class RecordingLayer:
    """An editor layer that records the size it was asked to draw at."""

    def __init__(self) -> None:
        self.rendered: list[tuple[int, int]] = []
        self.viewport_while_drawing: tuple[int, int, int, int] | None = None
        self.screen: Any = None

    def render(self, width: int, height: int, dt: float | None = None) -> None:
        self.rendered.append((width, height))
        if self.screen is not None:
            self.viewport_while_drawing = self.screen.viewport

    def release(self) -> None: ...


def _pass(clear: tuple[float, float, float] | None = None) -> tuple[Any, Any, Any]:
    """Build a pass over a fake context sitting at the letterbox."""
    layer = RecordingLayer()
    screen = FakeScreen(LETTERBOX)
    layer.screen = screen
    render_pass = ImGuiPass(layer, *WINDOW, clear_colour=clear)  # type: ignore[arg-type]
    return render_pass, FakeContext(screen), screen


@pytest.mark.unit
class TestTheEditorGetsTheWholeWindow:
    def test_it_draws_under_the_window_viewport(self) -> None:
        render_pass, ctx, screen = _pass()

        render_pass.execute(ctx, None)  # type: ignore[arg-type]

        assert screen.viewports == [(0, 0, *WINDOW)], (
            "the editor drew under the game's letterbox, which squeezes "
            "every panel by the ratio between the two"
        )

    def test_the_layer_is_laid_out_for_the_window(self) -> None:
        render_pass, ctx, _ = _pass()

        render_pass.execute(ctx, None)  # type: ignore[arg-type]

        assert render_pass.layer.rendered == [WINDOW]

    def test_the_viewport_matches_the_layout_while_drawing(self) -> None:
        """The two have to agree, or ImGui's coordinates are scaled by the
        difference -- which is the whole defect."""
        render_pass, ctx, _ = _pass()

        render_pass.execute(ctx, None)  # type: ignore[arg-type]

        assert render_pass.layer.viewport_while_drawing == (0, 0, *WINDOW)

    def test_the_clear_covers_the_window_not_the_frame(self) -> None:
        """Clearing under the letterbox would leave the bars holding last
        frame's pixels."""
        render_pass, ctx, screen = _pass(clear=(0.1, 0.1, 0.12))

        render_pass.execute(ctx, None)  # type: ignore[arg-type]

        assert screen.cleared == [(0, 0, *WINDOW)]


@pytest.mark.unit
class TestItPutsTheViewportBack:
    def test_the_game_frame_is_restored(self) -> None:
        """The game's UI composites after the graph runs, as a fullscreen
        quad; left on the window viewport it would spill onto the bars."""
        render_pass, ctx, screen = _pass()

        render_pass.execute(ctx, None)  # type: ignore[arg-type]

        assert screen.viewport == LETTERBOX

    def test_it_is_restored_even_when_drawing_raises(self) -> None:
        render_pass, ctx, screen = _pass()

        def explode(width: int, height: int, dt: float | None = None) -> None:
            raise RuntimeError("the panel exploded")

        render_pass.layer.render = explode  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            render_pass.execute(ctx, None)  # type: ignore[arg-type]

        assert screen.viewport == LETTERBOX

    def test_a_window_with_no_bars_is_unchanged(self) -> None:
        """Nothing to restore and nothing to narrow: the common case must
        not depend on the letterbox existing."""
        layer = RecordingLayer()
        screen = FakeScreen((0, 0, *WINDOW))
        layer.screen = screen
        render_pass = ImGuiPass(layer, *WINDOW)  # type: ignore[arg-type]

        render_pass.execute(FakeContext(screen), None)  # type: ignore[arg-type]

        assert screen.viewport == (0, 0, *WINDOW)
        assert layer.rendered == [WINDOW]


@pytest.mark.unit
class TestOffscreen:
    def test_no_default_framebuffer_still_draws(self) -> None:
        """A standalone context has no `ctx.screen`; the editor then draws
        into whatever the caller bound, which is what a capture wants."""
        layer = RecordingLayer()
        render_pass = ImGuiPass(layer, *WINDOW)  # type: ignore[arg-type]

        render_pass.execute(FakeContext(None), None)  # type: ignore[arg-type]

        assert layer.rendered == [WINDOW]

    def test_a_disabled_pass_draws_nothing(self) -> None:
        render_pass, ctx, screen = _pass()
        render_pass.enabled = False

        render_pass.execute(ctx, None)  # type: ignore[arg-type]

        assert render_pass.layer.rendered == []
        assert screen.viewports == []


@pytest.mark.unit
class TestResize:
    def test_the_window_size_is_what_follows(self) -> None:
        """`on_resize` is fed the window size, not the render size: only
        the game is letterboxed inside it."""
        render_pass, ctx, screen = _pass()

        render_pass.on_resize(3440, 1440)
        render_pass.execute(ctx, None)  # type: ignore[arg-type]

        assert screen.viewports == [(0, 0, 3440, 1440)]
        assert render_pass.layer.rendered == [(3440, 1440)]
