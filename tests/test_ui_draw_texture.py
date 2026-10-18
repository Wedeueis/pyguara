"""`UIRenderer.draw_texture` can name a region of its texture.

Until it could, the UI half of the engine was the only one that could
not address an atlas: `RenderCommand.source_rect` has always reached the
world renderers, and the pygame backend blits regions straight out of a
sheet on its fast path -- but a HUD icon or a nine-patch slice had to be
handed a surface somebody had already cut. The nine-patch renderer, which
needs nine differently-stretched regions of one texture, is why it was
worth closing.

The two real UI renderers share one `blit_texture`, so both are run
through the same cases: their `draw_texture` bodies were byte-identical
before, by coincidence rather than by construction, and a region that
worked on pygame and not on ModernGL would be worse than no region at
all. The ModernGL one is driven through its offscreen surface directly,
which is where it composes every pixel; no GL context is needed for that
and none is created here.
"""

from __future__ import annotations

from typing import Any

import pygame
import pytest

from pyguara.common.types import Color, Rect
from pyguara.graphics.backends import surface_texture

RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
STRIPES = (RED, GREEN, BLUE)


@pytest.fixture(autouse=True)
def _pygame() -> Any:
    pygame.init()
    surface_texture._warned_out_of_bounds = False
    yield
    pygame.quit()


@pytest.fixture
def target() -> pygame.Surface:
    return pygame.Surface((9, 9), pygame.SRCALPHA)


def _striped(height: int = 3, width: int = 3) -> pygame.Surface:
    """A texture whose rows are red, green then blue, top-down."""
    texture = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(height):
        for x in range(width):
            texture.set_at((x, y), STRIPES[y % len(STRIPES)])
    return texture


def _colours(surface: pygame.Surface) -> set[tuple[int, int, int, int]]:
    return {
        tuple(surface.get_at((x, y)))  # type: ignore[misc]
        for x in range(surface.get_width())
        for y in range(surface.get_height())
    }


def _ui_renderers(target: pygame.Surface) -> list[tuple[str, Any]]:
    """Both renderers that actually put pixels somewhere, over one surface."""
    from pyguara.graphics.backends.moderngl.ui_renderer import GLUIRenderer
    from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer

    gl = GLUIRenderer.__new__(GLUIRenderer)
    gl._surface = target  # type: ignore[attr-defined]
    gl._dirty = False  # type: ignore[attr-defined]
    return [("pygame", PygameUIRenderer(target)), ("moderngl", gl)]


@pytest.fixture(params=["pygame", "moderngl"])
def renderer(request: Any, target: pygame.Surface) -> Any:
    by_name = dict(_ui_renderers(target))
    return by_name[request.param]


