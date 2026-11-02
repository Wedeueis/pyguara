"""Net Horde: see replication running.

    uv run python games/net_horde/main.py                      # both sides, one window
    uv run python games/net_horde/main.py --host               # first window
    uv run python games/net_horde/main.py --join "pyguara://"  # second window

Only the host simulates anything. A client draws what arrives, about 100 ms behind.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from games.net_horde.bootstrap import configure_game_container
from games.net_horde.scenes import HostScene, JoinScene, SideBySideScene
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher


def main() -> None:
    """Parse the command line and run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="store_true", help="host over a real socket")
    parser.add_argument("--join", metavar="INVITE", help="join using an invite")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument(
        "--public-host",
        default="127.0.0.1",
        help="the address other machines reach this one at",
    )
    args = parser.parse_args()

    container = configure_game_container()
    app = container.get(Application)
    dispatcher = container.get(EventDispatcher)
    if args.host:
        scene = HostScene(dispatcher, args.port, args.public_host)
    elif args.join:
        scene = JoinScene(dispatcher, args.join)
    else:
        scene = SideBySideScene(dispatcher)
    app.run(starting_scene=scene)


if __name__ == "__main__":
    main()
