"""What one `GLUIRenderer` frame costs, and which part of it costs that.

The ModernGL UI renderer is a *hybrid*: every widget is rasterised by
pygame onto an offscreen surface, and `present()` uploads that whole
surface as a texture and composites it as a fullscreen quad. So the cost
of a UI frame is set by the **window area**, not by what the UI drew --
one HUD label and a forty-nine-primitive HUD pay the same, which is the
claim these benchmarks exist to put a number on.

The split matters more than the total, because the two halves move
differently:

- `pygame.transform.flip` and `pygame.image.tobytes` are **CPU** copies of
  the whole surface. They are the same cost on every machine with the same
  pixel count, and they exist only because the pixels were produced on the
  CPU in the first place.
- `Texture.write` is the upload, and it is a driver number. It will differ
  by an order of magnitude between a discrete GPU, an integrated one, and
  llvmpipe on a CI runner.

Like the rest of `test_perf_gl.py`, these describe a machine as much as
the engine. The portable half is the CPU half.
"""

from __future__ import annotations

import pygame
import pytest

from pyguara.common.types import Color, Rect, Vector2

pytestmark = [pytest.mark.performance, pytest.mark.slow]

WHITE = Color(255, 255, 255, 255)
PANEL = Color(20, 22, 28, 200)

SIZES = [(1280, 720), (1920, 1080)]
"""The default window size, and the other one people actually ship."""


def draw_one_label(renderer) -> None:
    """The pathological case: the smallest UI a game can have.

    `Application` calls `present()` every frame and every primitive sets
    `_dirty`, so a single FPS counter in the corner buys the whole
    fullscreen upload.
    """
    renderer.draw_text("99", Vector2(20, 20), WHITE, 16)


def draw_hud(renderer) -> None:
    """A realistic HUD: panels, bars, an item belt, a minimap, a stat block."""
    renderer.draw_rect(Rect(10, 10, 260, 90), PANEL, 0, 6)
    renderer.draw_rect(Rect(18, 42, 200, 14), Color(40, 40, 46, 255))
    renderer.draw_rect(Rect(18, 42, 150, 14), Color(200, 60, 40, 255))
    renderer.draw_rect(Rect(18, 62, 200, 10), Color(40, 40, 46, 255))
    renderer.draw_rect(Rect(18, 62, 90, 10), Color(60, 140, 220, 255))
    for i in range(8):
        renderer.draw_rect(Rect(300 + i * 44, 640, 40, 40), PANEL, 0, 4)
        renderer.draw_circle(Vector2(320 + i * 44, 660), 12, Color(180, 160, 90, 255))
        renderer.draw_text(str(i + 1), Vector2(302 + i * 44, 642), WHITE, 12)
    renderer.draw_rect(Rect(1010, 10, 260, 200), PANEL, 2, 4)
    for i in range(12):
        renderer.draw_circle(
            Vector2(1040 + i * 18, 60 + (i % 5) * 30), 3, Color(90, 200, 90, 255)
        )
    for i, line in enumerate(
        ["HP 150/200", "MANA 90/120", "Lv 7", "XP 3400", "Gold 1,284", "Floor 3"]
    ):
        renderer.draw_text(line, Vector2(20, 120 + i * 20), WHITE, 14)
    renderer.draw_line(Vector2(10, 110), Vector2(270, 110), Color(70, 70, 80, 255), 1)


SCENES = {"one_label": draw_one_label, "full_hud": draw_hud}


@pytest.fixture
def ui_renderer(gl_ctx, request):
    """A `GLUIRenderer` over a framebuffer of the requested size."""
    from pyguara.graphics.backends.moderngl.ui_renderer import GLUIRenderer

    if not pygame.get_init():
        pygame.init()
    width, height = request.param
    gl_ctx.simple_framebuffer((width, height)).use()
    renderer = GLUIRenderer(gl_ctx, width, height)
    yield renderer
    renderer.release()


@pytest.mark.parametrize("ui_renderer", SIZES, ids=str, indirect=True)
@pytest.mark.parametrize("scene", list(SCENES), ids=str)
def test_sweep_ui_frame_end_to_end(benchmark, gl_ctx, ui_renderer, scene) -> None:
    """A whole UI frame: draw the widgets, then present.

    The two scenes land within noise of each other, and that is the
    finding -- 49 primitives cost what 1 does.
    """
    draw = SCENES[scene]

    def one_frame() -> None:
        draw(ui_renderer)
        ui_renderer.present()
        gl_ctx.finish()

    benchmark(one_frame)


@pytest.mark.parametrize("ui_renderer", SIZES, ids=str, indirect=True)
@pytest.mark.parametrize("scene", list(SCENES), ids=str)
def test_sweep_ui_rasterise_only(benchmark, ui_renderer, scene) -> None:
    """Just the widgets, onto the surface -- no present.

    This is the only part of the frame that depends on what the UI
    contains, and it is the part that is already cheap.
    """
    draw = SCENES[scene]
    benchmark(lambda: draw(ui_renderer))


@pytest.mark.parametrize("ui_renderer", SIZES, ids=str, indirect=True)
def test_sweep_ui_present_only(benchmark, gl_ctx, ui_renderer) -> None:
    """Just `present()`, over a surface with one label already on it."""
    draw_one_label(ui_renderer)

    def present() -> None:
        ui_renderer._dirty = True
        ui_renderer.present()
        gl_ctx.finish()

    benchmark(present)


@pytest.mark.parametrize("ui_renderer", SIZES, ids=str, indirect=True)
def test_sweep_ui_upload_path(benchmark, gl_ctx, ui_renderer) -> None:
    """The upload alone: hand the surface's own memory to GL.

    What `present()` costs once the two CPU copies are gone, which is the
    floor for any version of this renderer that still produces its pixels
    on the CPU. Only instancing goes below it.
    """
    surface = ui_renderer._surface
    texture = ui_renderer._texture

    def upload() -> None:
        texture.write(surface.get_buffer())
        gl_ctx.finish()

    benchmark(upload)


@pytest.mark.parametrize("ui_renderer", SIZES, ids=str, indirect=True)
def test_sweep_ui_cpu_copies(benchmark, ui_renderer) -> None:
    """The two CPU copies on their own, with no GL in the measurement.

    The portable number: a flip of the whole surface plus a conversion of
    the whole surface to an RGBA bytes object, both proportional to the
    window area and neither dependent on a driver.
    """
    surface = ui_renderer._surface

    def copies() -> None:
        flipped = pygame.transform.flip(surface, False, True)
        pygame.image.tobytes(flipped, "RGBA", False)

    benchmark(copies)
