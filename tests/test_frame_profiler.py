"""The frame profiler: what it records, what it shows, and where it draws."""

from __future__ import annotations

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from typing import Any

import pytest

from pyguara.application import frame_profile
from pyguara.application.application import Application
from pyguara.application.bootstrap import (
    create_headless_application,
    create_headless_sandbox_application,
)
from pyguara.application.frame_profile import (
    PHASES,
    FrameProfiler,
    draw_frame_profile,
    profile_rows,
)
from pyguara.config.manager import ConfigManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.scene.base import Scene


class _Clock:
    """A `perf_counter` the test moves by hand, in milliseconds."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, milliseconds: float) -> None:
        self.now += milliseconds / 1000.0


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(frame_profile.time, "perf_counter", fake)
    return fake


def _frame(profiler: FrameProfiler, clock: _Clock, costs: dict[str, float]) -> None:
    profiler.begin_frame()
    for phase in PHASES:
        clock.advance(costs.get(phase, 0.0))
        profiler.mark(phase)
    profiler.end_frame(fixed_steps=1)


class _Recorder:
    """A `UIRenderer` that keeps what it was asked to draw."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.colours: dict[str, Any] = {}
        self.rects = 0

    def draw_rect(self, *args: Any, **kwargs: Any) -> None:
        self.rects += 1

    def draw_text(self, text: str, position: Any, color: Any, **kwargs: Any) -> None:
        self.texts.append(text)
        self.colours[text] = color


class TestRecording:
    def test_there_is_nothing_to_report_before_a_frame_ends(self) -> None:
        assert FrameProfiler().stats() is None

    def test_each_phase_is_charged_the_time_up_to_its_mark(self, clock: _Clock) -> None:
        profiler = FrameProfiler()
        _frame(profiler, clock, {"wait": 6, "fixed": 3, "update": 1, "render": 4})
        _frame(profiler, clock, {"wait": 2, "fixed": 5, "update": 1, "render": 8})

        stats = profiler.stats()

        assert stats is not None
        by_name = {phase.name: phase for phase in stats.phases}
        assert [phase.name for phase in stats.phases] == list(PHASES)
        assert by_name["fixed"].mean_ms == pytest.approx(4.0)
        assert by_name["fixed"].max_ms == pytest.approx(5.0)
        assert by_name["render"].max_ms == pytest.approx(8.0)
        assert by_name["input"].mean_ms == pytest.approx(0.0)

    def test_wait_counts_towards_the_frame_and_not_towards_the_work(
        self, clock: _Clock
    ) -> None:
        profiler = FrameProfiler()
        _frame(profiler, clock, {"wait": 6, "fixed": 3, "render": 1})

        stats = profiler.stats()

        assert stats is not None
        assert stats.frame_mean_ms == pytest.approx(10.0)
        assert stats.work_mean_ms == pytest.approx(4.0)
        assert stats.fps == pytest.approx(100.0)

    def test_a_phase_marked_twice_in_a_frame_adds_up(self, clock: _Clock) -> None:
        profiler = FrameProfiler()
        profiler.begin_frame()
        clock.advance(2)
        profiler.mark("fixed")
        clock.advance(3)
        profiler.mark("fixed")
        profiler.end_frame(fixed_steps=2)

        stats = profiler.stats()

        assert stats is not None
        assert stats.phases[PHASES.index("fixed")].mean_ms == pytest.approx(5.0)
        assert stats.fixed_steps_mean == 2

    def test_only_the_recent_frames_are_kept(self, clock: _Clock) -> None:
        profiler = FrameProfiler()
        _frame(profiler, clock, {"render": 500})
        for _ in range(frame_profile.HISTORY_FRAMES):
            _frame(profiler, clock, {"render": 1})

        stats = profiler.stats()

        assert stats is not None
        assert stats.frames == frame_profile.HISTORY_FRAMES
        assert stats.frame_max_ms == pytest.approx(1.0)

    def test_a_phase_that_does_not_exist_is_refused(self) -> None:
        profiler = FrameProfiler()
        profiler.begin_frame()

        with pytest.raises(KeyError, match="physics"):
            profiler.mark("physics")


