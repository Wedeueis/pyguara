"""Module 2: ECS Mental Model - Entry Point"""

import sys
import logging
import os

# Ensure we can import pyguara from root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher
from games.ecs_mental_model.bootstrap import configure_game_container
from games.ecs_mental_model.scenes import ECSScene

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Game")
    logger.info("Starting Module 2: The ECS Mental Model")

    container = configure_game_container()
    app = container.get(Application)
    
    event_dispatcher = container.get(EventDispatcher)
    start_scene = ECSScene(event_dispatcher)

    try:
        app.run(starting_scene=start_scene)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Game crashed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
