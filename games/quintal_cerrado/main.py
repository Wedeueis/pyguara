"""Quintal do Cerrado - Entry Point.

A cozy agroforestry capstone demonstrating:
- Procedural `pyguara.tilemap` construction and per-cell soil state
- Click-to-cell input through the UI system (`GardenGridCanvas`)
- Real `pyguara.persistence` save/load (from Phase 5 on)
- Plant-lifecycle FSM via `pyguara.ai.fsm` (from Phase 2 on)
"""

import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from games.quintal_cerrado.bootstrap import configure_game_container
from games.quintal_cerrado.scenes import TitleScene
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher


def main() -> None:
    """Application entry point."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("QuintalDoCerrado")
    logger.info("Starting Quintal do Cerrado")

    container = configure_game_container()
    app = container.get(Application)

    event_dispatcher = container.get(EventDispatcher)
    start_scene = TitleScene(event_dispatcher)

    try:
        app.run(starting_scene=start_scene)
    except KeyboardInterrupt:
        logger.info("Game stopped by user.")
    except Exception as e:
        logger.critical(f"Game crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
