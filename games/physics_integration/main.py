"""Module 5: Physics Integration - Entry Point."""

import logging
import os
import sys

# Ensure we can import pyguara from root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from games.physics_integration.bootstrap import configure_game_container
from games.physics_integration.scenes import PhysicsScene
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher


def main():
    """Run the Physics Integration tutorial."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Game")
    logger.info("Starting Module 5: Physics Integration")

    container = configure_game_container()
    app = container.get(Application)

    event_dispatcher = container.get(EventDispatcher)
    start_scene = PhysicsScene(event_dispatcher)

    try:
        app.run(starting_scene=start_scene)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Game crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
