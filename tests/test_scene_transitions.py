"""Tests for scene transition system."""

import math
from unittest.mock import Mock

import pytest

from pyguara.common.types import Color
from pyguara.scene.transitions import (
    DEFAULT_WIPE_SEGMENTS,
    CircularWipeTransition,
    EasingFunction,
    FadeTransition,
    SlideTransition,
    TransitionConfig,
    TransitionManager,
    TransitionState,
    WipeTransition,
    apply_easing,
    circular_cover_points,
    fully_revealed_radius,
)


class TestEasingFunctions:
    """Test easing function calculations."""

    def test_linear_easing(self):
        """Linear easing should return input unchanged."""
        assert apply_easing(0.0, EasingFunction.LINEAR) == 0.0
        assert apply_easing(0.5, EasingFunction.LINEAR) == 0.5
        assert apply_easing(1.0, EasingFunction.LINEAR) == 1.0

    def test_ease_in(self):
        """Ease in should start slow."""
        result = apply_easing(0.5, EasingFunction.EASE_IN)
        assert 0.0 < result < 0.5  # Slower than linear

    def test_ease_out(self):
        """Ease out should end slow."""
        result = apply_easing(0.5, EasingFunction.EASE_OUT)
        assert result > 0.5  # Faster than linear

    def test_ease_in_out(self):
        """Ease in-out should be slow at start and end."""
        result_early = apply_easing(0.25, EasingFunction.EASE_IN_OUT)
        result_late = apply_easing(0.75, EasingFunction.EASE_IN_OUT)
        assert result_early < 0.25
        assert result_late > 0.75

    def test_easing_clamping(self):
        """Easing should clamp values to [0, 1]."""
        assert apply_easing(-0.5, EasingFunction.LINEAR) == 0.0
        assert apply_easing(1.5, EasingFunction.LINEAR) == 1.0


class TestTransitionConfig:
    """Test transition configuration."""

    def test_config_defaults(self):
        """TransitionConfig should have sensible defaults."""
        config = TransitionConfig()

        assert config.duration == 0.5
        assert config.easing == EasingFunction.EASE_IN_OUT
        assert config.color == Color(0, 0, 0, 255)
        assert config.two_phase is True

    def test_config_custom_values(self):
        """TransitionConfig should accept custom values."""
        config = TransitionConfig(
            duration=1.0,
            easing=EasingFunction.LINEAR,
            color=Color(255, 255, 255, 255),
            two_phase=False,
        )

        assert config.duration == 1.0
        assert config.easing == EasingFunction.LINEAR
        assert config.color == Color(255, 255, 255, 255)
        assert config.two_phase is False


class TestFadeTransition:
    """Test fade transition effect."""

    def test_fade_creation(self):
        """FadeTransition should be created with default config."""
        fade = FadeTransition()

        assert fade.progress == 0.0
        assert fade.state == TransitionState.IDLE
        assert isinstance(fade.config, TransitionConfig)

    def test_fade_start(self):
        """Starting fade should reset progress."""
        fade = FadeTransition()
        fade.progress = 0.5

        fade.start()

        assert fade.progress == 0.0
        assert fade.state == TransitionState.TRANSITIONING_OUT

    def test_fade_update_progress(self):
        """Fade should update progress over time."""
        config = TransitionConfig(duration=1.0)
        fade = FadeTransition(config)
        fade.start()

        # Update half duration
        complete = fade.update(0.5)

        assert not complete
        assert fade.progress == 0.5

    def test_fade_completion(self):
        """Fade should complete after full duration."""
        config = TransitionConfig(duration=1.0)
        fade = FadeTransition(config)
        fade.start()

        # Update full duration
        complete = fade.update(1.0)

        assert complete
        assert fade.state == TransitionState.COMPLETE

    def test_fade_two_phase(self):
        """Two-phase fade should transition through both states."""
        config = TransitionConfig(duration=1.0, two_phase=True)
        fade = FadeTransition(config)
        fade.start()

        # First half
        fade.update(0.5)
        assert fade.state == TransitionState.TRANSITIONING_IN

        # Second half
        complete = fade.update(0.5)
        assert complete
        assert fade.state == TransitionState.COMPLETE

    def test_fade_single_phase(self):
        """Single-phase fade should complete at end."""
        config = TransitionConfig(duration=1.0, two_phase=False)
        fade = FadeTransition(config)
        fade.start()

        fade.update(0.5)
        assert fade.state == TransitionState.TRANSITIONING_OUT

        complete = fade.update(0.5)
        assert complete

    def test_fade_render(self):
        """Fade should render with alpha overlay."""
        fade = FadeTransition()
        fade.start()
        fade.update(0.25)

        # Mock renderers
        world_renderer = Mock()
        ui_renderer = Mock()

        fade.render(world_renderer, ui_renderer, 800, 600)

        # Should have called draw_rect with overlay
        assert ui_renderer.draw_rect.called


