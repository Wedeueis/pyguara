"""Main module defining the application entry point."""

from pyguara.application import create_application
from pyguara.game.scenes import GameplayScene
from pyguara.events.dispatcher import EventDispatcher


def main() -> None:
    """Application entry point function."""
    # 1. Bootstrap (wires everything automatically)
    app = create_application()

    # 2. Get dependencies for the scene manually if needed,
    # or let the scene resolve them itself.
    # Accessing internal container for scene injection:
    container = app._container
    dispatcher = container.get(EventDispatcher)

    # 3. Create Scene
    start_scene = GameplayScene("level_1", dispatcher)

    # 4. Run
    app.run(start_scene)


if __name__ == "__main__":
    main()
