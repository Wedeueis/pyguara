"""Tests for tween system."""

import pytest

from pyguara.animation.easing import EasingType
from pyguara.animation.tween import Tween, TweenState, TweenManager


class TestTweenCreation:
    """Test tween creation and validation."""

    def test_create_scalar_tween(self):
        """Should create tween with scalar values."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)

        assert tween.start_value == 0.0
        assert tween.end_value == 100.0
        assert tween.duration == 1.0
        assert tween.state == TweenState.IDLE

    def test_create_tuple_tween(self):
        """Should create tween with tuple values."""
        tween = Tween(start_value=(0.0, 0.0), end_value=(100.0, 50.0), duration=1.0)

        assert tween.start_value == (0.0, 0.0)
        assert tween.end_value == (100.0, 50.0)

    def test_invalid_duration_raises_error(self):
        """Duration must be positive."""
        with pytest.raises(ValueError, match="Duration must be positive"):
            Tween(start_value=0.0, end_value=100.0, duration=0.0)

        with pytest.raises(ValueError, match="Duration must be positive"):
            Tween(start_value=0.0, end_value=100.0, duration=-1.0)

    def test_mismatched_types_raises_error(self):
        """start_value and end_value must have same type."""
        with pytest.raises(ValueError, match="must both be float or both be tuple"):
            Tween(start_value=0.0, end_value=(100.0, 50.0), duration=1.0)

    def test_mismatched_tuple_length_raises_error(self):
        """Tuple start_value and end_value must have same length."""
        with pytest.raises(ValueError, match="tuples must have same length"):
            Tween(start_value=(0.0, 0.0), end_value=(100.0,), duration=1.0)


class TestTweenLifecycle:
    """Test tween lifecycle methods."""

    def test_start_tween(self):
        """start() should set state to PLAYING."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.start()

        assert tween.state == TweenState.PLAYING
        assert tween.elapsed == 0.0

    def test_pause_tween(self):
        """pause() should set state to PAUSED."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.start()
        tween.pause()

        assert tween.state == TweenState.PAUSED

    def test_resume_tween(self):
        """resume() should restore PLAYING state."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.start()
        tween.pause()
        tween.resume()

        assert tween.state == TweenState.PLAYING

    def test_stop_tween(self):
        """stop() should reset to IDLE."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.start()
        tween.update(0.5)
        tween.stop()

        assert tween.state == TweenState.IDLE
        assert tween.elapsed == 0.0

    def test_cannot_pause_idle_tween(self):
        """pause() should only work on PLAYING tweens."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.pause()

        assert tween.state == TweenState.IDLE

    def test_cannot_resume_playing_tween(self):
        """resume() should only work on PAUSED tweens."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.start()
        tween.resume()

        assert tween.state == TweenState.PLAYING


class TestTweenScalarInterpolation:
    """Test scalar value interpolation."""

    def test_interpolate_scalar_linear(self):
        """Should interpolate scalar with linear easing."""
        tween = Tween(
            start_value=0.0, end_value=100.0, duration=1.0, easing=EasingType.LINEAR
        )
        tween.start()

        tween.update(0.5)
        assert tween.current_value == pytest.approx(50.0)

        tween.update(0.5)
        assert tween.current_value == pytest.approx(100.0)

    def test_interpolate_scalar_ease_in_quad(self):
        """Should interpolate scalar with ease in quad."""
        tween = Tween(
            start_value=0.0,
            end_value=100.0,
            duration=1.0,
            easing=EasingType.EASE_IN_QUAD,
        )
        tween.start()

        tween.update(0.5)
        assert tween.current_value == pytest.approx(25.0)

    def test_initial_value_is_start(self):
        """current_value should start at start_value."""
        tween = Tween(start_value=10.0, end_value=100.0, duration=1.0)

        assert tween.current_value == 10.0


class TestTweenTupleInterpolation:
    """Test tuple value interpolation."""

    def test_interpolate_tuple_linear(self):
        """Should interpolate tuple values."""
        tween = Tween(
            start_value=(0.0, 0.0),
            end_value=(100.0, 50.0),
            duration=1.0,
            easing=EasingType.LINEAR,
        )
        tween.start()

        tween.update(0.5)
        result = tween.current_value
        assert result[0] == pytest.approx(50.0)
        assert result[1] == pytest.approx(25.0)

    def test_interpolate_triple(self):
        """Should interpolate 3-tuples."""
        tween = Tween(
            start_value=(0.0, 0.0, 0.0),
            end_value=(100.0, 50.0, 25.0),
            duration=1.0,
        )
        tween.start()

        tween.update(0.5)
        result = tween.current_value
        assert result[0] == pytest.approx(50.0)
        assert result[1] == pytest.approx(25.0)
        assert result[2] == pytest.approx(12.5)


class TestTweenDelay:
    """Test tween delay functionality."""

    def test_delay_postpones_start(self):
        """Tween should not progress during delay."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0, delay=0.5)
        tween.start()

        tween.update(0.25)
        assert tween.current_value == pytest.approx(0.0)

        tween.update(0.25)  # Delay finished
        assert tween.current_value == pytest.approx(0.0)

        tween.update(0.5)  # Halfway through duration
        assert tween.current_value == pytest.approx(50.0)

    def test_update_returns_true_during_delay(self):
        """update() should return True during delay."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0, delay=0.5)
        tween.start()

        still_playing = tween.update(0.25)
        assert still_playing is True


class TestTweenLooping:
    """Test tween looping functionality."""

    def test_no_loop_completes(self):
        """Tween with loops=0 should complete."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0, loops=0)
        tween.start()

        still_playing = tween.update(1.0)

        assert still_playing is False
        assert tween.is_complete

    def test_finite_loops(self):
        """Tween should loop N times."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0, loops=2)
        tween.start()

        # First completion
        tween.update(1.0)
        assert tween.state == TweenState.PLAYING
        assert tween.current_loop == 1

        # Second completion
        tween.update(1.0)
        assert tween.state == TweenState.PLAYING
        assert tween.current_loop == 2

        # Third completion (should finish)
        still_playing = tween.update(1.0)
        assert still_playing is False
        assert tween.is_complete

    def test_infinite_loop(self):
        """Tween with loops=-1 should loop forever."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0, loops=-1)
        tween.start()

        for _ in range(100):
            still_playing = tween.update(1.0)
            assert still_playing is True
            assert tween.state == TweenState.PLAYING