class TestSlideTransition:
    """Test slide transition effect."""

    def test_slide_creation(self):
        """SlideTransition should be created with direction."""
        slide = SlideTransition(direction="left")

        assert slide.direction == "left"
        assert slide.state == TransitionState.IDLE

    def test_slide_directions(self):
        """Slide should support all directions."""
        for direction in ["left", "right", "up", "down"]:
            slide = SlideTransition(direction=direction)
            assert slide.direction == direction

    def test_slide_render(self):
        """Slide should render black bars."""
        slide = SlideTransition(direction="left")
        slide.start()
        slide.update(0.25)

        world_renderer = Mock()
        ui_renderer = Mock()

        slide.render(world_renderer, ui_renderer, 800, 600)

        assert ui_renderer.draw_rect.called


class TestWipeTransition:
    """Test wipe transition effect."""

    def test_wipe_creation(self):
        """WipeTransition should be created with direction."""
        wipe = WipeTransition(direction="left_to_right")

        assert wipe.direction == "left_to_right"

    def test_wipe_directions(self):
        """Wipe should support all directions."""
        for direction in [
            "left_to_right",
            "right_to_left",
            "top_to_bottom",
            "bottom_to_top",
        ]:
            wipe = WipeTransition(direction=direction)
            assert wipe.direction == direction

    def test_wipe_render(self):
        """Wipe should render progressive overlay."""
        wipe = WipeTransition(direction="left_to_right")
        wipe.start()
        wipe.update(0.25)

        world_renderer = Mock()
        ui_renderer = Mock()

        wipe.render(world_renderer, ui_renderer, 800, 600)

        assert ui_renderer.draw_rect.called


