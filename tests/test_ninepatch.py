"""Tests for nine-patch sprite system."""

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.ninepatch import (
    NinePatchMetrics,
    NinePatchSprite,
    render_ninepatch,
    texture_size,
)


class TestNinePatchMetrics:
    """Test nine-patch metrics creation."""

    def test_uniform_metrics(self):
        """Uniform metrics should set all edges to same size."""
        metrics = NinePatchMetrics.uniform(10)

        assert metrics.left == 10
        assert metrics.right == 10
        assert metrics.top == 10
        assert metrics.bottom == 10

    def test_symmetric_metrics(self):
        """Symmetric metrics should set horizontal and vertical pairs."""
        metrics = NinePatchMetrics.symmetric(horizontal=15, vertical=10)

        assert metrics.left == 15
        assert metrics.right == 15
        assert metrics.top == 10
        assert metrics.bottom == 10

    def test_custom_metrics(self):
        """Custom metrics should allow individual edge sizes."""
        metrics = NinePatchMetrics(left=5, right=10, top=15, bottom=20)

        assert metrics.left == 5
        assert metrics.right == 10
        assert metrics.top == 15
        assert metrics.bottom == 20


class TestNinePatchSprite:
    """Test nine-patch sprite functionality."""

    def test_sprite_creation(self):
        """Nine-patch sprite should be created with basic properties."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        assert sprite.texture_path == "button.png"
        assert sprite.metrics == metrics
        assert sprite.source_rect is None
        assert sprite.min_size is None

    def test_get_min_size_from_metrics(self):
        """Minimum size should be calculated from metrics if not specified."""
        metrics = NinePatchMetrics(left=10, right=15, top=8, bottom=12)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        min_size = sprite.get_min_size()

        assert min_size.x == 25  # 10 + 15
        assert min_size.y == 20  # 8 + 12

    def test_get_min_size_explicit(self):
        """Explicit minimum size should be used if provided."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(
            texture_path="button.png",
            metrics=metrics,
            min_size=Vector2(50, 40),
        )

        min_size = sprite.get_min_size()

        assert min_size.x == 50
        assert min_size.y == 40

    def test_get_patch_rects_uniform(self):
        """Patch rectangles should be calculated correctly for uniform metrics."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Source texture is 100x100
        src_rects = sprite.get_patch_rects(100, 100)

        # Check corners (fixed size)
        assert src_rects[0] == Rect(0, 0, 10, 10)  # Top-Left
        assert src_rects[2] == Rect(90, 0, 10, 10)  # Top-Right
        assert src_rects[6] == Rect(0, 90, 10, 10)  # Bottom-Left
        assert src_rects[8] == Rect(90, 90, 10, 10)  # Bottom-Right

        # Check edges
        assert src_rects[1] == Rect(10, 0, 80, 10)  # Top edge
        assert src_rects[3] == Rect(0, 10, 10, 80)  # Left edge
        assert src_rects[5] == Rect(90, 10, 10, 80)  # Right edge
        assert src_rects[7] == Rect(10, 90, 80, 10)  # Bottom edge

        # Check center
        assert src_rects[4] == Rect(10, 10, 80, 80)  # Center

    def test_get_patch_rects_asymmetric(self):
        """Patch rectangles should handle asymmetric metrics."""
        metrics = NinePatchMetrics(left=5, right=15, top=10, bottom=20)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Source texture is 100x100
        src_rects = sprite.get_patch_rects(100, 100)

        # Check corners with different sizes
        assert src_rects[0] == Rect(0, 0, 5, 10)  # Top-Left
        assert src_rects[2] == Rect(85, 0, 15, 10)  # Top-Right
        assert src_rects[6] == Rect(0, 80, 5, 20)  # Bottom-Left
        assert src_rects[8] == Rect(85, 80, 15, 20)  # Bottom-Right

        # Check center dimensions
        assert src_rects[4] == Rect(5, 10, 80, 70)  # 100-5-15=80, 100-10-20=70

    def test_get_dest_rects_no_stretch(self):
        """Destination rects should match source when rendering at minimum size."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Render at exactly min size (20x20)
        dest_rects = sprite.get_dest_rects(x=0, y=0, width=20, height=20)

        # Corners should be 10x10
        assert dest_rects[0] == Rect(0, 0, 10, 10)  # Top-Left
        assert dest_rects[2] == Rect(10, 0, 10, 10)  # Top-Right
        assert dest_rects[6] == Rect(0, 10, 10, 10)  # Bottom-Left
        assert dest_rects[8] == Rect(10, 10, 10, 10)  # Bottom-Right

        # Edges and center should be 0 size (no stretching)
        assert dest_rects[1] == Rect(10, 0, 0, 10)  # Top edge
        assert dest_rects[4] == Rect(10, 10, 0, 0)  # Center

    def test_get_dest_rects_with_stretch(self):
        """Destination rects should stretch properly when larger than min size."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Render at 100x80 (larger than min 20x20)
        dest_rects = sprite.get_dest_rects(x=0, y=0, width=100, height=80)

        # Corners stay 10x10
        assert dest_rects[0] == Rect(0, 0, 10, 10)  # Top-Left
        assert dest_rects[2] == Rect(90, 0, 10, 10)  # Top-Right
        assert dest_rects[6] == Rect(0, 70, 10, 10)  # Bottom-Left
        assert dest_rects[8] == Rect(90, 70, 10, 10)  # Bottom-Right

        # Edges stretch
        assert dest_rects[1] == Rect(10, 0, 80, 10)  # Top edge (stretch width)
        assert dest_rects[3] == Rect(0, 10, 10, 60)  # Left edge (stretch height)
        assert dest_rects[5] == Rect(90, 10, 10, 60)  # Right edge (stretch height)
        assert dest_rects[7] == Rect(10, 70, 80, 10)  # Bottom edge (stretch width)

        # Center stretches in both directions
        assert dest_rects[4] == Rect(10, 10, 80, 60)  # Center

    def test_get_dest_rects_with_offset(self):
        """Destination rects should account for position offset."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Render at position (50, 30) with size 60x50
        dest_rects = sprite.get_dest_rects(x=50, y=30, width=60, height=50)

        # Check that positions are offset
        assert dest_rects[0] == Rect(50, 30, 10, 10)  # Top-Left
        assert dest_rects[2] == Rect(100, 30, 10, 10)  # Top-Right (50+60-10)
        assert dest_rects[6] == Rect(50, 70, 10, 10)  # Bottom-Left (30+50-10)
        assert dest_rects[8] == Rect(100, 70, 10, 10)  # Bottom-Right

        # Check stretched dimensions
        assert dest_rects[4] == Rect(60, 40, 40, 30)  # Center (60-20, 50-20)

    def test_get_dest_rects_enforces_min_size(self):
        """Destination rects should not render smaller than minimum size."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Try to render at 10x10 (smaller than min 20x20)
        dest_rects = sprite.get_dest_rects(x=0, y=0, width=10, height=10)

        # Should be clamped to min size (20x20)
        # Total width should be 20 (left 10 + center 0 + right 10)
        assert dest_rects[0].width == 10
        assert dest_rects[2].x == 10  # Right corner at x=10
        assert dest_rects[8].y == 10  # Bottom corner at y=10


class TestNinePatchUsagePatterns:
    """Test common usage patterns for nine-patch sprites."""

    def test_button_with_uniform_corners(self):
        """Common pattern: button with uniform corner radius."""
        # Button texture with 8px rounded corners
        metrics = NinePatchMetrics.uniform(8)
        button = NinePatchSprite(
            texture_path="assets/button.png",
            metrics=metrics,
        )

        # Render at various sizes
        dest_small = button.get_dest_rects(x=10, y=10, width=64, height=32)
        dest_large = button.get_dest_rects(x=10, y=10, width=200, height=60)

        # Corners always 8x8
        assert dest_small[0] == Rect(10, 10, 8, 8)
        assert dest_large[0] == Rect(10, 10, 8, 8)

        # Centers scale appropriately
        assert dest_small[4].width == 48  # 64 - 16
        assert dest_large[4].width == 184  # 200 - 16

    def test_panel_with_thick_border(self):
        """Common pattern: panel with decorative border."""
        # Panel with 20px ornate border on all sides
        metrics = NinePatchMetrics.uniform(20)
        panel = NinePatchSprite(
            texture_path="assets/panel.png",
            metrics=metrics,
        )

        # Large panel
        dest_rects = panel.get_dest_rects(x=0, y=0, width=400, height=300)

        # Border stays 20px
        assert dest_rects[1].height == 20  # Top edge
        assert dest_rects[3].width == 20  # Left edge

        # Large content area
        assert dest_rects[4].width == 360  # 400 - 40
        assert dest_rects[4].height == 260  # 300 - 40

    def test_dialog_with_title_bar(self):
        """Common pattern: dialog with asymmetric top bar."""
        # Dialog with 30px title bar, 10px other edges
        metrics = NinePatchMetrics(left=10, right=10, top=30, bottom=10)
        dialog = NinePatchSprite(
            texture_path="assets/dialog.png",
            metrics=metrics,
        )

        dest_rects = dialog.get_dest_rects(x=100, y=100, width=300, height=200)

        # Title bar is 30px
        assert dest_rects[1].height == 30  # Top edge

        # Other edges are 10px
        assert dest_rects[3].width == 10  # Left edge
        assert dest_rects[7].height == 10  # Bottom edge

        # Content area accounts for asymmetry
        assert dest_rects[4].height == 160  # 200 - 30 - 10


class TestNinePatchMetricsValidation:
    """Negative edges produce negative-width rects that reach the renderer as
    geometry rather than as an error."""

    def test_negative_edges_are_rejected(self):
        import pytest

        from pyguara.graphics.ninepatch import NinePatchMetrics

        with pytest.raises(ValueError, match="cannot be negative"):
            NinePatchMetrics.uniform(-5)

    def test_the_error_names_the_offending_edges(self):
        import pytest

        from pyguara.graphics.ninepatch import NinePatchMetrics

        with pytest.raises(ValueError, match="'right'"):
            NinePatchMetrics(left=4, right=-1, top=4, bottom=4)

    def test_zero_edges_are_allowed(self):
        from pyguara.graphics.ninepatch import NinePatchMetrics

        assert NinePatchMetrics.uniform(0).left == 0


class TestNinePatchSourceRects:
    """get_dest_rects clamped its input; get_patch_rects did not.

    Edges wider than the source leave the centre with negative extent, and five
    of the nine source rects came out with negative width or height --
    e.g. Rect(x=40, y=0, width=-32, height=40) for uniform(40) on a 48px
    texture.
    """

    def _sprite(self, edge: int, size: int = 48):
        from unittest.mock import MagicMock

        from pyguara.graphics.ninepatch import NinePatchMetrics, NinePatchSprite

        texture = MagicMock()
        texture.width = size
        texture.height = size
        return NinePatchSprite(texture, NinePatchMetrics.uniform(edge))

    def test_edges_wider_than_the_source_are_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="do not fit the source"):
            self._sprite(40).get_patch_rects(48, 48)

    def test_the_error_reports_both_the_edges_and_the_texture(self):
        import pytest

        with pytest.raises(ValueError, match="40\\+40.*48x48"):
            self._sprite(40).get_patch_rects(48, 48)

    def test_edges_exactly_filling_the_source_are_allowed(self):
        """left+right == width leaves a zero-width centre, which is degenerate
        but not negative -- a legitimate patch with no stretchable middle."""
        rects = self._sprite(24).get_patch_rects(48, 48)

        assert len(rects) == 9
        assert all(r.width >= 0 and r.height >= 0 for r in rects)

    def test_valid_metrics_produce_nine_non_negative_rects(self):
        rects = self._sprite(16).get_patch_rects(48, 48)

        assert len(rects) == 9
        assert all(r.width >= 0 and r.height >= 0 for r in rects)

    def test_the_source_rects_tile_the_texture(self):
        rects = self._sprite(16).get_patch_rects(48, 48)
        covered = sum(r.width * r.height for r in rects)

        assert covered == 48 * 48

    def test_destination_rects_stay_clamped_for_a_tiny_target(self):
        """The destination side already handled this; the test pins it so the
        two sides cannot diverge again."""
        rects = self._sprite(16).get_dest_rects(0, 0, 4, 4)

        assert all(r.width >= 0 and r.height >= 0 for r in rects)


class TestTheSourceRectsFollowTheSpriteIntoAnAtlas:
    """`NinePatchSprite.source_rect` was declared, documented as "Source
    rectangle in the texture", and read by nothing in the class, so a
    nine-patch packed into an atlas reported its slices at the atlas's
    own origin -- it would have drawn whatever happened to sit in the
    sheet's top-left corner."""

    @staticmethod
    def _at(origin: tuple[int, int], size: int = 16, edge: int = 4):
        return NinePatchSprite(
            texture_path="atlas.png",
            metrics=NinePatchMetrics.uniform(edge),
            source_rect=Rect(origin[0], origin[1], size, size),
        )

    def test_the_slices_are_offset_by_the_regions_origin(self):
        rects = self._at((100, 200)).get_patch_rects(16, 16)

        assert rects[0] == Rect(100, 200, 4, 4)

    def test_every_slice_stays_inside_the_region(self):
        region = Rect(100, 200, 16, 16)
        rects = self._at((100, 200)).get_patch_rects(16, 16)

        assert all(
            region.x <= r.x and r.x + r.width <= region.x + region.width for r in rects
        )
        assert all(
            region.y <= r.y and r.y + r.height <= region.y + region.height
            for r in rects
        )

    def test_the_slices_still_tile_the_region(self):
        rects = self._at((100, 200)).get_patch_rects(16, 16)

        assert sum(r.width * r.height for r in rects) == 16 * 16

    def test_the_regions_own_extent_wins_over_the_arguments(self):
        """A caller that passes the whole sheet's size, which is what it
        has to hand, must not get slices sized to the sheet."""
        rects = self._at((100, 200), size=16).get_patch_rects(512, 512)

        assert rects[4] == Rect(104, 204, 8, 8)

    def test_a_sprite_without_a_region_is_unchanged(self):
        """The two existing callers pass a bare texture; nothing about them
        may move."""
        bare = NinePatchSprite(
            texture_path="panel.png", metrics=NinePatchMetrics.uniform(4)
        )

        assert bare.get_patch_rects(16, 16)[0] == Rect(0, 0, 4, 4)

    def test_edges_too_big_for_the_region_are_still_rejected(self):
        """The fit check has to measure the region, not the sheet, or an
        atlas entry escapes it entirely."""
        import pytest

        sprite = self._at((100, 200), size=16, edge=12)

        with pytest.raises(ValueError, match="12\\+12.*16x16"):
            sprite.get_patch_rects(512, 512)


