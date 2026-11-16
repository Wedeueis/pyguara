"""Entry point for Tamanduá: O Guardião dos Murundus."""

from __future__ import annotations

from games.tamandua_murundus.bootstrap import (
    configure_game_container,
)
from games.tamandua_murundus.scenes import ClearingScene
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher


def main() -> None:
    """Boot the clearing."""
    container = configure_game_container()
    dispatcher = container.get(EventDispatcher)
    app = container.get(Application)
    app.run(ClearingScene(dispatcher))


if __name__ == "__main__":
    main()
