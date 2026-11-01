"""`NinePatchPanel` and `Image.source_rect`: the widgets over `render_ninepatch`."""

from __future__ import annotations

import pygame

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.ninepatch import NinePatchMetrics, NinePatchSprite
from pyguara.ui.builder import UIBuilder
from pyguara.ui.components.image import Image
from pyguara.ui.components.nine_patch_panel import NinePatchPanel
from pyguara.ui.components.panel import Panel

RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
GREEN = (0, 255, 0, 255)


def _plate() -> pygame.Surface:
    """12x12: a 4 px red frame around a blue centre."""
    plate = pygame.Surface((12, 12), pygame.SRCALPHA)
    plate.fill(RED)
    plate.fill(BLUE, pygame.Rect(4, 4, 4, 4))
    return plate


def _sprite(source_rect: Rect | None = None) -> NinePatchSprite:
    return NinePatchSprite(
        "unused.png", NinePatchMetrics.uniform(4), source_rect=source_rect
    )


def _target() -> pygame.Surface:
    target = pygame.Surface((64, 64), pygame.SRCALPHA)
    target.fill(GREEN)
    return target


class TestNinePatchPanelDraws:
    """Against real pixels, not a recorder: the slices have to land."""

    def test_the_frame_holds_its_size_and_the_centre_stretches(self) -> None:
        target = _target()
        panel = NinePatchPanel(_plate(), _sprite(), Vector2(8, 8), Vector2(40, 40))

        panel.render(PygameUIRenderer(target))

        assert tuple(target.get_at((9, 9))) == RED
        assert tuple(target.get_at((11, 28))) == RED
        assert tuple(target.get_at((12, 12))) == BLUE
        assert tuple(target.get_at((43, 43))) == BLUE
        assert tuple(target.get_at((44, 44))) == RED
        assert tuple(target.get_at((48, 48))) == GREEN

    def test_an_atlas_region_is_drawn_from_its_own_corner(self) -> None:
        atlas = pygame.Surface((32, 32), pygame.SRCALPHA)
        atlas.fill(GREEN)
        atlas.blit(_plate(), (20, 20))
        target = _target()
        panel = NinePatchPanel(
            atlas, _sprite(Rect(20, 20, 12, 12)), Vector2(0, 0), Vector2(30, 30)
        )

        panel.render(PygameUIRenderer(target))

        assert tuple(target.get_at((1, 1))) == RED
        assert tuple(target.get_at((15, 15))) == BLUE

    def test_children_draw_on_top_of_the_plate(self) -> None:
        target = _target()
        panel = NinePatchPanel(_plate(), _sprite(), Vector2(0, 0), Vector2(40, 40))
        panel.add_child(Panel(Vector2(15, 15), Vector2(10, 10), color=Color(9, 9, 9)))

        panel.render(PygameUIRenderer(target))

        assert tuple(target.get_at((20, 20)))[:3] == (9, 9, 9)


class TestImageSourceRect:
    def test_it_draws_only_the_named_region(self) -> None:
        target = _target()
        image = Image(
            _plate(), Vector2(0, 0), Vector2(8, 8), source_rect=Rect(4, 4, 4, 4)
        )

        image.render(PygameUIRenderer(target))

        assert tuple(target.get_at((0, 0))) == BLUE
        assert tuple(target.get_at((7, 7))) == BLUE

    def test_without_one_it_draws_the_whole_texture(self) -> None:
        target = _target()

        Image(_plate(), Vector2(0, 0), Vector2(12, 12)).render(PygameUIRenderer(target))

        assert tuple(target.get_at((0, 0))) == RED
        assert tuple(target.get_at((6, 6))) == BLUE


class TestTheBuilder:
    def test_a_nine_patch_panel_is_a_container(self) -> None:
        plate, sprite = _plate(), _sprite()
        with (
            UIBuilder() as ui,
            ui.nine_patch_panel(plate, sprite, Vector2(1, 2), Vector2(30, 40)) as panel,
        ):
            label = ui.label("inside")

        assert isinstance(panel, NinePatchPanel)
        assert panel.texture is plate
        assert label in panel.children

    def test_an_image_passes_its_source_rect_through(self) -> None:
        region = Rect(4, 4, 4, 4)
        with UIBuilder() as ui:
            image = ui.image(_plate(), Vector2(0, 0), Vector2(8, 8), source_rect=region)

        assert image.source_rect == region
