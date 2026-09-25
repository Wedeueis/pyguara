"""`PygameBackend.draw_texture` honours the transforms it is given.

It used to ignore `rotation` and `scale` outright and blit top-left,
while the ModernGL backend honoured both and centred -- so one
`draw_texture` call put a sprite somewhere else, at another size,
depending on which backend was running. These pin the contract in
`IRenderer.draw_texture`: centred, rotated, scaled, and mirrored by a
negative scale.
"""

from __future__ import annotations

import pygame
import pytest

from pyguara.common.types import Vector2
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend

SIZE = (200, 200)
MARK = (255, 0, 0, 255)
"""The one opaque pixel every test looks for."""


@pytest.fixture(autouse=True)
def _pygame() -> None:
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def screen() -> pygame.Surface:
    return pygame.Surface(SIZE, pygame.SRCALPHA)


@pytest.fixture
def renderer(screen: pygame.Surface) -> PygameBackend:
    return PygameBackend(screen)


class _Texture:
    """The smallest thing the renderer will accept: a wrapped surface."""

    def __init__(self, surface: pygame.Surface) -> None:
        self.native_handle = surface
        self.path = "<test>"
        self.width = surface.get_width()
        self.height = surface.get_height()


def _swatch(width: int, height: int, mark: tuple[int, int, int] | None = None):
    """A green rectangle, optionally with one red pixel top-left."""
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    surface.fill((0, 200, 0, 255))
    if mark is not None:
        surface.set_at((0, 0), mark)
    return _Texture(surface)


def _opaque_box(screen: pygame.Surface) -> tuple[int, int, int, int]:
    """The bounding box of everything drawn, as `(left, top, right, bottom)`."""
    xs, ys = [], []
    for y in range(screen.get_height()):
        for x in range(screen.get_width()):
            if screen.get_at((x, y)).a > 0:
                xs.append(x)
                ys.append(y)
    assert xs, "nothing was drawn"
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


class TestItCentresOnThePosition:
    """Centred, not top-left -- `IRenderer.draw_texture`'s contract."""

    def test_an_untransformed_texture_is_centred(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(_swatch(20, 10), Vector2(100, 100))

        assert _opaque_box(screen) == (90, 95, 110, 105)

    def test_it_is_the_same_centre_at_any_scale(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(_swatch(20, 10), Vector2(100, 100), scale=Vector2(2, 2))

        left, top, right, bottom = _opaque_box(screen)
        assert (left + right) // 2 == pytest.approx(100, abs=1)
        assert (top + bottom) // 2 == pytest.approx(100, abs=1)


class TestItScales:
    """It used to drop `scale` on the floor."""

    def test_a_scale_of_two_doubles_the_box(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(_swatch(20, 10), Vector2(100, 100), scale=Vector2(2, 2))

        left, top, right, bottom = _opaque_box(screen)
        assert (right - left, bottom - top) == (40, 20)

    def test_a_non_uniform_scale_stretches_one_axis(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(_swatch(20, 10), Vector2(100, 100), scale=Vector2(3, 1))

        left, top, right, bottom = _opaque_box(screen)
        assert (right - left, bottom - top) == (60, 10)

    def test_a_scale_of_one_is_left_alone(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        """The plain-blit path: every `draw_text` in the game takes it."""
        renderer.draw_texture(_swatch(20, 10), Vector2(100, 100), scale=Vector2(1, 1))

        left, top, right, bottom = _opaque_box(screen)
        assert (right - left, bottom - top) == (20, 10)


class TestItMirrors:
    """A negative scale is a flip -- how a sprite faces the other way."""

    def _mark_side(self, screen: pygame.Surface, box) -> str:
        """Which half of the drawn box the red marker landed in."""
        left, top, right, _ = box
        for x in range(left, right):
            if screen.get_at((x, top)) == MARK:
                return "left" if x < (left + right) / 2 else "right"
        raise AssertionError("marker not found")

    def test_a_negative_x_scale_mirrors_horizontally(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(
            _swatch(20, 10, MARK), Vector2(100, 100), scale=Vector2(-1, 1)
        )

        assert self._mark_side(screen, _opaque_box(screen)) == "right"

    def test_a_positive_x_scale_does_not(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(_swatch(20, 10, MARK), Vector2(100, 100))

        assert self._mark_side(screen, _opaque_box(screen)) == "left"

    def test_mirroring_does_not_move_it(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(_swatch(20, 10), Vector2(100, 100))
        forward = _opaque_box(screen)
        screen.fill((0, 0, 0, 0))

        renderer.draw_texture(_swatch(20, 10), Vector2(100, 100), scale=Vector2(-1, 1))

        assert _opaque_box(screen) == forward

    def test_a_mirror_still_scales(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(_swatch(20, 10), Vector2(100, 100), scale=Vector2(-2, 2))

        left, top, right, bottom = _opaque_box(screen)
        assert (right - left, bottom - top) == (40, 20)


class TestItRotates:
    """It used to drop `rotation` too."""

    def test_a_quarter_turn_swaps_the_axes(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        renderer.draw_texture(_swatch(30, 10), Vector2(100, 100), rotation=90.0)

        left, top, right, bottom = _opaque_box(screen)
        assert (right - left) == pytest.approx(10, abs=2)
        assert (bottom - top) == pytest.approx(30, abs=2)

    def test_it_turns_about_its_own_centre(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        """Rotating about a corner would walk the sprite off its position."""
        renderer.draw_texture(_swatch(30, 10), Vector2(100, 100), rotation=90.0)

        left, top, right, bottom = _opaque_box(screen)
        assert (left + right) // 2 == pytest.approx(100, abs=2)
        assert (top + bottom) // 2 == pytest.approx(100, abs=2)


class TestItFiltersLikeTheRestOfTheBackend:
    """`render_batch` scales nearest-neighbour; this must not differ."""

    def test_an_upscale_keeps_its_hard_edges(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        """Smooth scaling would blur a pixel-art sprite into its
        neighbours; the one red pixel would stop being red."""
        renderer.draw_texture(
            _swatch(4, 4, MARK), Vector2(100, 100), scale=Vector2(8, 8)
        )

        left, top, _, _ = _opaque_box(screen)
        assert screen.get_at((left + 1, top + 1)) == MARK

    def test_it_turns_the_same_way_the_batch_path_does(
        self, renderer: PygameBackend, screen: pygame.Surface
    ) -> None:
        """Clockwise for a positive angle, matching `render_batch`'s own
        negation and the GL backend's rotation matrix."""
        # A wide bar with its marker on the left end. A clockwise quarter
        # turn puts that end at the top.
        renderer.draw_texture(_swatch(40, 4, MARK), Vector2(100, 100), rotation=90.0)

        left, top, right, bottom = _opaque_box(screen)
        found = [
            y
            for y in range(top, bottom)
            for x in range(left, right)
            if screen.get_at((x, y)) == MARK
        ]
        assert found, "marker not found"
        assert min(found) < (top + bottom) / 2, "the marked end should be on top"