class TestTransitionManager:
    """Test transition manager."""

    def test_manager_creation(self):
        """TransitionManager should initialize correctly."""
        manager = TransitionManager()

        assert manager.current_transition is None
        assert not manager.is_transitioning()

    def test_manager_set_screen_size(self):
        """Manager should store screen dimensions."""
        manager = TransitionManager()

        manager.set_screen_size(1920, 1080)

        assert manager.screen_width == 1920
        assert manager.screen_height == 1080

    def test_manager_start_transition(self):
        """Manager should start transitions."""
        manager = TransitionManager()
        transition = FadeTransition()
        from_scene = Mock()
        to_scene = Mock()

        manager.start_transition(transition, from_scene, to_scene)

        assert manager.is_transitioning()
        assert manager.current_transition == transition

    def test_manager_callback_on_complete(self):
        """Manager should call callback when transition completes."""
        manager = TransitionManager()
        config = TransitionConfig(duration=0.5, two_phase=False)
        transition = FadeTransition(config)
        from_scene = Mock()
        to_scene = Mock()

        callback_called = []

        def on_complete():
            callback_called.append(True)

        manager.start_transition(transition, from_scene, to_scene, on_complete)

        # Complete transition
        manager.update(0.5)

        assert len(callback_called) == 1
        assert not manager.is_transitioning()

    def test_manager_two_phase_transition(self):
        """Manager should handle two-phase transitions.

        Per the scene lifecycle repair (wayfinder ticket 07): both
        on_from_hidden/on_to_shown callbacks fire together at the
        phase-flip midpoint, not at transition start -- firing on_exit at
        start was SCENE-1's "push destroys the paused scene" bug.
        """
        manager = TransitionManager()
        config = TransitionConfig(duration=1.0, two_phase=True)
        transition = FadeTransition(config)
        from_scene = Mock()
        to_scene = Mock()

        manager.start_transition(
            transition,
            from_scene,
            to_scene,
            on_from_hidden=from_scene.on_exit,
            on_to_shown=to_scene.on_enter,
        )

        # Neither callback fires at start for a two-phase transition.
        assert not from_scene.on_exit.called
        assert not to_scene.on_enter.called

        # Midpoint: both fire together, and the new scene gets a settling update.
        manager.update(0.5)
        assert from_scene.on_exit.called
        assert to_scene.on_enter.called
        assert to_scene.update.called

        # Complete
        manager.update(0.5)
        assert not manager.is_transitioning()

    def test_manager_single_phase_transition(self):
        """Manager should handle single-phase transitions.

        Per the scene lifecycle repair: single-phase transitions show
        to_scene from frame one, so both callbacks fire at transition
        *start* -- lifecycle-equivalent to an immediate switch, just with a
        cosmetic overlay on top -- rather than deferred to completion.
        """
        manager = TransitionManager()
        config = TransitionConfig(duration=0.5, two_phase=False)
        transition = FadeTransition(config)
        from_scene = Mock()
        to_scene = Mock()

        manager.start_transition(
            transition,
            from_scene,
            to_scene,
            on_from_hidden=from_scene.on_exit,
            on_to_shown=to_scene.on_enter,
        )

        # Both callbacks fire immediately, not deferred to completion.
        assert from_scene.on_exit.called
        assert to_scene.on_enter.called

        # Complete
        manager.update(0.5)
        assert not manager.is_transitioning()


class TestTransitionIntegration:
    """Test transition system integration."""

    def test_fade_to_black_pattern(self):
        """Common pattern: fade to black transition."""
        config = TransitionConfig(
            duration=0.5, color=Color(0, 0, 0, 255), two_phase=True
        )
        fade = FadeTransition(config)

        fade.start()
        fade.update(0.1)  # Early in fade out (20% progress)

        # Progress should be in transition out phase
        assert fade.state == TransitionState.TRANSITIONING_OUT
        assert 0.0 < fade.get_eased_progress() < 1.0

    def test_slide_in_from_right(self):
        """Common pattern: slide in from right."""
        slide = SlideTransition(direction="left")  # Content slides left
        slide.start()

        # Render at various progress points
        world_renderer = Mock()
        ui_renderer = Mock()

        for progress in [0.0, 0.25, 0.5, 0.75, 1.0]:
            slide.progress = progress
            slide.render(world_renderer, ui_renderer, 800, 600)

            # Should render black bars
            assert ui_renderer.draw_rect.called
            ui_renderer.reset_mock()

    def test_quick_transition(self):
        """Test very short transition duration."""
        config = TransitionConfig(duration=0.1)
        fade = FadeTransition(config)
        fade.start()

        complete = fade.update(0.1)

        assert complete

    def test_custom_color_transition(self):
        """Test transition with custom color."""
        config = TransitionConfig(color=Color(255, 255, 255, 255))
        fade = FadeTransition(config)

        assert fade.config.color == Color(255, 255, 255, 255)


