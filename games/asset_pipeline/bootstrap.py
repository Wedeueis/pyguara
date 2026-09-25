"""Module 3: Asset Pipeline Bootstrap."""

import os

from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig
from pyguara.di.container import DIContainer
from pyguara.resources.manager import ResourceManager


def _configure(config: GameConfig) -> None:
    """Name and size the window this module opens.

    Called before the window exists, so this is what it is built from.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Module 3: Asset Pipeline"
    config.display.screen_width = 800
    config.display.screen_height = 600


def configure_game_container() -> DIContainer:
    """Build the engine container, then index this module's assets.

    `create_container()` already builds a `ResourceManager` with the image,
    sound, JSON and prefab loaders registered -- which is the whole of what
    the other modules need. This module's own topic is what comes next:
    pointing that manager at a directory so `.meta` files are discovered.

    That split is the point. A game asks the engine for the wiring every
    game needs, and writes only the part that is its own.

    Returns:
        The configured container.
    """
    container = create_container(_configure)

    resources = container.get(ResourceManager)
    assets_path = os.path.join(os.path.dirname(__file__), "assets")
    resources.index_directory(assets_path)

    return container
