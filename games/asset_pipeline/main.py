"""Module 3: Asset Pipeline - Entry Point."""

import sys
import logging
import os

# Ensure we can import pyguara from root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher
from games.asset_pipeline.bootstrap import configure_game_container
from games.asset_pipeline.scenes import AssetScene


def main():
    """Run the Asset Pipeline tutorial."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Game")
    logger.info("Starting Module 3: The Asset Pipeline")

    container = configure_game_container()
    app = container.get(Application)

    event_dispatcher = container.get(EventDispatcher)
    start_scene = AssetScene(event_dispatcher)

    try:
        app.run(starting_scene=start_scene)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Game crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
