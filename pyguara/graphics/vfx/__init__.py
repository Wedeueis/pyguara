"""Visual effects system for PyGuara.

This module provides post-processing infrastructure:
- PostProcessEffect: Base class for screen-space effects
- PostProcessStack: Manager for chaining effects
- Effects: Bloom, Vignette, and more
"""

from pyguara.graphics.vfx.post_process import PostProcessEffect, PostProcessStack
from pyguara.graphics.vfx.effects import BloomEffect, VignetteEffect

__all__ = [
    "PostProcessEffect",
    "PostProcessStack",
    "BloomEffect",
    "VignetteEffect",
]
