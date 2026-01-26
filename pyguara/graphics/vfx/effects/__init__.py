"""Post-processing effects for PyGuara.

This module provides screen-space visual effects:
- BloomEffect: Glowing halos around bright areas
- VignetteEffect: Darkened screen edges
"""

from pyguara.graphics.vfx.effects.bloom import BloomEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect

__all__ = ["BloomEffect", "VignetteEffect"]