class TestRenderNinepatchActuallyDraws:
    """It was a `pass` with a comment explaining that a real implementation
    would need the texture's size -- while being exported from
    `pyguara.graphics.__init__`, so the public API included a function
    that drew nothing."""

    @staticmethod
    def _recorder():
        calls: list[tuple[Rect, Rect | None]] = []

        class Recording:
            def draw_texture(self, texture, rect, color=None, source_rect=None):
                calls.append((rect, source_rect))

        return Recording(), calls

    @staticmethod
    def _texture(width: int = 16, height: int = 16):
        class Sized:
            def __init__(self) -> None:
                self.width = width
                self.height = height

        return Sized()

    def test_nine_slices_reach_the_renderer(self):
        renderer, calls = self._recorder()
        sprite = NinePatchSprite(
            texture_path="panel.png", metrics=NinePatchMetrics.uniform(4)
        )

        drawn = render_ninepatch(renderer, sprite, self._texture(), 0, 0, 64, 32)

        assert drawn == 9
        assert len(calls) == 9

    def test_every_slice_names_its_own_source_region(self):
        """Nine draws of the whole texture would also be nine draws; the
        point is that each is a different region of it."""
        renderer, calls = self._recorder()
        sprite = NinePatchSprite(
            texture_path="panel.png", metrics=NinePatchMetrics.uniform(4)
        )

        render_ninepatch(renderer, sprite, self._texture(), 0, 0, 64, 32)

        sources = [source for _, source in calls]
        assert all(source is not None for source in sources)
        assert len({(s.x, s.y, s.width, s.height) for s in sources if s}) == 9

    def test_the_corners_keep_their_size_and_the_centre_stretches(self):
        """The whole reason a nine-patch exists."""
        renderer, calls = self._recorder()
        sprite = NinePatchSprite(
            texture_path="panel.png", metrics=NinePatchMetrics.uniform(4)
        )

        render_ninepatch(renderer, sprite, self._texture(), 0, 0, 64, 32)

        top_left = calls[0][0]
        centre = calls[4][0]
        assert top_left.size == (4, 4)
        assert centre.size == (64 - 8, 32 - 8)

    def test_the_destination_is_covered_exactly(self):
        renderer, calls = self._recorder()
        sprite = NinePatchSprite(
            texture_path="panel.png", metrics=NinePatchMetrics.uniform(4)
        )

        render_ninepatch(renderer, sprite, self._texture(), 10, 20, 64, 32)

        covered = sum(rect.width * rect.height for rect, _ in calls)
        assert covered == 64 * 32
        assert min(rect.x for rect, _ in calls) == 10
        assert max(rect.x + rect.width for rect, _ in calls) == 74

    def test_an_atlas_backed_sprite_draws_from_its_own_region(self):
        renderer, calls = self._recorder()
        sprite = NinePatchSprite(
            texture_path="atlas.png",
            metrics=NinePatchMetrics.uniform(4),
            source_rect=Rect(100, 200, 16, 16),
        )

        render_ninepatch(renderer, sprite, self._texture(512, 512), 0, 0, 64, 32)

        assert calls[0][1] == Rect(100, 200, 4, 4)

    def test_a_zero_width_edge_skips_its_three_slices(self):
        """`metrics.left == 0` is legal -- a plate with no left border --
        and makes three destination rects zero-width. Drawing them would
        reach `transform.scale`, which raises on a zero extent."""
        renderer, calls = self._recorder()
        sprite = NinePatchSprite(
            texture_path="panel.png",
            metrics=NinePatchMetrics(left=0, right=4, top=4, bottom=4),
        )

        drawn = render_ninepatch(renderer, sprite, self._texture(), 0, 0, 64, 32)

        assert drawn == 6
        assert all(rect.width > 0 and rect.height > 0 for rect, _ in calls)

    def test_a_tint_reaches_every_slice(self):
        tints: list[object] = []

        class Recording:
            def draw_texture(self, texture, rect, color=None, source_rect=None):
                tints.append(color)

        sprite = NinePatchSprite(
            texture_path="panel.png", metrics=NinePatchMetrics.uniform(4)
        )
        red = Color(255, 0, 0, 255)

        render_ninepatch(Recording(), sprite, self._texture(), 0, 0, 64, 32, red)

        assert tints == [red] * 9


