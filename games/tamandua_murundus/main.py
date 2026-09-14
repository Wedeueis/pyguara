"""Entry point for Tamanduá: O Guardião dos Murundus."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from games.tamandua_murundus.bootstrap import (  # noqa: E402
    configure_game_container,
)
from games.tamandua_murundus.scenes import ClearingScene  # noqa: E402
from pyguara.application.application import Application  # noqa: E402
from pyguara.events.dispatcher import EventDispatcher  # noqa: E402


def main() -> None:
    """Boot the clearing."""
    container = configure_game_container()
    dispatcher = container.get(EventDispatcher)
    app = container.get(Application)
    app.run(ClearingScene(dispatcher))


if __name__ == "__main__":
    main()
