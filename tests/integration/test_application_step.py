"""`Application.begin()` / `step()`: driving frames without `run()`.

Before these existed, every caller that needed a bounded number of frames
monkeypatched `_render` and flipped `_is_running` from inside it --
`tools/agent_view.py`, `test_time_scale.py`, `test_bootstrap_smoke.py` all
do it, each slightly differently. `step()` is that seam made public, and
it is what PyGuara Studio's play-in-editor and headless agent harness
drive.
"""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

from games.boot_process.scenes import BootScene
from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


@pytest.fixture
def app() -> Application:
    return create_headless_application()


def _scene(app: Application) -> BootScene:
    return BootScene(app._event_dispatcher)


@pytest.mark.integration
class TestStep:
    """One call, one frame."""

    def test_step_before_begin_is_a_no_op(self, app: Application) -> None:
        """No scene, no armed timestep -- so it must not loop forever.

        `_fixed_dt` is 0.0 until `begin()`, and the accumulator loop would
        never terminate against it.
        """
        assert app.step() is False

    def test_begin_then_step_advances_exactly_one_frame(self, app: Application) -> None:
        renders = []
        real_render = app._render

        def counting_render() -> None:
            real_render()
            renders.append(1)

        app._render = counting_render  # type: ignore[method-assign]

        app.begin(_scene(app))
        app.step()
        assert len(renders) == 1
        app.step()
        assert len(renders) == 2

        app.shutdown()

    def test_begin_activates_the_scene(self, app: Application) -> None:
        scene = _scene(app)
        app.begin(scene)
        assert app._scene_manager.current_scene is scene
        app.shutdown()

    def test_begin_arms_the_fixed_timestep(self, app: Application) -> None:
        """`_fixed_dt` is what `_render()` divides by for its alpha."""
        assert app._fixed_dt == 0.0
        app.begin(_scene(app))
        assert app._fixed_dt > 0.0
        app.shutdown()

    def test_begin_dispatches_application_start(self, app: Application) -> None:
        from pyguara.events.lifecycle import ApplicationStartEvent

        seen = []
        app._event_dispatcher.subscribe(ApplicationStartEvent, seen.append)
        app.begin(_scene(app))
        assert len(seen) == 1
        app.shutdown()

    def test_step_reports_false_once_stopped(self, app: Application) -> None:
        """So `while app.step(): pass` terminates where `run()` does."""
        app.begin(_scene(app))
        assert app.step() is True
        app._is_running = False
        assert app.step() is False
        app.shutdown()

    def test_a_bounded_run_needs_no_monkeypatching(self, app: Application) -> None:
        """The whole point: N frames, driven from outside, no patching."""
        app.begin(_scene(app))
        frames = 0
        while frames < 5 and app.step():
            frames += 1
        assert frames == 5
        app.shutdown()

    def test_step_does_not_shut_down_on_its_own(self, app: Application) -> None:
        """`run()` owns `shutdown()`; a hand-driven loop decides for itself."""
        app.begin(_scene(app))
        app._is_running = False
        app.step()
        assert app._has_shut_down is False
        app.shutdown()


@pytest.mark.integration
class TestRunStillWorks:
    """`run()` is now a loop over `step()`, and must behave identically."""

    def test_run_renders_until_stopped(self, app: Application) -> None:
        renders = []
        real_render = app._render

        def stop_after_three() -> None:
            real_render()
            renders.append(1)
            if len(renders) >= 3:
                app._is_running = False

        app._render = stop_after_three  # type: ignore[method-assign]
        app.run(_scene(app))

        assert len(renders) == 3

    def test_run_shuts_down_on_the_way_out(self, app: Application) -> None:
        app._render = lambda: setattr(app, "_is_running", False)  # type: ignore[method-assign]
        app.run(_scene(app))
        assert app._has_shut_down is True

    def test_run_reraises_and_still_shuts_down(self, app: Application) -> None:
        """A crash in a frame must not skip cleanup."""

        def boom(dt: float) -> None:
            raise RuntimeError("frame exploded")

        app._update = boom  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="frame exploded"):
            app.run(_scene(app))
        assert app._has_shut_down is True

    def test_step_lets_the_exception_through_untouched(self, app: Application) -> None:
        """Unlike `run()`, `step()` neither logs nor shuts down."""

        def boom(dt: float) -> None:
            raise RuntimeError("frame exploded")

        app.begin(_scene(app))
        app._update = boom  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="frame exploded"):
            app.step()
        assert app._has_shut_down is False
        app.shutdown()
