"""Vinagre: Matilha - Bootstrap.

Configures the DI container for the squad-tactics demo.

Physics is here because two mechanics need it -- the water currents and
the pressure plate are trigger volumes -- but nothing in this demo is a
falling body, and level geometry (walls, the log) blocks movement through
the pack's own `GridGraph` rather than physics collision. Gravity is
therefore zero, set per-scene where `GameScene` builds its `PhysicsSystem`,
not here.
"""

from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig
from pyguara.di.container import DIContainer


def _configure(config: GameConfig) -> None:
    """Name and size the window this demo opens.

    Called before the window exists, so this is what it is built from.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Vinagre: Matilha -- Tactical Pack Action!"
    config.display.screen_width = 960
    config.display.screen_height = 640


def configure_game_container() -> DIContainer:
    """Build the engine container for this demo.

    Everything this demo resolves -- `Window`, `IPhysicsEngine`,
    `InputManager`, `SceneManager`, `UIManager`, `SpatialHash`,
    `EventDispatcher`, `Application` -- `create_container()` already wires,
    so there is nothing demo-specific to add here. What makes this demo
    what it is lives in `scenes.py` and `systems.py`, which is where it
    belongs.

    Returns:
        The configured container.
    """
    return create_container(_configure)
