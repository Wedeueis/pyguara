"""
Sandbox Entry Point.
Runs the game with developer tools and the robust ImGui editor.
"""

from pyguara.application import create_sandbox_application
from pyguara.game.scenes import GameplayScene
from pyguara.events.dispatcher import EventDispatcher


def main() -> None:
    """Run sandbox application."""
    # 1. Bootstrap Sandbox (includes ToolManager and Editor)
    app = create_sandbox_application()

    # 2. Setup Scene
    container = app._container
    dispatcher = container.get(EventDispatcher)
    start_scene = GameplayScene("sandbox_level", dispatcher)

    # 3. Run
    app.run(start_scene)


if __name__ == "__main__":
    main()
