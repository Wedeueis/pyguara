"""Two real `Application`s over a real socket, running the Net Horde demo's scenes.

The other suites use a simulated wire and no frame loop. This is everything together:
the hooks in `Application.step`, the session, replication, and the socket thread.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from games.net_horde.scenes import HostScene, JoinScene  # noqa: E402
from games.net_horde.world import HORDE_SIZE, Avatar, Move  # noqa: E402
from pyguara.application.application import Application  # noqa: E402
from pyguara.application.bootstrap import create_headless_application  # noqa: E402
from pyguara.application.clock import FixedClock  # noqa: E402
from pyguara.common.components import Transform  # noqa: E402
from pyguara.events.dispatcher import EventDispatcher  # noqa: E402
from pyguara.events.input import KeyDownEvent, KeyUpEvent  # noqa: E402
from pyguara.input.keys import D, W  # noqa: E402
from pyguara.input.manager import InputManager  # noqa: E402
from pyguara.scene.base import Scene  # noqa: E402

pytestmark = pytest.mark.integration


def start(scene_factory: object) -> tuple[Application, Scene]:
    app = create_headless_application()
    app._clock = FixedClock()
    dispatcher = app._container.get(EventDispatcher)
    scene = scene_factory(dispatcher)  # type: ignore[operator]
    app.begin(scene)
    return app, scene


def test_a_client_application_shows_what_a_host_application_simulates() -> None:
    host_app, host = start(lambda d: HostScene(d, 0, "127.0.0.1"))
    client_app, client = start(lambda d: JoinScene(d, host._invite))  # type: ignore[attr-defined]
    try:
        hashes_matched = 0
        deadline = time.monotonic() + 30
        replication = client._replication  # type: ignore[attr-defined]
        while time.monotonic() < deadline:
            host_app.step()
            client_app.step()
            time.sleep(0.002)
            hashes_matched = replication.digests_matched
            if hashes_matched >= 3 and len(replication.entities()) >= HORDE_SIZE:
                break

        assert len(replication.entities()) >= HORDE_SIZE
        assert hashes_matched >= 3
        assert replication.digests_mismatched == 0
        assert replication.malformed == 0
        assert host._slots == [1]  # type: ignore[attr-defined]
        assert client._slot == 1  # type: ignore[attr-defined]
    finally:
        client_app.shutdown()
        host_app.shutdown()


def test_a_real_client_steers_its_character_and_the_host_agrees() -> None:
    """Everything together, over a real socket: keys, prediction, the host and back."""
    host_app, host = start(lambda d: HostScene(d, 0, "127.0.0.1"))
    client_app, client = start(lambda d: JoinScene(d, host._invite))  # type: ignore[attr-defined]
    keys = client._keys  # type: ignore[attr-defined]
    held = [Move(0.0, -1.0)]
    keys.command = lambda: held[0]  # The physical key layer has its own tests.
    prediction = client._player.prediction  # type: ignore[attr-defined]
    simulation = host._simulation  # type: ignore[attr-defined]
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and prediction.tick is None:
            host_app.step()
            client_app.step()
            time.sleep(0.002)
        assert prediction.tick is not None

        avatar = simulation.avatar(client._slot)  # type: ignore[attr-defined]
        start_y = avatar.get_component(Transform).position.y
        for _ in range(60):
            host_app.step()
            client_app.step()
            time.sleep(0.002)
        assert avatar.get_component(Transform).position.y < start_y

        held[0] = Move()
        for _ in range(120):
            host_app.step()
            client_app.step()
            time.sleep(0.002)

        assert prediction.malformed == 0
        own = next(
            e
            for e in client.entity_manager.get_entities_with(Avatar)  # type: ignore[attr-defined]
            if e.get_component(Avatar).slot == client._slot  # type: ignore[attr-defined]
        )
        assert (
            own.get_component(Transform).position
            == avatar.get_component(Transform).position
        )
    finally:
        client_app.shutdown()
        host_app.shutdown()


def test_the_movement_keys_reach_the_command() -> None:
    """The other test stands in for the keys, so this one covers the real path."""
    host_app, host = start(lambda d: HostScene(d, 0, "127.0.0.1"))
    try:
        inputs = host.container.get(InputManager)
        keys = host._keys  # type: ignore[attr-defined]
        assert keys.command() == Move()
        inputs.process_event(KeyDownEvent(key_code=D))
        inputs.process_event(KeyDownEvent(key_code=W))
        assert keys.command() == Move(1.0, -1.0)
        inputs.process_event(KeyUpEvent(key_code=D))
        assert keys.command() == Move(0.0, -1.0)
        inputs.process_event(KeyUpEvent(key_code=W))
        assert keys.command() == Move()
    finally:
        host_app.shutdown()
