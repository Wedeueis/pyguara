"""Dynamic 2D lighting system for PyGuara.

This module provides:
- LightSource: Component for creating dynamic lights
- AmbientLight: Component for scene-wide ambient lighting
- LightingSystem: ECS system that processes lights for rendering
- AmbientCycle / AmbientCycleSystem: drives AmbientLight around a loop of
  keyframes -- the mechanism under a day/night cycle
"""

from pyguara.graphics.lighting.components import (
    AmbientLight,
    LightSource,
    LightType,
)
from pyguara.graphics.lighting.cycle import (
    AmbientCycle,
    AmbientCycleSystem,
    LightKeyframe,
    sample_cycle,
)
from pyguara.graphics.lighting.light_system import LightData, LightingSystem

__all__ = [
    "LightSource",
    "LightType",
    "AmbientLight",
    "AmbientCycle",
    "AmbientCycleSystem",
    "LightKeyframe",
    "sample_cycle",
    "LightData",
    "LightingSystem",
]
