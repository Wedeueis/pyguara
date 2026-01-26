"""Lighting system for rendering dynamic 2D lights.

This system queries entities with LightSource components and prepares
light data for the light render pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List

from pyguara.common.types import Color, Vector2
from pyguara.common.components import Transform
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.lighting.components import AmbientLight, LightSource

if TYPE_CHECKING:
    pass


@dataclass
class LightData:
    """Processed light data ready for rendering.

    Contains screen-space position and normalized parameters
    for the GPU.
    """

    position: Vector2  # Screen position (pixels)
    radius: float  # Screen radius (pixels)
    color: tuple[float, float, float]  # Normalized RGB (0-1)
    intensity: float
    falloff: float


class LightingSystem:
    """System that collects and processes lights for rendering.

    Queries entities with LightSource components, transforms their
    positions to screen space, and prepares data for the light pass.

    Implements InitializableSystem and CleanupSystem protocols.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        """Initialize the lighting system.

        Args:
            entity_manager: The ECS entity manager.
        """
        self._entity_manager = entity_manager
        self._lights: List[LightData] = []
        self._ambient_color: Color = Color(30, 30, 40)
        self._ambient_intensity: float = 0.3

    @property
    def lights(self) -> List[LightData]:
        """Get the current frame's processed lights."""
        return self._lights

    @property
    def ambient_color(self) -> Color:
        """Get the ambient light color."""
        return self._ambient_color

    @property
    def ambient_intensity(self) -> float:
        """Get the ambient light intensity."""
        return self._ambient_intensity

    def get_ambient_normalized(self) -> tuple[float, float, float]:
        """Get ambient color as normalized RGB tuple."""
        return (
            self._ambient_color[0] / 255.0 * self._ambient_intensity,
            self._ambient_color[1] / 255.0 * self._ambient_intensity,
            self._ambient_color[2] / 255.0 * self._ambient_intensity,
        )

    def initialize(self) -> None:
        """Initialize the lighting system."""
        pass

    def cleanup(self) -> None:
        """Cleanup the lighting system."""
        self._lights.clear()

    def update(self, dt: float) -> None:
        """Update the lighting system.

        Queries all entities with LightSource components and collects
        their data for rendering. Position transform happens in the
        light pass using the camera.

        Args:
            dt: Delta time in seconds.
        """
        self._lights.clear()

        # Query ambient light (use first found)
        for entity in self._entity_manager.get_entities_with(AmbientLight):
            ambient = entity.get_component(AmbientLight)
            if ambient is not None:
                self._ambient_color = ambient.color
                self._ambient_intensity = ambient.intensity
                break

        # Query all lights
        for entity in self._entity_manager.get_entities_with(LightSource, Transform):
            light = entity.get_component(LightSource)
            transform = entity.get_component(Transform)

            if light is None or transform is None or not light.enabled:
                continue

            # Store world position - screen transform happens in render pass
            light_data = LightData(
                position=transform.position,
                radius=light.radius,
                color=(
                    light.color[0] / 255.0,
                    light.color[1] / 255.0,
                    light.color[2] / 255.0,
                ),
                intensity=light.intensity,
                falloff=light.falloff,
            )
            self._lights.append(light_data)

    def collect_lights_screen_space(
        self,
        camera_position: Vector2,
        camera_zoom: float,
        viewport_offset: Vector2,
    ) -> List[LightData]:
        """Get lights with positions transformed to screen space.

        Args:
            camera_position: Camera world position.
            camera_zoom: Camera zoom factor.
            viewport_offset: Viewport offset in screen space.

        Returns:
            List of LightData with screen-space positions.
        """
        screen_lights: List[LightData] = []

        for light in self._lights:
            # Transform world position to screen space
            screen_pos = (
                light.position - camera_position
            ) * camera_zoom + viewport_offset

            screen_light = LightData(
                position=screen_pos,
                radius=light.radius * camera_zoom,  # Scale radius by zoom
                color=light.color,
                intensity=light.intensity,
                falloff=light.falloff,
            )
            screen_lights.append(screen_light)

        return screen_lights
