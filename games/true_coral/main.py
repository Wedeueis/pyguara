"""True Coral - Entry Point.

A Sokoban-style puzzle game demonstrating:
- Grid-based movement
- Tween animations
- Coroutines for sequences
- Undo functionality
"""

import sys
import logging
import os

# Ensure we can import pyguara from root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher
from games.true_coral.bootstrap import configure_game_container
from games.true_coral.scenes import MenuScene


def main():
    """Application entry point."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("TrueCoral")
    logger.info("Starting True Coral")

    # Bootstrap DI container
    container = configure_game_container()

    # Resolve application
    app = container.get(Application)

    # Create initial scene
    event_dispatcher = container.get(EventDispatcher)
    start_scene = MenuScene(event_dispatcher)

    # Run game loop
    try:
        app.run(starting_scene=start_scene)
    except KeyboardInterrupt:
        logger.info("Game stopped by user.")
    except Exception as e:
        logger.critical(f"Game crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