class TestARegionOfTheTextureIsDrawable:
    def test_the_whole_texture_is_still_the_default(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        """No `source_rect` means what it always meant: all of it."""
        renderer.draw_texture(_striped(), Rect(0, 0, 9, 9))

        assert _colours(target) == {RED, GREEN, BLUE}

    def test_one_row_fills_the_destination(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        """The probe this came from: asking for the green row used to get
        all three rows scaled up, because there was nowhere to say which
        row was wanted."""
        renderer.draw_texture(_striped(), Rect(0, 0, 9, 9), None, Rect(0, 1, 3, 1))

        assert _colours(target) == {GREEN}

    def test_the_region_is_cut_before_the_scale(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        """A 1x1 region scaled 9x covers the destination in one colour. The
        other order -- scale the sheet, then cut -- would land a ninth of
        it, and is what a naive implementation does."""
        renderer.draw_texture(_striped(), Rect(0, 0, 9, 9), None, Rect(1, 2, 1, 1))

        assert _colours(target) == {BLUE}

    def test_a_region_lands_at_the_destination_not_at_its_own_offset(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        """Source coordinates and destination coordinates are separate
        spaces; a region at y=2 draws wherever the rect says."""
        renderer.draw_texture(_striped(), Rect(3, 0, 3, 3), None, Rect(0, 2, 3, 1))

        assert _colours(target.subsurface(pygame.Rect(3, 0, 3, 3))) == {BLUE}
        assert _colours(target.subsurface(pygame.Rect(0, 0, 3, 9))) == {(0, 0, 0, 0)}

    def test_an_unscaled_region_is_copied_pixel_for_pixel(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        """A region the same size as its destination must not be run
        through `transform.scale` -- same size in, same pixels out."""
        renderer.draw_texture(_striped(), Rect(0, 0, 3, 2), None, Rect(0, 0, 3, 2))

        assert tuple(target.get_at((1, 0))) == RED
        assert tuple(target.get_at((1, 1))) == GREEN


class TestTheTintStillApplies:
    def test_a_tint_multiplies_a_region(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        """Tint and region compose: the tint runs on the cut region, not on
        the whole sheet. A white source times a red tint is red, so the
        tint is visible in the result rather than merely harmless."""
        white = pygame.Surface((3, 3), pygame.SRCALPHA)
        white.fill((255, 255, 255, 255))

        renderer.draw_texture(
            white, Rect(0, 0, 9, 9), Color(255, 0, 0, 255), Rect(0, 1, 3, 1)
        )

        assert _colours(target) == {RED}

    def test_a_tint_does_not_discolour_the_texture_itself(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        """`fill` mutates in place, and with no scale to copy through, the
        surface reaching it is the caller's own texture -- so a tinted draw
        would permanently recolour every later draw of that texture."""
        texture = _striped()
        renderer.draw_texture(
            texture, Rect(0, 0, 3, 3), Color(255, 0, 0, 255), Rect(0, 0, 3, 3)
        )

        assert tuple(texture.get_at((0, 1))) == GREEN


class TestARegionTheTextureDoesNotContain:
    def test_a_partly_outside_region_draws_the_overlap(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        """Clipped, not refused: one wrong atlas entry shows one wrong
        sprite rather than blanking the surface around it."""
        renderer.draw_texture(_striped(), Rect(0, 0, 9, 9), None, Rect(0, 2, 3, 99))

        assert _colours(target) == {BLUE}

    def test_a_fully_outside_region_draws_nothing(
        self, renderer: Any, target: pygame.Surface
    ) -> None:
        renderer.draw_texture(_striped(), Rect(0, 0, 9, 9), None, Rect(50, 50, 3, 3))

        assert _colours(target) == {(0, 0, 0, 0)}

    def test_the_clip_is_logged(
        self, renderer: Any, target: pygame.Surface, caplog: Any
    ) -> None:
        """The caller's atlas metadata disagrees with its atlas, which is
        always a bug; drawing the overlap has to leave a trail or the bug
        is only findable by looking at the frame."""
        with caplog.at_level("WARNING"):
            renderer.draw_texture(_striped(), Rect(0, 0, 9, 9), None, Rect(0, 2, 3, 99))

        assert "does not contain it" in caplog.text

    def test_a_region_inside_the_texture_is_not_logged(
        self, renderer: Any, target: pygame.Surface, caplog: Any
    ) -> None:
        with caplog.at_level("WARNING"):
            renderer.draw_texture(_striped(), Rect(0, 0, 9, 9), None, Rect(0, 1, 3, 1))

        assert caplog.text == ""


class TestADegenerateDestination:
    @pytest.mark.parametrize("rect", [Rect(0, 0, 0, 5), Rect(0, 0, 5, 0)])
    def test_a_zero_extent_destination_draws_nothing(
        self, renderer: Any, target: pygame.Surface, rect: Rect
    ) -> None:
        """A nine-patch with a zero-width edge produces three of these per
        frame, so they have to be free rather than an error."""
        renderer.draw_texture(_striped(), rect)

        assert _colours(target) == {(0, 0, 0, 0)}


class TestTheModernGLBackendOnlyReuploadsWhenSomethingLanded:
    """Its `present()` uploads the whole overlay when `_dirty` is set --
    3.69 MB at the default window size. A draw that produced no pixels
    must not buy that."""

    def test_a_drawn_region_dirties_the_surface(self, target: pygame.Surface) -> None:
        gl = dict(_ui_renderers(target))["moderngl"]

        gl.draw_texture(_striped(), Rect(0, 0, 9, 9), None, Rect(0, 1, 3, 1))

        assert gl._dirty is True

    def test_a_fully_outside_region_does_not(self, target: pygame.Surface) -> None:
        gl = dict(_ui_renderers(target))["moderngl"]

        gl.draw_texture(_striped(), Rect(0, 0, 9, 9), None, Rect(50, 50, 3, 3))

        assert gl._dirty is False
