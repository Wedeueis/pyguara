"""Module 4: Input Bootstrap."""

from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig
from pyguara.di.container import DIContainer


def _configure(config: GameConfig) -> None:
    """Name and size the window this module opens.

    Called before the window exists, so this is what it is built from.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Module 4: Input & Events"
    config.display.screen_width = 800
    config.display.screen_height = 600


def configure_game_container() -> DIContainer:
    """Build the engine container for this module.

    `create_container()` wires the window, renderer, input, physics, audio,
    resources, persistence, prefabs, coroutines, the seeded RNG service and
    the spatial hash -- everything a game can assume is there. A game adds
    only what is its own.

    `games/boot_process` does this by hand instead, and deliberately: how
    the container is assembled is module 1's actual lesson. Every module
    after it is about something else.

    Returns:
        The configured container.
    """
    return create_container(_configure)
