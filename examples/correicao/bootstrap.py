"""Correição: the window, and nothing else the engine does not already wire."""

from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig
from pyguara.di.container import DIContainer

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SEED = 1987


def _configure(config: GameConfig) -> None:
    """Name and size the window, and fix the seed.

    A fixed seed makes every run the same raid, which is what a benchmark
    and a frame comparison need.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Correição"
    config.display.screen_width = SCREEN_WIDTH
    config.display.screen_height = SCREEN_HEIGHT
    config.debug.rng_seed = SEED


def configure_game_container() -> DIContainer:
    """Build the engine container for this demo.

    Returns:
        The configured container.
    """
    return create_container(_configure)
