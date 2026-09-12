"""Visual effects system for PyGuara.

Two layers live here:

- **Post-processing** -- `PostProcessEffect` and `PostProcessStack`, plus
  the shipped screen-space effects (bloom, heat haze, storm, vignette).
  These transform the finished frame.
- **Feedback** -- `Sparks` and `Shaker`, the small pooled primitives a
  game reaches for when something is hit. These are composed into a scene
  rather than resolved from DI, the same way `ParticleSystem` is.
"""

from pyguara.graphics.vfx.effects import (
    BloomEffect,
    HeatHazeEffect,
    StormEffect,
    VignetteEffect,
)
from pyguara.graphics.vfx.post_process import PostProcessEffect, PostProcessStack
from pyguara.graphics.vfx.shake import Shaker
from pyguara.graphics.vfx.sparks import Sparks

__all__ = [
    "PostProcessEffect",
    "PostProcessStack",
    "BloomEffect",
    "HeatHazeEffect",
    "StormEffect",
    "VignetteEffect",
    "Sparks",
    "Shaker",
]
