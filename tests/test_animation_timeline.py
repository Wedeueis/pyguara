"""Timelines: sequential and parallel composition, waits and callbacks."""

import pytest

from pyguara.animation.easing import EasingType
from pyguara.animation.timeline import Animatable, Timeline
from pyguara.animation.tween import Tween, TweenManager


def _tween(duration: float = 1.0) -> Tween:
    return Tween(start_value=0.0, end_value=100.0, duration=duration)


# -- Sequential --


def test_steps_run_in_order_one_after_another():
    first, second = _tween(1.0), _tween(1.0)
    timeline = Timeline().then(first).then(second).start()

    timeline.update(0.5)
    assert first.is_playing
    assert second.state.name == "IDLE"

    timeline.update(0.6)
    assert first.is_complete
    assert second.is_playing


def test_a_timeline_reports_running_until_its_last_step_finishes():
    timeline = Timeline().then(_tween(1.0)).then(_tween(1.0)).start()

    assert timeline.update(1.0) is True
    assert timeline.update(1.0) is False
    assert timeline.is_complete


def test_a_wait_delays_the_next_step():
    tween = _tween(1.0)
    timeline = Timeline().wait(0.5).then(tween).start()

    timeline.update(0.2)
    assert tween.state.name == "IDLE"

    timeline.update(0.4)
    assert tween.is_playing


def test_a_callback_runs_in_order_with_the_steps_around_it():
    calls: list[str] = []
    first = Tween(
        start_value=0.0,
        end_value=1.0,
        duration=0.1,
        on_complete=lambda: calls.append("tween"),
    )
    timeline = Timeline().then(first).call(lambda: calls.append("call")).start()

    timeline.update(0.2)

    assert calls == ["tween", "call"]


def test_leftover_time_carries_into_the_next_step():
    """Five 1 ms steps would otherwise take one frame each -- 83 ms at 60 Hz
    for 5 ms of animation."""
    calls: list[int] = []
    timeline = Timeline()
    for index in range(5):
        timeline.wait(0.001).call(lambda i=index: calls.append(i))
    timeline.start()

    timeline.update(1 / 60)

    assert calls == [0, 1, 2, 3, 4]
    assert timeline.is_complete


def test_a_timeline_of_only_callbacks_completes_in_one_tick():
    calls: list[int] = []
    timeline = Timeline()
    for index in range(3):
        timeline.call(lambda i=index: calls.append(i))
    timeline.start()

    assert timeline.update(0.016) is False
    assert calls == [0, 1, 2]


def test_a_negative_wait_is_refused():
    """It would finish before it began and swallow the step after it in the
    same frame."""
    with pytest.raises(ValueError, match="non-negative"):
        Timeline().wait(-1.0)


# -- Parallel --


def test_a_parallel_group_runs_its_members_together():
    left, right = _tween(1.0), _tween(1.0)
    Timeline().parallel(left, right).start().update(0.5)

    assert left.progress == pytest.approx(0.5)
    assert right.progress == pytest.approx(0.5)


def test_a_parallel_group_finishes_with_its_slowest_member():
    """ "And then" after a parallel step means after all of it -- the only
    reading that makes `parallel(a, b)` composable with `then(c)`."""
    quick, slow = _tween(0.2), _tween(1.0)
    after = _tween(1.0)
    timeline = Timeline().parallel(quick, slow).then(after).start()

    timeline.update(0.3)
    assert quick.is_complete
    assert after.state.name == "IDLE"

    timeline.update(0.8)
    assert slow.is_complete
    assert after.is_playing


def test_an_empty_parallel_group_is_a_no_op_step():
    tween = _tween(1.0)
    timeline = Timeline().parallel().then(tween).start()

    timeline.update(0.1)

    assert tween.is_playing


# -- Nesting --


def test_a_timeline_can_be_a_step_inside_another():
    inner_tween = _tween(0.5)
    inner = Timeline().then(inner_tween)
    after = _tween(1.0)
    outer = Timeline().then(inner).then(after).start()

    outer.update(0.6)

    assert inner.is_complete
    assert after.is_playing