class TestTransitionUsagePatterns:
    """Test common usage patterns."""

    def test_menu_to_game_fade(self):
        """Common pattern: fade from menu to game."""
        manager = TransitionManager()
        manager.set_screen_size(800, 600)

        menu_scene = Mock()
        game_scene = Mock()

        fade = FadeTransition(TransitionConfig(duration=0.5))

        manager.start_transition(fade, menu_scene, game_scene)

        # Simulate game loop (31 frames to account for floating point precision)
        for _ in range(31):  # 31 frames at 60fps > 0.5s
            manager.update(1 / 60)

        assert not manager.is_transitioning()

    def test_level_transition_slide(self):
        """Common pattern: slide between levels."""
        manager = TransitionManager()

        level1 = Mock()
        level2 = Mock()

        slide = SlideTransition(TransitionConfig(duration=0.3), direction="left")

        completed = []

        manager.start_transition(slide, level1, level2, lambda: completed.append(True))

        # Fast forward
        manager.update(0.3)

        assert len(completed) == 1

    def test_death_fade_to_black(self):
        """Common pattern: fade to black on death."""
        config = TransitionConfig(
            duration=1.0, color=Color(0, 0, 0, 255), easing=EasingFunction.EASE_IN
        )
        fade = FadeTransition(config)

        fade.start()

        # Slow fade at start (ease in)
        fade.update(0.1)
        progress_early = fade.get_eased_progress()

        fade.update(0.4)
        progress_mid = fade.get_eased_progress()

        # Ease in means slower at start
        assert progress_mid > progress_early * 5

    def test_instant_scene_change(self):
        """Test instant scene change (no transition)."""
        manager = TransitionManager()

        # No transition = instant
        # This would be handled by SceneManager.switch_to(scene_name, transition=None)
        # TransitionManager should not be involved

        assert not manager.is_transitioning()


