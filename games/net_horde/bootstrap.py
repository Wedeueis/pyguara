"""Net Horde: bootstrap."""

from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig
from pyguara.di.container import DIContainer


def _configure(config: GameConfig) -> None:
    """Name and size the window.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Net Horde"
    config.display.screen_width = 1000
    config.display.screen_height = 560


def configure_game_container() -> DIContainer:
    """Build the engine container.

    Returns:
        The configured container.
    """
    return create_container(_configure)
