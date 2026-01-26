"""Light source components for 2D dynamic lighting.

This module provides components for creating dynamic lights that
affect the scene through the lighting render pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from pyguara.common.types import Color
from pyguara.ecs.component import BaseComponent


class LightType(Enum):
    """Types of 2D lights."""

    POINT = auto()  # Radial light from a point
    DIRECTIONAL = auto()  # Parallel rays (sun, moon)
    SPOT = auto()  # Cone-shaped light


@dataclass(slots=True)
class LightSource(BaseComponent):
    """A dynamic light that illuminates the scene.

    Lights are rendered to a separate light map which is then
    composited with the world to create the final lit image.

    Attributes:
        color: RGB color of the light.
        radius: Maximum distance the light reaches (in world units).
        intensity: Brightness multiplier (0.0-1.0, can go higher for HDR).
        falloff: Attenuation curve exponent (1.0 = linear, 2.0 = quadratic).
        light_type: The type of light (point, directional, spot).
        enabled: Whether this light is currently active.
    """

    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    radius: float = 100.0
    intensity: float = 1.0
    falloff: float = 2.0  # Quadratic falloff by default

    # Light type and settings
    light_type: LightType = LightType.POINT

    # Spot light specific (angle in degrees)
    spot_angle: float = 45.0
    spot_direction: float = 0.0  # Angle in degrees from right

    # State
    enabled: bool = True

    # Flicker effect (optional)
    flicker_enabled: bool = False
    flicker_speed: float = 10.0  # Hz
    flicker_intensity: float = 0.1  # How much intensity varies


@dataclass(slots=True)
class AmbientLight(BaseComponent):
    """Global ambient lighting for the scene.

    Sets the base light level when no dynamic lights are present.
    Only one ambient light should be active per scene.

    Attributes:
        color: RGB color of the ambient light.
        intensity: Brightness multiplier (0.0 = pitch black, 1.0 = full bright).
    """

    color: Color = field(default_factory=lambda: Color(30, 30, 40))
    intensity: float = 0.3