class TestOverlay:
    def test_it_lists_the_frame_the_work_and_every_phase(self, clock: _Clock) -> None:
        profiler = FrameProfiler()
        _frame(profiler, clock, {"wait": 6, "fixed": 3, "render": 1})
        stats = profiler.stats()
        assert stats is not None

        rows = profile_rows(stats)

        assert rows[0] == ("100 fps", "10.00 ms", "max 10.00")
        assert rows[1] == ("work", "4.00 ms", "")
        assert [row[0] for row in rows[2:8]] == list(PHASES)
        assert rows[4 + 1] == ("fixed", "3.00 ms", "max 3.00")
        assert rows[-1] == ("fixed steps", "1.00", "per frame")

    def test_the_work_row_is_highlighted_only_over_budget(self, clock: _Clock) -> None:
        profiler = FrameProfiler()
        _frame(profiler, clock, {"wait": 6, "fixed": 3, "render": 1})

        def work_colour(budget_ms: float) -> Any:
            recorder = _Recorder()
            draw_frame_profile(profiler, recorder, budget_ms)  # type: ignore[arg-type]
            return recorder.colours["work"]

        assert work_colour(3.0) != work_colour(5.0)

    def test_a_hidden_profiler_draws_nothing(self, clock: _Clock) -> None:
        profiler = FrameProfiler(visible=False)
        _frame(profiler, clock, {"render": 1})
        recorder = _Recorder()

        draw_frame_profile(profiler, recorder)  # type: ignore[arg-type]

        assert recorder.texts == [] and recorder.rects == 0

    def test_a_profiler_with_no_frame_draws_nothing(self) -> None:
        recorder = _Recorder()

        draw_frame_profile(FrameProfiler(), recorder)  # type: ignore[arg-type]

        assert recorder.texts == [] and recorder.rects == 0


class _Idle(Scene):
    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass


def _run(app: Application, frames: int, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Step `app` and return the text its UI renderer was asked to draw."""
    drawn: list[str] = []
    renderer = app.container.get(UIRenderer)  # type: ignore[type-abstract]
    original = renderer.draw_text

    def recording(text: str, *args: Any, **kwargs: Any) -> None:
        drawn.append(text)
        original(text, *args, **kwargs)

    monkeypatch.setattr(renderer, "draw_text", recording)
    app.begin(_Idle())
    try:
        for _ in range(frames):
            app.step()
    finally:
        app.shutdown()
    return drawn


class TestInTheApplication:
    def test_it_is_off_unless_asked_for(self, monkeypatch: pytest.MonkeyPatch) -> None:
        app = create_headless_application()

        drawn = _run(app, 3, monkeypatch)

        assert app.frame_profiler is None
        assert not any("fps" in text for text in drawn)

    def test_the_config_flag_turns_it_on_and_it_records_every_frame(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = create_headless_application()
        app.container.get(ConfigManager).config.debug.enable_profiler = True

        drawn = _run(app, 5, monkeypatch)

        profiler = app.frame_profiler
        assert profiler is not None
        stats = profiler.stats()
        assert stats is not None and stats.frames == 5
        assert stats.frame_mean_ms > 0
        assert any("fps" in text for text in drawn)

    def test_hiding_it_keeps_recording(self, monkeypatch: pytest.MonkeyPatch) -> None:
        app = create_headless_application()
        profiler = app.enable_frame_profiler(visible=False)

        drawn = _run(app, 4, monkeypatch)

        stats = profiler.stats()
        assert stats is not None and stats.frames == 4
        assert not any("fps" in text for text in drawn)

    def test_enabling_twice_keeps_the_same_profiler(self) -> None:
        app = create_headless_application()
        try:
            first = app.enable_frame_profiler(visible=False)
            second = app.enable_frame_profiler(visible=True)

            assert second is first and first.visible
            app.disable_frame_profiler()
            assert app.frame_profiler is None
        finally:
            app.shutdown()

    def test_the_sandbox_draws_it_beside_its_own_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = create_headless_sandbox_application()
        app.enable_frame_profiler()

        drawn = _run(app, 3, monkeypatch)

        assert any("fps" in text for text in drawn)


def test_the_overlay_holds_its_numbers_between_refreshes(clock: _Clock) -> None:
    profiler = FrameProfiler()
    _frame(profiler, clock, {"render": 1})
    first = profiler.shown_stats()

    for _ in range(frame_profile.REFRESH_FRAMES - 2):
        _frame(profiler, clock, {"render": 9})
    assert profiler.shown_stats() is first

    _frame(profiler, clock, {"render": 9})
    refreshed = profiler.shown_stats()

    assert refreshed is not first
    assert refreshed is not None and refreshed.frame_max_ms == pytest.approx(9.0)