class TestTweenYoyo:
    """Test yoyo (ping-pong) functionality."""

    def test_yoyo_reverses(self):
        """Yoyo should alternate between forward and reverse."""
        tween = Tween(
            start_value=0.0, end_value=100.0, duration=1.0, loops=2, yoyo=True
        )
        tween.start()

        # First pass: forward (loop 0 -> 1)
        tween.update(1.0)
        assert tween.current_value == pytest.approx(100.0)
        assert tween.is_reverse is True  # Flipped to reverse
        assert tween.state == TweenState.PLAYING
        assert tween.current_loop == 1

        # Second pass: reverse (loop 1 -> 2)
        tween.update(1.0)
        assert tween.current_value == pytest.approx(0.0)
        assert tween.is_reverse is False  # Flipped back to forward
        assert tween.state == TweenState.PLAYING  # Still playing
        assert tween.current_loop == 2

        # Third pass: forward again (loop 2 -> complete)
        tween.update(1.0)
        assert tween.current_value == pytest.approx(100.0)
        assert tween.state == TweenState.COMPLETE  # Now completes

    def test_yoyo_without_loop_no_effect(self):
        """Yoyo without loops should complete normally."""
        tween = Tween(
            start_value=0.0, end_value=100.0, duration=1.0, loops=0, yoyo=True
        )
        tween.start()

        still_playing = tween.update(1.0)
        assert still_playing is False
        assert tween.is_complete


