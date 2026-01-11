"""Tests for scene transition system."""

from unittest.mock import Mock

from pyguara.common.types import Color
from pyguara.scene.transitions import (
    TransitionConfig,
    TransitionState,
    EasingFunction,
    FadeTransition,
    SlideTransition,
    WipeTransition,
    TransitionManager,
    apply_easing,
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
        """Manager should handle two-phase transitions."""
        manager = TransitionManager()
        config = TransitionConfig(duration=1.0, two_phase=True)
        transition = FadeTransition(config)
        from_scene = Mock()
        to_scene = Mock()

        manager.start_transition(transition, from_scene, to_scene)

        # First phase: old scene exits
        assert from_scene.on_exit.called

        # Midpoint: new scene enters
        manager.update(0.5)
        assert to_scene.on_enter.called
        assert to_scene.update.called

        # Complete
        manager.update(0.5)
        assert not manager.is_transitioning()

    def test_manager_single_phase_transition(self):
        """Manager should handle single-phase transitions."""
        manager = TransitionManager()
        config = TransitionConfig(duration=0.5, two_phase=False)
        transition = FadeTransition(config)
        from_scene = Mock()
        to_scene = Mock()

        manager.start_transition(transition, from_scene, to_scene)

        # Should not exit old scene yet
        assert not from_scene.on_exit.called

        # Complete
        manager.update(0.5)

        # Now should switch
        assert from_scene.on_exit.called
        assert to_scene.on_enter.called


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