class TestTheTextureSizeIsReadFromEitherShapeOfTexture:
    """`UIRenderer.draw_texture` is annotated `texture: Any` and the real
    backends want a `pygame.Surface`, while the world side passes a
    `resources.Texture`. Both reach a UI renderer, so both have to work
    here, and `Any` tells a caller nothing about which."""

    def test_a_resource_texture_answers_through_its_properties(self):
        class Wrapped:
            width = 32
            height = 48

        assert texture_size(Wrapped()) == (32, 48)

    def test_a_backend_surface_answers_through_its_getters(self):
        import pygame

        pygame.init()
        try:
            assert texture_size(pygame.Surface((32, 48))) == (32, 48)
        finally:
            pygame.quit()

    def test_anything_else_is_refused_by_name(self):
        """At the boundary, not four slices into the loop with an
        AttributeError from inside a draw call."""
        import pytest

        with pytest.raises(TypeError, match="str has neither"):
            texture_size("assets/panel.png")


class TestARealRendererProducesTheExpectedPixels:
    """The recorder above proves nine regions reach a renderer with the
    right geometry. This proves a real one turns them into the frame a
    nine-patch is for: corners at their own size, edges stretched along
    one axis, centre along both, and no seam between them.

    Driven through `PygameUIRenderer`, which is the same `blit_texture`
    the ModernGL UI renderer uses.
    """

    CELLS = [
        [(200, 0, 0), (0, 200, 0), (0, 0, 200)],
        [(200, 200, 0), (200, 200, 200), (0, 200, 200)],
        [(100, 0, 100), (0, 100, 0), (0, 0, 100)],
    ]
    """Nine distinguishable colours, one per patch, so a slice drawn from
    the wrong region shows up as the wrong colour rather than as nothing."""

    def _texture(self, pygame, cell: int = 3):
        texture = pygame.Surface((cell * 3, cell * 3), pygame.SRCALPHA)
        for row in range(3):
            for column in range(3):
                red, green, blue = self.CELLS[row][column]
                texture.fill(
                    (red, green, blue, 255),
                    pygame.Rect(column * cell, row * cell, cell, cell),
                )
        return texture

    def _render(self, size: int = 15, cell: int = 3):
        import pygame

        from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer

        pygame.init()
        target = pygame.Surface((size, size), pygame.SRCALPHA)
        sprite = NinePatchSprite(
            texture_path="plate.png", metrics=NinePatchMetrics.uniform(cell)
        )
        drawn = render_ninepatch(
            PygameUIRenderer(target),
            sprite,
            self._texture(pygame, cell),
            0,
            0,
            size,
            size,
        )
        return target, drawn

    def test_every_pixel_of_the_destination_is_covered(self):
        """Nine rects that tile the destination must leave no gap. A
        rounding slip in the stretched spans shows up here as a
        transparent seam."""
        import pygame

        target, drawn = self._render()
        try:
            assert drawn == 9
            transparent = [
                (x, y)
                for x in range(15)
                for y in range(15)
                if target.get_at((x, y)).a == 0
            ]
            assert transparent == []
        finally:
            pygame.quit()

    def test_the_corners_are_their_own_colours_at_their_own_size(self):
        import pygame

        target, _ = self._render()
        try:
            assert tuple(target.get_at((0, 0)))[:3] == self.CELLS[0][0]
            assert tuple(target.get_at((14, 0)))[:3] == self.CELLS[0][2]
            assert tuple(target.get_at((0, 14)))[:3] == self.CELLS[2][0]
            assert tuple(target.get_at((14, 14)))[:3] == self.CELLS[2][2]
            # One pixel past the corner is already the stretched edge.
            assert tuple(target.get_at((3, 0)))[:3] == self.CELLS[0][1]
        finally:
            pygame.quit()

    def test_the_centre_is_stretched_across_the_middle(self):
        import pygame

        target, _ = self._render()
        try:
            middle = {
                tuple(target.get_at((x, y)))[:3]
                for x in range(3, 12)
                for y in range(3, 12)
            }
            assert middle == {self.CELLS[1][1]}
        finally:
            pygame.quit()

    def test_the_edges_stretch_along_one_axis_only(self):
        """The top edge is one colour across its whole span and the left
        edge down its whole span -- if the implementation stretched a
        corner instead, these would be two colours."""
        import pygame

        target, _ = self._render()
        try:
            top = {tuple(target.get_at((x, 1)))[:3] for x in range(3, 12)}
            left = {tuple(target.get_at((1, y)))[:3] for y in range(3, 12)}
            assert top == {self.CELLS[0][1]}
            assert left == {self.CELLS[1][0]}
        finally:
            pygame.quit()

    def test_a_destination_at_the_minimum_degenerates_to_four_corners(self):
        """`get_dest_rects` clamps up to the minimum rather than letting the
        corners overlap, and at exactly that minimum the stretchable spans
        are all zero -- so a nine-patch is four corners and nothing else.
        Worth pinning because it is the case that would otherwise reach
        `transform.scale` with a zero extent and raise, and because a
        caller sizing a panel to its content can land here by accident."""
        import pygame

        target, drawn = self._render(size=4)
        try:
            assert drawn == 4
            # The corners still cover the whole visible target: the clamp
            # means the draw is 6x6 and pygame clips it to the surface.
            assert all(
                target.get_at((x, y)).a == 255 for x in range(4) for y in range(4)
            )
        finally:
            pygame.quit()