class TestTweenCallbacks:
    """Test tween callback functionality."""

    def test_on_update_callback(self):
        """on_update should be called each frame."""
        updates = []

        def on_update(value):
            updates.append(value)

        tween = Tween(
            start_value=0.0, end_value=100.0, duration=1.0, on_update=on_update
        )
        tween.start()

        tween.update(0.5)
        tween.update(0.5)

        assert len(updates) == 2
        assert updates[0] == pytest.approx(50.0)
        assert updates[1] == pytest.approx(100.0)

    def test_on_complete_callback(self):
        """on_complete should be called when tween finishes."""
        completed = []

        def on_complete():
            completed.append(True)

        tween = Tween(
            start_value=0.0, end_value=100.0, duration=1.0, on_complete=on_complete
        )
        tween.start()

        tween.update(1.0)

        assert len(completed) == 1

    def test_on_complete_not_called_for_loops(self):
        """on_complete should only be called at final completion."""
        completed = []

        def on_complete():
            completed.append(True)

        tween = Tween(
            start_value=0.0,
            end_value=100.0,
            duration=1.0,
            loops=2,
            on_complete=on_complete,
        )
        tween.start()

        tween.update(1.0)  # First loop
        assert len(completed) == 0

        tween.update(1.0)  # Second loop
        assert len(completed) == 0

        tween.update(1.0)  # Complete
        assert len(completed) == 1


class TestTweenProperties:
    """Test tween read-only properties."""

    def test_progress_property(self):
        """progress should return normalized value [0, 1]."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        assert tween.progress == 0.0

        tween.start()
        tween.update(0.5)
        assert tween.progress == pytest.approx(0.5)

        tween.update(0.5)
        assert tween.progress == pytest.approx(1.0)

    def test_progress_with_delay(self):
        """progress should account for delay."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0, delay=0.5)
        tween.start()

        tween.update(0.5)  # Still in delay
        assert tween.progress == 0.0

        tween.update(0.5)  # Halfway through duration
        assert tween.progress == pytest.approx(0.5)

    def test_is_complete_property(self):
        """is_complete should reflect completion state."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        assert tween.is_complete is False

        tween.start()
        assert tween.is_complete is False

        tween.update(1.0)
        assert tween.is_complete is True

    def test_is_playing_property(self):
        """is_playing should reflect playing state."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        assert tween.is_playing is False

        tween.start()
        assert tween.is_playing is True

        tween.pause()
        assert tween.is_playing is False


class TestTweenUpdate:
    """Test tween update return values."""

    def test_update_returns_false_when_complete(self):
        """update() should return False when tween completes."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.start()

        still_playing = tween.update(1.0)
        assert still_playing is False

    def test_update_returns_false_when_paused(self):
        """update() should return True when paused (not complete)."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.start()
        tween.pause()

        still_playing = tween.update(0.5)
        assert still_playing is True  # Still exists, just paused

    def test_update_idle_returns_true(self):
        """update() on IDLE tween should return True (not complete)."""
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)

        still_playing = tween.update(0.5)
        assert still_playing is True  # IDLE != COMPLETE, so returns True


