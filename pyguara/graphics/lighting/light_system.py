"""Lighting system for rendering dynamic 2D lights.

This system queries entities with LightSource components and prepares
light data for the light render pass.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.lighting.components import AmbientLight, LightSource, LightType

if TYPE_CHECKING:
    pass


# Successive multiples of this are spread as widely as any sequence can
# be on a circle -- the standard trick for de-correlating per-entity
# phases without a random source.
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


@dataclass
class LightData:
    """Processed light data ready for rendering.

    Contains screen-space position and normalized parameters
    for the GPU.

    The cone terms are resolved here rather than in the shader:
    `spot_cos_half_angle` is the cosine of half the cone's opening,
    precomputed on the CPU so `light.frag` compares two dot products
    instead of calling `cos` once per fragment.

    `intensity` is the *resolved* intensity, flicker already folded in --
    a flickering light's value changes every frame, and nothing downstream
    needs to know why.
    """

    position: Vector2  # Screen position (pixels)
    radius: float  # Screen radius (pixels)
    color: tuple[float, float, float]  # Normalized RGB (0-1)
    intensity: float
    falloff: float

    # Which of the three shapes `light.frag` should draw. Carried as a
    # float because it travels as one column of an instance array.
    light_type: float = float(LightType.POINT.value)

    # Cone axis, radians, measured clockwise from screen +x -- the same
    # convention `IRenderer.draw_line` uses, since screen Y points down.
    spot_direction: float = 0.0

    # cos(spot_angle / 2), so the shader's cone test is a dot product
    # against this. 1.0 is a degenerate zero-width cone.
    spot_cos_half_angle: float = 1.0


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
        self._lights: list[LightData] = []
        self._ambient_color: Color = Color(30, 30, 40)
        self._ambient_intensity: float = 0.3
        # Per-light flicker phase, keyed by entity id. Pruned each frame
        # so a destroyed light does not leave its phase behind forever.
        self._flicker_phases: dict[str, float] = {}

    @property
    def lights(self) -> list[LightData]:
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
        live_flickers: set[str] = set()
        for entity in self._entity_manager.get_entities_with(LightSource, Transform):
            light = entity.get_component(LightSource)
            transform = entity.get_component(Transform)

            if light is None or transform is None or not light.enabled:
                continue

            intensity = light.intensity
            if light.flicker_enabled:
                live_flickers.add(entity.id)
                intensity = self._resolve_flicker(entity.id, light, dt)

            # Store world position - screen transform happens in render pass
            light_data = LightData(
                position=transform.position,
                radius=light.radius,
                color=(
                    light.color[0] / 255.0,
                    light.color[1] / 255.0,
                    light.color[2] / 255.0,
                ),
                intensity=intensity,
                falloff=light.falloff,
                light_type=float(light.light_type.value),
                spot_direction=math.radians(light.spot_direction),
                spot_cos_half_angle=math.cos(math.radians(light.spot_angle) / 2.0),
            )
            self._lights.append(light_data)

        # Drop phases belonging to lights that are gone or no longer
        # flickering, so the dict tracks the scene rather than its history.
        if len(self._flicker_phases) != len(live_flickers):
            self._flicker_phases = {
                entity_id: phase
                for entity_id, phase in self._flicker_phases.items()
                if entity_id in live_flickers
            }

    def _resolve_flicker(self, entity_id: str, light: LightSource, dt: float) -> float:
        """Advance this light's flicker phase and return its intensity now.

        Resolved on the CPU, deliberately. This system already iterates
        every light every frame and already has `dt`, so doing it here
        needs no time uniform and no extra instance attribute -- and,
        decisively, it stays testable without a GL context, which is the
        only kind of lighting test this repo can run.

        The waveform is two sines at incommensurate frequencies rather
        than one, so a torch reads as guttering instead of pulsing, and
        `RandomStream` stays out of it: a light's brightness should not
        depend on how many other systems drew from a shared stream this
        frame.

        Args:
            entity_id: Identifies this light's phase across frames.
            light: The light being resolved.
            dt: Seconds since the last update.

        Returns:
            The intensity to render with, within `flicker_intensity` of
            the light's configured intensity and never below zero.
        """
        phase = self._flicker_phases.get(entity_id)
        if phase is None:
            # Offset per light so a row of torches does not gutter in
            # lockstep. Entity ids are opaque strings, so the offset comes
            # from a checksum of one -- `hash()` is salted per process, and
            # a light that flickers differently on every run would break
            # replay reproduction for the sake of a starting phase. The
            # golden angle then spreads consecutive values about as widely
            # as anything can on a circle.
            phase = (zlib.crc32(entity_id.encode()) * _GOLDEN_ANGLE) % math.tau

        phase = (phase + dt * light.flicker_speed) % math.tau
        self._flicker_phases[entity_id] = phase

        wave = 0.5 * math.sin(phase) + 0.5 * math.sin(phase * 1.7 + 1.3)
        return max(0.0, light.intensity * (1.0 + light.flicker_intensity * wave))

    def collect_lights_screen_space(
        self,
        camera_zoom: float,
        viewport_offset: Vector2,
    ) -> list[LightData]:
        """Get lights with positions transformed to screen space.

        The transform is `Camera2D`'s single world-to-screen definition:
        `world * zoom + screen_offset`. This used to subtract the camera
        position here as well, on top of the `screen_offset` that already
        has it subtracted out -- so every light was displaced by a whole
        camera position, which on a centred camera threw the entire light
        map off the left of the frame. `PulsePass` hit and documented the
        same double-subtraction; this is the other half of it.

        Args:
            camera_zoom: Camera zoom factor.
            viewport_offset: The camera's `screen_offset(viewport)` -- the
                translation that already accounts for camera position.

        Returns:
            List of LightData with screen-space positions.
        """
        screen_lights: list[LightData] = []

        for light in self._lights:
            screen_pos = light.position * camera_zoom + viewport_offset

            screen_light = LightData(
                position=screen_pos,
                radius=light.radius * camera_zoom,  # Scale radius by zoom
                color=light.color,
                intensity=light.intensity,
                falloff=light.falloff,
                light_type=light.light_type,
                spot_direction=light.spot_direction,
                spot_cos_half_angle=light.spot_cos_half_angle,
            )
            screen_lights.append(screen_light)

        return screen_lights