class TestTheCircularWipeGeometry:
    """The cover outline, asserted without a renderer.

    `circular_cover_points` is one self-touching outline -- round the
    window, in along a seam, round the circle the other way, back out -- so
    the interesting properties are about winding and about the two clamps
    at either end of the radius range.
    """

    def test_a_full_radius_covers_nothing(self) -> None:
        points = circular_cover_points(
            640, 360, fully_revealed_radius(1280, 720), 1280, 720
        )
        assert points == []

    def test_a_radius_past_full_also_covers_nothing(self) -> None:
        """Clamped, not extrapolated into a polygon turned inside out."""
        points = circular_cover_points(640, 360, 10_000, 1280, 720)
        assert points == []

    def test_a_zero_radius_is_the_plain_window_rectangle(self) -> None:
        """No hole means no seam, so the degenerate ring is not drawn at all."""
        points = circular_cover_points(640, 360, 0.0, 1280, 720)
        assert points == [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    def test_a_negative_radius_is_treated_as_zero(self) -> None:
        assert circular_cover_points(640, 360, -5.0, 1280, 720) == (
            circular_cover_points(640, 360, 0.0, 1280, 720)
        )

    @staticmethod
    def _split(points: list[tuple[int, int]]):
        """Return (seam, outer rectangle, ring) from one cover outline."""
        seam = points[0]
        seam_second = len(points) - 1 - points[::-1].index(seam)
        return seam, points[1:seam_second], points[seam_second + 1 : -1]

    def test_the_outline_closes_the_seam_on_both_sides(self) -> None:
        """The seam point appears twice, which is what cancels its edges.

        One traversal would leave the outline open and the fill would run
        out through the gap.
        """
        points = circular_cover_points(640, 360, 100.0, 1280, 720)
        assert points.count(points[0]) == 2

    def test_the_seam_begins_outside_the_hole(self) -> None:
        """It runs along the circle's centre line, from outside it.

        When the seam crossed the hole -- which it did, because the ring
        began at whichever vertex the construction produced first, on the
        *right* of the circle -- a scanline fill left a dotted line of
        cover colour across the revealed scene.
        """
        points = circular_cover_points(640, 360, 100.0, 1280, 720)
        seam, _, ring = self._split(points)
        assert seam[1] == 360, "the seam is on the circle's centre line"
        assert seam[0] < 640 - 100, "and starts beyond the circle's left edge"
        assert ring[0] == min(ring, key=lambda point: point[0]), (
            "so the ring must begin at its own leftmost vertex"
        )

    def test_the_ring_closes_on_itself(self) -> None:
        points = circular_cover_points(640, 360, 100.0, 1280, 720)
        _, _, ring = self._split(points)
        assert points[-1] == ring[0]

    def test_the_outer_loop_contains_the_circle(self) -> None:
        """Otherwise the cover is not an annulus and the fill misbehaves.

        For most of a wipe the circle is *larger* than the window -- at
        1280x720 it starts at radius 735 against a half-height of 360 --
        so an outer loop equal to the window is crossed by it, and the
        fill left a 42-pixel band of cover colour across the top of the
        revealed scene.
        """
        radius = 700.0
        points = circular_cover_points(640, 360, radius, 1280, 720)
        _, rect, _ = self._split(points)
        xs = [x for x, _ in rect]
        ys = [y for _, y in rect]
        assert min(xs) < 640 - radius
        assert max(xs) > 640 + radius
        assert min(ys) < 360 - radius
        assert max(ys) > 360 + radius
        # And it still covers the window, or the corners would go unpainted.
        assert min(xs) <= 0 and min(ys) <= 0
        assert max(xs) >= 1280 and max(ys) >= 720

    def test_the_ring_winds_against_the_rectangle(self) -> None:
        """Opposite winding is what makes the hole a hole.

        Both loops wound the same way would fill as one solid region with
        a scanline fill, and the circle would simply not appear.
        """
        points = circular_cover_points(640, 360, 200.0, 1280, 720)
        _, rect, ring = self._split(points)

        def signed_area(loop: list[tuple[int, int]]) -> float:
            total = 0.0
            for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1], strict=True):
                total += x0 * y1 - x1 * y0
            return total / 2.0

        assert signed_area(rect) * signed_area(ring) < 0

    def test_the_segment_count_is_honoured(self) -> None:
        few = circular_cover_points(640, 360, 100.0, 1280, 720, segments=8)
        many = circular_cover_points(640, 360, 100.0, 1280, 720, segments=128)
        assert len(many) - len(few) == 120

    def test_fewer_than_three_segments_is_clamped(self) -> None:
        """Two sides is not a polygon; a caller asking for one gets a triangle."""
        assert len(circular_cover_points(640, 360, 100.0, 1280, 720, segments=1)) == (
            len(circular_cover_points(640, 360, 100.0, 1280, 720, segments=3))
        )

    def test_the_full_radius_clears_the_corners_not_just_the_edge_midpoints(
        self,
    ) -> None:
        """Why the maximum is not the half-diagonal.

        An inscribed polygon touches its circle only at the vertices, so a
        64-gon at exactly the half-diagonal falls *inside* the window
        corners and leaves four slivers covered -- 2131 pixels of a
        1280x720 window, at the one moment the effect should be invisible.
        """
        half_diagonal = math.hypot(640, 360)
        assert fully_revealed_radius(1280, 720) > half_diagonal
        # And the excess is exactly the apothem correction.
        assert fully_revealed_radius(1280, 720) == pytest.approx(
            half_diagonal / math.cos(math.pi / DEFAULT_WIPE_SEGMENTS)
        )


class TestTheCircularWipeRevealedRadius:
    """What the effect is doing at a given moment, as one number."""

    def _at(self, progress: float, state: TransitionState | None = None):
        transition = CircularWipeTransition(TransitionConfig(duration=1.0))
        transition.start()
        transition.progress = progress
        if state is not None:
            transition.state = state
        return transition

    def test_it_starts_fully_revealed(self) -> None:
        transition = self._at(0.0)
        assert transition.revealed_radius(1280, 720) == pytest.approx(
            fully_revealed_radius(1280, 720)
        )

    def test_it_is_fully_covered_at_the_midpoint(self) -> None:
        transition = self._at(0.5)
        assert transition.revealed_radius(1280, 720) == pytest.approx(0.0)

    def test_it_is_fully_revealed_again_at_the_end(self) -> None:
        """The second phase reopens over the new scene."""
        transition = self._at(1.0, TransitionState.TRANSITIONING_IN)
        assert transition.revealed_radius(1280, 720) == pytest.approx(
            fully_revealed_radius(1280, 720)
        )

    def test_the_radius_shrinks_monotonically_through_the_first_phase(self) -> None:
        radii = [
            self._at(p).revealed_radius(1280, 720)
            for p in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)
        ]
        assert radii == sorted(radii, reverse=True)


