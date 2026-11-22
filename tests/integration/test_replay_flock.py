"""A replay with a flock in it reproduces the flock.

The check #58 asked for before building on replays: a seeded flock once
simulated differently each run, because query order followed `uuid4`.
Here a recorded session adds agents on key presses, and the playback, in a
fresh application, must leave every agent where the recording did.
"""

from __future__ import annotations

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from pathlib import Path

import pygame
import pytest

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.events.input import KeyDownEvent, KeyUpEvent
from pyguara.input import keys as key_codes
from pyguara.input.events import OnActionEvent
from pyguara.input.types import ActionType, InputContext, InputDevice
from pyguara.random.service import RandomService
from tests.integration._scenes import ClearScene

FRAMES = 90
SPAWN = key_codes.D
PRESSES = (5, 30, 31, 60)


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


def _frames(presses: tuple[int, ...]) -> list[list[object]]:
    frames: list[list[object]] = [[] for _ in range(FRAMES + 1)]
    for frame in presses:
        frames[frame].append(KeyDownEvent(key_code=SPAWN))
        frames[frame + 1].append(KeyUpEvent(key_code=SPAWN))
    return frames


def _flock_scene(app: Application) -> ClearScene:
    """Agents scattered from the engine's seeded stream; a press adds three."""
    scene = ClearScene(app._event_dispatcher)
    app.begin(scene)
    rng = app.container.get(RandomService).stream("flock")

    def spawn(count: int) -> None:
        for _ in range(count):
            entity = scene.entity_manager.create_entity()
            entity.add_component(
                Transform(position=Vector2(rng.uniform(0, 300), rng.uniform(0, 300)))
            )
            entity.add_component(
                FlockingAgent(
                    velocity=Vector2(rng.uniform(-40, 40), rng.uniform(-40, 40))
                )
            )

    spawn(40)
    scene.system_manager.register(FlockingSystem(scene.entity_manager))

    def on_action(event: OnActionEvent) -> None:
        if event.action_name == "Spawn":
            spawn(3)

    app._event_dispatcher.subscribe(OnActionEvent, on_action)
    app._input_manager.register_action("Spawn", ActionType.PRESS)
    app._input_manager.bind_input(
        InputDevice.KEYBOARD, SPAWN, "Spawn", InputContext.GAMEPLAY
    )
    return scene


def _positions(scene: ClearScene) -> list[tuple[float, float]]:
    return sorted(
        (t.position.x, t.position.y)
        for t in (
            e.get_component(Transform)
            for e in scene.entity_manager.get_entities_with(Transform)
        )
    )


def _run(app: Application) -> None:
    for _ in range(FRAMES):
        app.step()


def _record(path: Path, presses: tuple[int, ...]) -> list[tuple[float, float]]:
    app = create_headless_application()
    app.start_recording(seed=2024)
    scene = _flock_scene(app)
    app._window.poll_events = iter(_frames(presses)).__next__  # type: ignore[method-assign]
    _run(app)
    data = app.stop_recording()
    assert data is not None
    assert app.save_recording(data, str(path))
    app.shutdown()
    return _positions(scene)


def test_a_replay_with_a_flock_leaves_every_agent_where_the_recording_did(
    tmp_path: Path,
) -> None:
    path = tmp_path / "flock.replay.gz"
    recorded = _record(path, PRESSES)
    assert len(recorded) == 40 + 3 * len(PRESSES)

    app = create_headless_application()
    assert app.load_replay(str(path))
    scene = _flock_scene(app)
    app._window.poll_events = lambda: []  # type: ignore[method-assign]
    _run(app)
    app.shutdown()

    assert _positions(scene) == recorded


def test_the_check_can_fail(tmp_path: Path) -> None:
    """Different input moves the flock somewhere else, so equality means something."""
    assert _record(tmp_path / "a.replay.gz", PRESSES) != _record(
        tmp_path / "b.replay.gz", (5, 30, 31, 61)
    )
