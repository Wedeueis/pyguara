"""Correição: start the raid.

uv run python -m examples.correicao.main              # 2,000 ants
uv run python -m examples.correicao.main --ants 10000
"""

import argparse
import logging

from examples.correicao.bootstrap import configure_game_container
from examples.correicao.scenes import DEFAULT_ANTS, HordeScene
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher


def main() -> None:
    """Parse the raid's size and run the game."""
    parser = argparse.ArgumentParser(description="Correição: an army-ant raid.")
    parser.add_argument("--ants", type=int, default=DEFAULT_ANTS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    container = configure_game_container()
    app = container.get(Application)
    app.run(HordeScene(container.get(EventDispatcher), ants=args.ants))


if __name__ == "__main__":
    main()
