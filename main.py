"""Main module defining the application entry point."""

from games.boot_process.scenes import BootScene
from pyguara.application import create_application
from pyguara.events.dispatcher import EventDispatcher


def main() -> None:
    """Application entry point function."""
    # 1. Bootstrap (wires everything automatically)
    app = create_application()

    # 2. A scene is built with the application's event dispatcher.
    dispatcher = app.container.get(EventDispatcher)

    # 3. Create Scene
    start_scene = BootScene(dispatcher)

    # 4. Run
    app.run(start_scene)


if __name__ == "__main__":
    main()
