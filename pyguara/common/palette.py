"""
Standard color definitions for Engine utilities and Debugging.

This module provides quick access to common colors.
For game-specific artistic palettes, prefer loading them as Resources.
"""

from pyguara.common.types import Color


class BasicColors:
    """Standard CSS/HTML colors for rapid prototyping."""

    WHITE = Color(255, 255, 255)
    BLACK = Color(0, 0, 0)
    TRANSPARENT = Color(0, 0, 0, 0)

    RED = Color(255, 0, 0)
    GREEN = Color(0, 255, 0)
    BLUE = Color(0, 0, 255)
    YELLOW = Color(255, 255, 0)
    CYAN = Color(0, 255, 255)
    MAGENTA = Color(255, 0, 255)


class DebugColors:
    """
    Semantic colors for the Engine's debug visualization system.

    Using semi-transparency allows seeing the game behind the debug shapes.
    """

    # Physics
    COLLIDER_ACTIVE = Color(0, 255, 0, 150)  # Green: Safe/Active
    COLLIDER_SLEEPING = Color(128, 128, 128, 150)  # Gray: Sleeping body
    COLLIDER_CONTACT = Color(255, 0, 0, 180)  # Red: Collision happening

    # Logic
    RAYCAST = Color(255, 255, 0)  # Yellow Line
    PATHFINDING = Color(0, 255, 255, 100)  # Cyan Path

    # UI Bounds
    UI_BORDER = Color(255, 0, 255)  # Magenta Rect
