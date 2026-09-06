"""Named colours for engine utilities and debug drawing.

`BasicColors` re-exports the constants defined on `Color` itself, so the two
spellings can never drift apart. For game-specific artistic palettes, load a
palette as a resource instead of extending these.
"""

from pyguara.common.types import Color


class BasicColors:
    """Standard colours for rapid prototyping."""

    WHITE = Color.WHITE
    BLACK = Color.BLACK
    TRANSPARENT = Color.TRANSPARENT

    RED = Color.RED
    GREEN = Color.GREEN
    BLUE = Color.BLUE
    YELLOW = Color.YELLOW
    CYAN = Color.CYAN
    MAGENTA = Color.MAGENTA


class DebugColors:
    """Semantic colours for the engine's debug visualisation.

    Most are semi-transparent so the game stays visible behind debug shapes.
    """

    COLLIDER_ACTIVE = Color(0, 255, 0, 150)
    COLLIDER_SLEEPING = Color(128, 128, 128, 150)
    COLLIDER_CONTACT = Color(255, 0, 0, 180)

    RAYCAST = Color(255, 255, 0)
    PATHFINDING = Color(0, 255, 255, 100)

    UI_BORDER = Color(255, 0, 255)
