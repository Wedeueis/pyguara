"""Module 6: Tilemap Authoring bootstrap."""

from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig
from pyguara.di.container import DIContainer


def _configure(config: GameConfig) -> None:
    """Name and size the window this module opens.

    The window is exactly the map: 25 x 18 tiles of 32 pixels is 800 x 576,
    plus 24 pixels for the caption strip. A tutorial about loading a map
    should not also be about scrolling one.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Module 6: Tilemap Authoring"
    config.display.screen_width = 800
    config.display.screen_height = 600
    config.physics.gravity_y = 900.0


def configure_game_container() -> DIContainer:
    """Build the engine container for this module.

    Returns:
        The configured container.
    """
    return create_container(_configure)
