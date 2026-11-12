"""Tests for the `Clock` frame-pacing seam (issue #9).

`Application` used `pygame.time.Clock` directly; the loop now takes a `Clock`
from the DI container. These pin the contract and the wiring.
"""

from __future__ import annotations

import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.application.clock import Clock, FixedClock, WallClock


class TestFixedClock:
    def test_tick_returns_the_configured_frame_time(self) -> None:
        clock = FixedClock(frame_time_ms=20.0)
        assert clock.tick() == 20.0

    def test_default_frame_time_is_one_sixtieth_of_a_second(self) -> None:
        assert FixedClock().tick() == pytest.approx(1000.0 / 60.0)

    def test_target_fps_argument_is_ignored(self) -> None:
        clock = FixedClock(frame_time_ms=7.0)
        assert clock.tick(240) == 7.0
        assert clock.tick(0) == 7.0

    def test_it_never_blocks(self) -> None:
        """A deterministic clock must not sleep, however low the target rate."""
        import time

        clock = FixedClock()
        start = time.perf_counter()
        for _ in range(1000):
            clock.tick(1)  # 1 FPS would be a 1s sleep on a real clock
        assert time.perf_counter() - start < 0.5


class TestClockProtocol:
    def test_fixed_clock_satisfies_the_protocol(self) -> None:
        assert isinstance(FixedClock(), Clock)

    def test_pygame_clock_satisfies_the_protocol(self) -> None:
        pygame = pytest.importorskip("pygame")
        pygame.init()
        try:
            from pyguara.graphics.backends.pygame.clock import PygameClock

            assert isinstance(PygameClock(), Clock)
        finally:
            pygame.quit()


class TestBootstrapWiring:
    def test_headless_application_is_driven_by_a_fixed_clock(self) -> None:
        """No pygame clock, no wall-clock sleep in a headless run."""
        app = create_headless_application()
        try:
            resolved = app._container.get(Clock)  # type: ignore[type-abstract]
            assert isinstance(resolved, FixedClock)
            assert app._clock is resolved
        finally:
            app.shutdown()


class _FakeTime:
    """A monotonic timer that only moves when told, or when slept on."""

    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class TestWallClock:
    def test_an_uncapped_tick_reports_the_frame_and_never_sleeps(self) -> None:
        fake = _FakeTime()
        clock = WallClock(now=fake, sleep=fake.sleep)
        fake.now += 0.004

        assert clock.tick() == pytest.approx(4.0)
        assert fake.slept == []

    def test_a_capped_tick_sleeps_out_the_rest_and_reports_all_of_it(self) -> None:
        fake = _FakeTime()
        clock = WallClock(now=fake, sleep=fake.sleep)
        fake.now += 0.010

        assert clock.tick(50) == pytest.approx(20.0)
        assert fake.slept == [pytest.approx(0.010)]

    def test_a_frame_over_budget_does_not_sleep(self) -> None:
        fake = _FakeTime()
        clock = WallClock(now=fake, sleep=fake.sleep)
        fake.now += 0.030

        assert clock.tick(60) == pytest.approx(30.0)
        assert fake.slept == []

    def test_time_is_not_rounded_to_whole_milliseconds(self) -> None:
        fake = _FakeTime()
        clock = WallClock(now=fake, sleep=fake.sleep)
        fake.now += 1 / 60

        assert clock.tick() == pytest.approx(16.6667, abs=1e-3)

    def test_it_is_a_clock(self) -> None:
        assert isinstance(WallClock(), Clock)

    def test_the_real_timer_paces_roughly(self) -> None:
        clock = WallClock()
        clock.tick()
        elapsed = clock.tick(100)
        # Asleep for about 10 ms; generous on a loaded machine.
        assert 9.0 <= elapsed < 60.0
