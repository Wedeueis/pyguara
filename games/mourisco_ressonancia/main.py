"""Mourisco: Ressonância - Entry Point."""

import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from games.mourisco_ressonancia.bootstrap import configure_game_container
from games.mourisco_ressonancia.scenes import CaveScene
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher


def main() -> None:
    """Application entry point."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("MouriscoRessonancia")
    logger.info("Starting Mourisco: Ressonância")

    container = configure_game_container()
    app = container.get(Application)
    event_dispatcher = container.get(EventDispatcher)

    try:
        app.run(starting_scene=CaveScene(event_dispatcher))
    except KeyboardInterrupt:
        logger.info("Game stopped by user.")
    except Exception as e:
        logger.critical(f"Game crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
