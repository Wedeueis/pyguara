"""Module 1: The Boot Process - Entry Point

This file demonstrates the minimal code required to start the PyGuara engine.
"""

import sys
import logging
import os

# Ensure we can import pyguara from root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher
from games.boot_process.bootstrap import configure_game_container
from games.boot_process.scenes import BootScene

def main():
    """Application Entry Point."""
    # 1. Configure Logging (Optional but recommended)
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Game")
    logger.info("Starting Module 1: The Boot Process")

    # 2. Bootstrap the Dependency Injection Container
    # This is where we wire up all our systems
    container = configure_game_container()

    # 3. Resolve the Application instance
    app = container.get(Application)

    # 4. Create Initial Scene
    # Note: Scene constructor needs EventDispatcher
    event_dispatcher = container.get(EventDispatcher)
    start_scene = BootScene(event_dispatcher)

    # 5. Run the Game Loop
    try:
        app.run(starting_scene=start_scene)
    except KeyboardInterrupt:
        logger.info("Game stopped by user.")
    except Exception as e:
        logger.critical(f"Game crashed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