class TestTweenManager:
    """Test TweenManager functionality."""

    def test_manager_creation(self):
        """TweenManager should initialize correctly."""
        manager = TweenManager()

        assert manager.tween_count == 0

    def test_add_tween(self):
        """Should add tweens to manager."""
        manager = TweenManager()
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)

        result = manager.add(tween)

        assert result is tween
        assert manager.tween_count == 1

    def test_add_multiple_tweens(self):
        """Should manage multiple tweens."""
        manager = TweenManager()
        tween1 = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween2 = Tween(start_value=0.0, end_value=50.0, duration=2.0)

        manager.add(tween1)
        manager.add(tween2)

        assert manager.tween_count == 2

    def test_remove_tween(self):
        """Should remove tweens."""
        manager = TweenManager()
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        manager.add(tween)

        removed = manager.remove(tween)

        assert removed is True
        assert manager.tween_count == 0

    def test_remove_nonexistent_tween(self):
        """Removing nonexistent tween should return False."""
        manager = TweenManager()
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)

        removed = manager.remove(tween)

        assert removed is False

    def test_update_all_tweens(self):
        """Should update all tweens."""
        manager = TweenManager()

        tween1 = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween2 = Tween(start_value=0.0, end_value=50.0, duration=1.0)
        tween1.start()
        tween2.start()

        manager.add(tween1)
        manager.add(tween2)

        manager.update(0.5)

        assert tween1.current_value == pytest.approx(50.0)
        assert tween2.current_value == pytest.approx(25.0)

    def test_auto_remove_completed(self):
        """Should automatically remove completed tweens."""
        manager = TweenManager()

        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween.start()
        manager.add(tween)

        manager.update(1.0)

        assert manager.tween_count == 0

    def test_clear_all_tweens(self):
        """Should clear all tweens."""
        manager = TweenManager()

        tween1 = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween2 = Tween(start_value=0.0, end_value=50.0, duration=1.0)
        manager.add(tween1)
        manager.add(tween2)

        manager.clear()

        assert manager.tween_count == 0

    def test_pause_all_tweens(self):
        """Should pause all playing tweens."""
        manager = TweenManager()

        tween1 = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween2 = Tween(start_value=0.0, end_value=50.0, duration=1.0)
        tween1.start()
        tween2.start()
        manager.add(tween1)
        manager.add(tween2)

        manager.pause_all()

        assert tween1.state == TweenState.PAUSED
        assert tween2.state == TweenState.PAUSED

    def test_resume_all_tweens(self):
        """Should resume all paused tweens."""
        manager = TweenManager()

        tween1 = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween2 = Tween(start_value=0.0, end_value=50.0, duration=1.0)
        tween1.start()
        tween2.start()
        manager.add(tween1)
        manager.add(tween2)

        manager.pause_all()
        manager.resume_all()

        assert tween1.state == TweenState.PLAYING
        assert tween2.state == TweenState.PLAYING

    def test_stop_all_tweens(self):
        """Should stop all tweens and clear."""
        manager = TweenManager()

        tween1 = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween2 = Tween(start_value=0.0, end_value=50.0, duration=1.0)
        tween1.start()
        tween2.start()
        manager.add(tween1)
        manager.add(tween2)

        manager.stop_all()

        assert tween1.state == TweenState.IDLE
        assert tween2.state == TweenState.IDLE
        assert manager.tween_count == 0

    def test_active_tweens_property(self):
        """Should return copy of active tweens list."""
        manager = TweenManager()

        tween1 = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        tween2 = Tween(start_value=0.0, end_value=50.0, duration=1.0)
        manager.add(tween1)
        manager.add(tween2)

        active = manager.active_tweens

        assert len(active) == 2
        assert tween1 in active
        assert tween2 in active

    def test_active_tweens_is_copy(self):
        """active_tweens should return a copy."""
        manager = TweenManager()
        tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        manager.add(tween)

        active = manager.active_tweens
        active.clear()

        assert manager.tween_count == 1


class TestTweenIntegration:
    """Test tween integration scenarios."""

    def test_chained_callbacks(self):
        """Test chaining tweens via callbacks."""
        sequence = []

        def on_first_complete():
            sequence.append("first_complete")

        def on_second_complete():
            sequence.append("second_complete")

        manager = TweenManager()

        tween1 = Tween(
            start_value=0.0,
            end_value=100.0,
            duration=1.0,
            on_complete=on_first_complete,
        )
        tween2 = Tween(
            start_value=100.0,
            end_value=0.0,
            duration=1.0,
            on_complete=on_second_complete,
        )

        tween1.start()
        manager.add(tween1)

        manager.update(1.0)
        assert sequence == ["first_complete"]

        tween2.start()
        manager.add(tween2)

        manager.update(1.0)
        assert sequence == ["first_complete", "second_complete"]

    def test_position_animation(self):
        """Test animating a position vector."""
        tween = Tween(
            start_value=(0.0, 0.0),
            end_value=(100.0, 50.0),
            duration=1.0,
            easing=EasingType.EASE_OUT_QUAD,
        )
        tween.start()

        tween.update(0.5)
        x, y = tween.current_value
        assert x > 50.0  # Should be past halfway due to ease out
        assert y > 25.0
