"""Post-processing effects for PyGuara.

This module provides screen-space visual effects:
- BloomEffect: Glowing halos around bright areas
- HeatHazeEffect: Refracting hot air and drifting dust
- StormEffect: Procedural rain and lightning
- VignetteEffect: Darkened screen edges
"""

from pyguara.graphics.vfx.effects.bloom import BloomEffect
from pyguara.graphics.vfx.effects.heat_haze import HeatHazeEffect
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect

__all__ = ["BloomEffect", "HeatHazeEffect", "StormEffect", "VignetteEffect"]
