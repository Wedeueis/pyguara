"""Settling memory: one full collection, then a freeze, when the scenes change.

See `pyguara.application.memory` for why: a full collection walks everything a
game loaded, and freezing that once it's loaded keeps the walk out of the frame.
"""

from __future__ import annotations

import gc
import weakref
from collections.abc import Iterator
from typing import Any

import pytest

import pyguara.application.application as application_module
from pyguara.application.bootstrap import create_headless_application
from pyguara.application.clock import FixedClock
from pyguara.application.memory import settle_memory
from pyguara.events.dispatcher import EventDispatcher
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.scene.transitions import FadeTransition, TransitionConfig


class Quiet(Scene):
    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def render(self, world_renderer: Any, ui_renderer: Any) -> None:
        pass


class Cycle:
    """Something only the cycle collector can free: it refers to itself."""

    def __init__(self) -> None:
        self.me = self


@pytest.fixture(autouse=True)
def unfrozen() -> Iterator[None]:
    """Leave the rest of the suite with nothing frozen, as it found it."""
    gc.unfreeze()
    yield
    gc.unfreeze()


@pytest.fixture
def settles(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count the application's settles, still settling for real."""
    calls: list[int] = []

    def counted() -> int:
        calls.append(1)
        return settle_memory()

    monkeypatch.setattr(application_module, "settle_memory", counted)
    return calls


@pytest.fixture
def app() -> Iterator[Any]:
    application = create_headless_application()
    application._clock = FixedClock(1000.0 / 60.0)
    yield application
    application.shutdown()


def scene(app: Any, name: str) -> Quiet:
    made = Quiet(name, app._container.get(EventDispatcher))
    app._container.get(SceneManager).register(made)
    return made


def test_settling_freezes_what_is_alive() -> None:
    kept = Cycle()

    frozen = settle_memory()

    assert frozen == gc.get_freeze_count() > 0
    assert gc.is_tracked(kept)


def test_settling_again_frees_a_cycle_the_last_settle_froze() -> None:
    """Unfreezing first is what stops a frozen scene's garbage living forever."""
    cycle = Cycle()
    alive = weakref.ref(cycle)
    settle_memory()
    del cycle
    gc.collect()
    assert alive() is not None, "a frozen cycle isn't collected"

    settle_memory()

    assert alive() is None


def test_the_first_frame_of_the_starting_scene_settles_memory(
    app: Any, settles: list[int]
) -> None:
    app.begin(scene(app, "start"))
    assert settles == [], "not before a frame has run"

    app.step()

    assert settles == [1]
    assert gc.get_freeze_count() > 0


def test_later_frames_of_the_same_scenes_do_not(app: Any, settles: list[int]) -> None:
    app.begin(scene(app, "start"))
    for _ in range(5):
        app.step()

    assert settles == [1]


def test_a_new_scene_settles_once_more(app: Any, settles: list[int]) -> None:
    app.begin(scene(app, "start"))
    app.step()
    scene(app, "next")
    app._container.get(SceneManager).switch_to("next")
    for _ in range(3):
        app.step()

    assert settles == [1, 1]


def test_a_layer_coming_or_going_settles(app: Any, settles: list[int]) -> None:
    app.begin(scene(app, "start"))
    app.step()
    scene(app, "hud")
    manager = app._container.get(SceneManager)

    manager.add_layer("hud")
    app.step()
    manager.remove_layer("hud")
    app.step()

    assert settles == [1, 1, 1]


def test_nothing_settles_until_a_transition_is_over(
    app: Any, settles: list[int]
) -> None:
    app.begin(scene(app, "start"))
    app.step()
    scene(app, "next")
    manager = app._container.get(SceneManager)
    manager.switch_to("next", FadeTransition(TransitionConfig(duration=0.5)))

    # A two-phase fade swaps the current scene at its midpoint, while still
    # running: the frames after that are the ones that must wait.
    frames = 0
    while manager.is_transitioning():
        assert settles == [1], f"settled on frame {frames} of the transition"
        app.step()
        frames += 1
    assert frames > 20

    app.step()

    assert settles == [1, 1]


def test_turned_off_it_never_settles(app: Any, settles: list[int]) -> None:
    app._config_manager.config.performance.freeze_on_scene_change = False
    app.begin(scene(app, "start"))
    app.step()

    assert settles == []
    assert gc.get_freeze_count() == 0
