"""The two hooks in `Application.step`, and the tick counter beside them."""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.application.clock import FixedClock
from pyguara.events.dispatcher import EventDispatcher
from pyguara.scene.base import Scene


class Recording:
    def __init__(self, log: list[str], name: str = "hook") -> None:
        self.log = log
        self.name = name

    def before_fixed_updates(self, frame_time: float) -> None:
        self.log.append(f"{self.name}:before")

    def after_fixed_updates(self, frame_time: float) -> None:
        self.log.append(f"{self.name}:after")


class RecordingScene(Scene):
    def __init__(self, dispatcher: Any, log: list[str]) -> None:
        super().__init__("recording", dispatcher)
        self.log = log

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def fixed_update(self, fixed_dt: float) -> None:
        self.log.append("fixed")

    def update(self, dt: float) -> None:
        self.log.append("update")

    def render(self, world_renderer: Any, ui_renderer: Any) -> None:
        self.log.append("render")


@pytest.fixture
def app() -> Any:
    application = create_headless_application()
    yield application
    application.shutdown()


def begin(app: Any, log: list[str]) -> None:
    dispatcher = app._container.get(EventDispatcher)
    app._clock = FixedClock(1000.0 / 60.0)
    app.begin(RecordingScene(dispatcher, log))
    log.clear()


def test_hooks_run_around_the_fixed_updates(app: Any) -> None:
    log: list[str] = []
    begin(app, log)
    app.add_step_hook(Recording(log))
    app._accumulator = app._fixed_dt

    app.step()

    assert log.index("hook:before") < log.index("fixed")
    assert log.index("fixed") < log.index("hook:after")
    assert log.index("hook:after") < log.index("update")
    assert log.index("update") < log.index("render")


def test_hooks_run_on_a_frame_with_no_fixed_update(app: Any) -> None:
    log: list[str] = []
    begin(app, log)
    app._clock = FixedClock(1.0)
    app.add_step_hook(Recording(log))
    app._accumulator = 0.0

    app.step()

    assert "fixed" not in log
    assert log.count("hook:before") == 1
    assert log.count("hook:after") == 1


def test_hooks_run_in_the_order_they_were_added(app: Any) -> None:
    log: list[str] = []
    begin(app, log)
    app.add_step_hook(Recording(log, "a"))
    app.add_step_hook(Recording(log, "b"))

    app.step()

    assert log.index("a:before") < log.index("b:before")
    assert log.index("a:after") < log.index("b:after")


def test_adding_twice_runs_once_and_removing_stops_it(app: Any) -> None:
    log: list[str] = []
    begin(app, log)
    hook = Recording(log)
    app.add_step_hook(hook)
    app.add_step_hook(hook)

    app.step()
    assert log.count("hook:before") == 1

    log.clear()
    app.remove_step_hook(hook)
    app.remove_step_hook(hook)
    app.step()
    assert "hook:before" not in log


def test_the_tick_counts_fixed_updates_including_several_in_one_frame(app: Any) -> None:
    log: list[str] = []
    begin(app, log)
    before = app.fixed_tick
    fixed_before = log.count("fixed")
    app._clock = FixedClock(1000.0 * 3.5 * app._fixed_dt)

    app.step()

    assert app.fixed_tick - before == log.count("fixed") - fixed_before
    assert app.fixed_tick - before == 3


def test_a_hook_sees_the_tick_the_simulation_reached(app: Any) -> None:
    log: list[str] = []
    begin(app, log)
    seen: list[tuple[int, str]] = []

    class Watching:
        def before_fixed_updates(self, frame_time: float) -> None:
            seen.append((app.fixed_tick, "before"))

        def after_fixed_updates(self, frame_time: float) -> None:
            seen.append((app.fixed_tick, "after"))

    app.add_step_hook(Watching())
    app._accumulator = app._fixed_dt

    app.step()

    assert seen[1][0] > seen[0][0]


def test_frame_time_given_to_a_hook_is_scaled_like_the_simulation(app: Any) -> None:
    log: list[str] = []
    begin(app, log)
    times: list[float] = []

    class Watching:
        def before_fixed_updates(self, frame_time: float) -> None:
            times.append(frame_time)

        def after_fixed_updates(self, frame_time: float) -> None:
            times.append(frame_time)

    app.add_step_hook(Watching())
    app.time_scale = 0.5

    app.step()

    assert times[0] == times[1]
    assert times[0] == pytest.approx(1 / 60 * 0.5)


def test_an_exception_in_a_hook_propagates(app: Any) -> None:
    log: list[str] = []
    begin(app, log)

    class Broken:
        def before_fixed_updates(self, frame_time: float) -> None:
            raise RuntimeError("hook failed")

        def after_fixed_updates(self, frame_time: float) -> None:
            pass

    app.add_step_hook(Broken())

    with pytest.raises(RuntimeError, match="hook failed"):
        app.step()
