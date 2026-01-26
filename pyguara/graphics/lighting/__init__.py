"""Dynamic 2D lighting system for PyGuara.

This module provides:
- LightSource: Component for creating dynamic lights
- AmbientLight: Component for scene-wide ambient lighting
- LightingSystem: ECS system that processes lights for rendering
"""

from pyguara.graphics.lighting.components import (
    LightSource,
    LightType,
    AmbientLight,
)
from pyguara.graphics.lighting.light_system import LightData, LightingSystem

__all__ = [
    "LightSource",
    "LightType",
    "AmbientLight",
    "LightData",
    "LightingSystem",
]
