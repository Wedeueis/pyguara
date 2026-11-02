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
from games.net_horde.world import HORDE_SIZE  # noqa: E402
from pyguara.application.application import Application  # noqa: E402
from pyguara.application.bootstrap import create_headless_application  # noqa: E402
from pyguara.application.clock import FixedClock  # noqa: E402
from pyguara.events.dispatcher import EventDispatcher  # noqa: E402
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