def test_a_timeline_satisfies_the_animatable_protocol():
    assert isinstance(Timeline(), Animatable)
    assert isinstance(_tween(), Animatable)


def test_a_tween_manager_ticks_a_timeline_like_a_tween():
    """Which is the point of the shared contract: the manager holds either
    without knowing which."""
    manager = TweenManager()
    timeline = Timeline().then(_tween(0.5)).start()
    manager.add(timeline)  # type: ignore[arg-type]

    manager.update(0.6)

    assert timeline.is_complete
    assert manager.tween_count == 0


# -- Looping and lifecycle --


def test_loops_repeat_the_whole_timeline():
    calls: list[int] = []
    timeline = Timeline(loops=2)
    timeline.call(lambda: calls.append(1)).wait(0.1)
    timeline.start()

    for _ in range(10):
        timeline.update(0.05)

    assert len(calls) == 3  # once, plus two extra loops


def test_an_infinite_timeline_never_completes():
    timeline = Timeline(loops=-1).wait(0.1).start()

    for _ in range(50):
        assert timeline.update(0.05) is True

    assert not timeline.is_complete


def test_on_complete_fires_once_after_the_last_loop():
    calls: list[int] = []
    timeline = Timeline(loops=1, on_complete=lambda: calls.append(1))
    timeline.wait(0.1).start()

    for _ in range(10):
        timeline.update(0.05)

    assert calls == [1]


def test_an_empty_timeline_is_complete_rather_than_stuck():
    """A game building one from a filtered list of effects should not hang
    when the filter matches nothing."""
    timeline = Timeline().start()

    assert timeline.is_complete
    assert timeline.update(1.0) is False


def test_stopping_halts_every_member_of_a_parallel_group():
    """Not only the current step: an interrupted group must not leave its
    members running."""
    left, right = _tween(1.0), _tween(1.0)
    timeline = Timeline().parallel(left, right).start()
    timeline.update(0.1)

    timeline.stop()

    assert not left.is_playing
    assert not right.is_playing
    assert not timeline.is_playing
    assert not timeline.is_complete


def test_stopping_does_not_fire_on_complete():
    calls: list[int] = []
    timeline = Timeline(on_complete=lambda: calls.append(1))
    timeline.then(_tween(1.0)).start()
    timeline.update(0.1)

    timeline.stop()

    assert calls == []


def test_restarting_goes_back_to_the_first_step():
    calls: list[int] = []
    timeline = Timeline().call(lambda: calls.append(1)).wait(1.0)
    timeline.start()
    timeline.update(0.1)

    timeline.start()
    timeline.update(0.1)

    assert calls == [1, 1]
    assert timeline.current_step == 1


def test_step_count_reports_what_was_appended():
    timeline = Timeline().then(_tween()).wait(0.1).call(lambda: None).parallel()

    assert timeline.step_count == 4


def test_a_tween_inside_a_timeline_keeps_its_own_easing():
    tween = Tween(
        start_value=0.0,
        end_value=100.0,
        duration=1.0,
        easing=EasingType.EASE_IN_QUAD,
    )
    Timeline().then(tween).start().update(0.5)

    assert tween.current_value == pytest.approx(25.0)


def test_an_instant_step_after_a_tween_runs_in_the_same_tick():
    """`then(tween).call(spawn_hitbox)` firing a frame late is exactly the
    off-by-one that makes a combat timeline feel loose."""
    calls: list[str] = []
    timeline = Timeline().then(_tween(0.1)).call(lambda: calls.append("hitbox"))
    timeline.start()

    timeline.update(0.2)

    assert calls == ["hitbox"]


def test_a_looping_timeline_of_instant_steps_does_not_spin_forever():
    """One full pass per call, or an all-instant infinite timeline hangs
    the frame instead of merely misbehaving."""
    calls: list[int] = []
    timeline = Timeline(loops=-1)
    for _ in range(3):
        timeline.call(lambda: calls.append(1))
    timeline.start()

    assert timeline.update(0.016) is True
    assert len(calls) <= 4