class TestTheCircularWipeActuallyDrawsACircle:
    """Real pixels, because the defect was invisible to everything else.

    The class promised "expands a circle from center" and drew a
    full-screen fade behind a `# TODO: Proper circular mask rendering`. Not
    approximately a fade: its output was **byte-identical** to
    `FadeTransition`'s at the same progress, which is what the first test
    here pins. Nothing covered this class before, which is how a stub
    stayed shipped and exported.
    """

    WIDTH = 320
    HEIGHT = 240
    SCENE = (0, 200, 0)

    def _frame(self, progress, state=None, alpha=255, transition=None, size=None):
        import pygame

        from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer

        pygame.init()
        width, height = size or (self.WIDTH, self.HEIGHT)
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        surface.fill((*self.SCENE, 255))
        if transition is None:
            transition = CircularWipeTransition(
                TransitionConfig(duration=1.0, color=Color(0, 0, 0, alpha))
            )
        transition.start()
        transition.progress = progress
        if state is not None:
            transition.state = state
        transition.render(Mock(), PygameUIRenderer(surface), width, height)
        return surface

    def _revealed(self, surface) -> int:
        return sum(
            1
            for y in range(self.HEIGHT)
            for x in range(self.WIDTH)
            if surface.get_at((x, y))[:3] == self.SCENE
        )

    def test_it_is_not_a_fade(self) -> None:
        """The regression guard. These two used to be the same bytes."""
        import pygame

        circular = self._frame(0.25)
        fade = self._frame(
            0.25, transition=FadeTransition(TransitionConfig(duration=1.0))
        )
        assert pygame.image.tobytes(circular, "RGBA") != pygame.image.tobytes(
            fade, "RGBA"
        )

    def test_mid_transition_shows_a_revealed_region_not_a_uniform_tint(self) -> None:
        surface = self._frame(0.25)
        centre = surface.get_at((self.WIDTH // 2, self.HEIGHT // 2))[:3]
        corner = surface.get_at((1, 1))[:3]
        assert centre == self.SCENE
        assert corner == (0, 0, 0)

    def test_the_revealed_region_is_round(self) -> None:
        """Sampled just inside and just outside the radius, all the way round.

        A square or diamond revealed region would pass the centre/corner
        test above; this is what says it is a circle.
        """
        transition = CircularWipeTransition(TransitionConfig(duration=1.0))
        surface = self._frame(0.25, transition=transition)
        radius = transition.revealed_radius(self.WIDTH, self.HEIGHT)
        cx, cy = self.WIDTH / 2, self.HEIGHT / 2

        for step in range(24):
            angle = 2 * math.pi * step / 24
            dx, dy = math.cos(angle), math.sin(angle)
            inside = (
                int(cx + dx * (radius - 4)),
                int(cy + dy * (radius - 4)),
            )
            outside = (
                int(cx + dx * (radius + 4)),
                int(cy + dy * (radius + 4)),
            )
            if not (0 <= outside[0] < self.WIDTH and 0 <= outside[1] < self.HEIGHT):
                continue
            assert surface.get_at(inside)[:3] == self.SCENE, f"angle {step}"
            assert surface.get_at(outside)[:3] == (0, 0, 0), f"angle {step}"

    def test_the_start_of_the_transition_covers_nothing(self) -> None:
        """The artefact that `fully_revealed_radius` exists to remove.

        With the maximum set to the half-diagonal, the approximating
        polygon's edges fall inside the window corners and four slivers
        stay dark at the one moment the effect should be invisible.
        """
        assert self._revealed(self._frame(0.0)) == self.WIDTH * self.HEIGHT

    def test_the_end_of_the_transition_covers_nothing(self) -> None:
        surface = self._frame(1.0, TransitionState.TRANSITIONING_IN)
        assert self._revealed(surface) == self.WIDTH * self.HEIGHT

    def test_the_midpoint_covers_everything(self) -> None:
        assert self._revealed(self._frame(0.5)) == 0

    def test_the_revealed_area_matches_the_circle(self) -> None:
        """Area, not just a few samples: a wrong radius passes point tests."""
        transition = CircularWipeTransition(TransitionConfig(duration=1.0))
        surface = self._frame(0.25, transition=transition)
        radius = transition.revealed_radius(self.WIDTH, self.HEIGHT)
        assert self._revealed(surface) == pytest.approx(
            math.pi * radius * radius, rel=0.02
        )

    def test_a_translucent_cover_is_blended_exactly_once(self) -> None:
        """The reason the cover is one polygon rather than a fan of quads.

        A fan of 68 quads between the arc and the window edge tiles the
        same region, but `pygame.draw.polygon` fills boundary pixels, so
        adjacent quads blend a translucent cover **twice** along every
        shared edge -- measured as (0, 50, 0) spokes against (0, 100, 0) on
        a 50%-black cover over green. One outline cannot do that, and this
        asserts it: exactly two colours in the frame.
        """
        surface = self._frame(0.25, alpha=128)
        colours = {
            surface.get_at((x, y))[:3]
            for y in range(0, self.HEIGHT, 3)
            for x in range(0, self.WIDTH, 3)
        }
        assert colours == {self.SCENE, (0, 100, 0)}

    @pytest.mark.parametrize("width,height", [(480, 270), (320, 240), (200, 400)])
    @pytest.mark.parametrize("progress", [0.1, 0.2, 0.25, 0.3, 0.4])
    def test_every_pixel_is_on_the_right_side_of_the_circle(
        self, width: int, height: int, progress: float
    ) -> None:
        """The whole frame, both ways, at three aspect ratios.

        **This is the test the earlier ones should have been.** Two real
        defects got past a centre/corner check, a 24-point ring walk, a
        distinct-colour count and an area assertion, and were found by
        rendering the frame and looking at it:

        - The outline's seam ran from the window's left edge to whichever
          ring vertex the construction produced first -- on the *right* of
          the circle -- so it crossed the hole. Its two traversals
          coincide and ought to cancel, but a scanline fill counts a
          vertex lying exactly on a row inconsistently, and the result was
          a dotted line of cover colour across the revealed scene. Invisible
          to a distinct-colour check, because the colour is one already in
          the frame, and about 0.3% of the area, under the area tolerance.
        - The outer loop was the window itself, so once the circle grew
          past the window edges -- which it is, for most of a wipe -- the
          cover stopped being an annulus and the fill left a 42-pixel band
          of cover colour across the top of the revealed scene.

        A pixel inside the polygon's apothem must show the scene and a
        pixel outside the circumradius must not. The 2px margin is for
        integer vertex rounding, which moves the drawn edge by up to half
        a pixel either way.
        """
        transition = CircularWipeTransition(TransitionConfig(duration=1.0))
        surface = self._frame(progress, transition=transition, size=(width, height))
        radius = transition.revealed_radius(width, height)
        apothem = radius * math.cos(math.pi / transition.segments)
        cx, cy = width / 2, height / 2

        covered_inside = 0
        revealed_outside = 0
        for y in range(height):
            for x in range(width):
                distance = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                revealed = surface.get_at((x, y))[:3] == self.SCENE
                if distance < apothem - 2 and not revealed:
                    covered_inside += 1
                elif distance > radius + 2 and revealed:
                    revealed_outside += 1
        assert covered_inside == 0
        assert revealed_outside == 0
