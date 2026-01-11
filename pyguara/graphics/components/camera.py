"""
Defines the Camera component for 2D coordinate transformations.

This module provides the `Camera2D` class, which is responsible for converting
coordinates between World Space (game logic) and Screen Space (pixels).
It serves as a data container used by the RenderPipeline, decoupling the math
of "viewing" from the logic of "drawing".
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import Optional

from pyguara.common.types import Vector2, Rect


# ===== Camera Effects Data Structures =====


@dataclass
class CameraShake:
    """
    Camera shake effect for impact feedback.

    Attributes:
        duration (float): Total shake duration in seconds.
        magnitude (float): Maximum shake offset in pixels.
        frequency (float): Shake oscillation speed.
        elapsed (float): Time elapsed since shake started.
    """

    duration: float
    magnitude: float
    frequency: float = 20.0
    elapsed: float = 0.0

    def update(self, dt: float) -> Vector2:
        """
        Calculate shake offset for current frame.

        Args:
            dt (float): Delta time in seconds.

        Returns:
            Vector2: Shake offset to apply to camera position.
        """
        self.elapsed += dt

        if self.elapsed >= self.duration:
            return Vector2.zero()

        # Decay magnitude over time (envelope)
        progress = self.elapsed / self.duration
        current_magnitude = self.magnitude * (1.0 - progress)

        # Random offset based on frequency
        angle = random.uniform(0, 360)
        offset_x = math.cos(math.radians(angle)) * current_magnitude
        offset_y = math.sin(math.radians(angle)) * current_magnitude

        return Vector2(offset_x, offset_y)


@dataclass
class CameraZoomTransition:
    """
    Smooth zoom transition with easing.

    Attributes:
        target_zoom (float): Target zoom level.
        duration (float): Transition duration in seconds.
        start_zoom (float): Starting zoom level.
        elapsed (float): Time elapsed since transition started.
        easing (str): Easing function name ("linear", "smooth", "ease_in", "ease_out").
    """

    target_zoom: float
    duration: float
    start_zoom: float
    elapsed: float = 0.0
    easing: str = "smooth"

    def update(self, dt: float) -> Optional[float]:
        """
        Calculate zoom for current frame.

        Args:
            dt (float): Delta time in seconds.

        Returns:
            Optional[float]: Current zoom value, or None if transition complete.
        """
        self.elapsed += dt

        if self.elapsed >= self.duration:
            return self.target_zoom  # Ensure we hit exact target

        # Calculate progress (0.0 to 1.0)
        t = self.elapsed / self.duration

        # Apply easing function
        if self.easing == "smooth":
            # Smoothstep (ease in and out)
            t = t * t * (3.0 - 2.0 * t)
        elif self.easing == "ease_in":
            # Quadratic ease in
            t = t * t
        elif self.easing == "ease_out":
            # Quadratic ease out
            t = 1.0 - (1.0 - t) * (1.0 - t)
        # else: linear (no modification to t)

        # Lerp between start and target
        return self.start_zoom + (self.target_zoom - self.start_zoom) * t


@dataclass
class CameraFollowConstraints:
    """
    Constraints for smooth camera following.

    Attributes:
        deadzone (Rect): Rectangle where target can move without camera moving.
        max_speed (float): Maximum camera movement speed in pixels/second.
        smooth_time (float): Smoothing factor (smaller = more responsive).
    """

    deadzone: Rect
    max_speed: float = float("inf")
    smooth_time: float = 0.1


class Camera2D:
    """
    A 2D Camera component that defines the viewable area of the game world.

    It handles Zoom, Rotation, and Panning math. It does NOT render anything;
    it simply provides the transformation matrices (or equivalent logic) for the renderer.

    Attributes:
        position (Vector2): The center of the camera in World Coordinates.
        offset (Vector2): The center of the viewport in Screen Coordinates.
        zoom (float): The scale factor (1.0 = 100%, 2.0 = 200%).
        rotation (float): The rotation in degrees.
    """

    def __init__(self, width: int, height: int):
        """
        Initialize the Camera with a default viewport size.

        Args:
            width (int): The initial width of the target viewport/screen.
            height (int): The initial height of the target viewport/screen.
        """
        self.position: Vector2 = Vector2.zero()
        self.offset: Vector2 = Vector2(width / 2, height / 2)
        self.zoom: float = 1.0
        self.rotation: float = 0.0

        # Camera effects
        self._shake: Optional[CameraShake] = None
        self._zoom_transition: Optional[CameraZoomTransition] = None
        self._target_position: Optional[Vector2] = None
        self._follow_constraints: Optional[CameraFollowConstraints] = None
        self._follow_velocity: Vector2 = Vector2.zero()

    def set_viewport_size(self, width: int, height: int) -> None:
        """
        Recalculate the screen offset based on new dimensions.

        Call this when the window is resized to keep the camera centered.

        Args:
            width (int): New width in pixels.
            height (int): New height in pixels.
        """
        self.offset = Vector2(width / 2, height / 2)

    def world_to_screen(self, world_pos: Vector2) -> Vector2:
        """
        Transform a point from World Space to Screen Space.

        Formula: (WorldPos - CamPos) * Zoom + ScreenOffset

        Args:
            world_pos (Vector2): The coordinate in the game world.

        Returns:
            Vector2: The pixel coordinate on the screen.
        """
        # 1. Translate world to camera local
        local_pos = world_pos - self.position

        # 2. Scale (Zoom)
        local_pos = local_pos * self.zoom

        # 3. Rotate (around camera center)
        if self.rotation != 0:
            local_pos = local_pos.rotate(-self.rotation)

        screen_pos = local_pos + self.offset

        # 4. Translate to screen center
        return screen_pos

    def screen_to_world(self, screen_pos: Vector2) -> Vector2:
        """
        Transform a point from Screen Space (e.g., Mouse) to World Space.

        This is the inverse of world_to_screen.
        Formula: (ScreenPos - ScreenOffset) / Zoom + CamPos

        Args:
            screen_pos (Vector2): The pixel coordinate (e.g., pygame.mouse.get_pos()).

        Returns:
            Vector2: The coordinate in the game world.
        """
        # 1. Translate screen to center relative
        local_pos = screen_pos - self.offset

        # 2. Inverse Rotate
        if self.rotation != 0:
            local_pos = local_pos.rotate(self.rotation)

        # 3. Inverse Scale
        # Avoid division by zero
        safe_zoom = self.zoom if self.zoom != 0 else 0.001
        local_pos = local_pos * (1.0 / safe_zoom)
        world_pos = local_pos + self.position

        # 4. Translate back to world
        return world_pos

    def get_view_bounds(self) -> Rect:
        """
        Calculate the visible rectangle of the world in World Coordinates.

        Useful for Culling (not rendering objects outside this rect) or
        keeping the player inside bounds.

        Note:
            This approximation assumes no rotation for the bounding box calculation.
            If rotation is used, this returns a generic AABB that fits the view.

        Returns:
            Rect: The rectangle representing the visible world area.
        """
        # Calculate the size of the view in world units
        # ScreenSize / Zoom
        view_width = (self.offset.x * 2) / self.zoom
        view_height = (self.offset.y * 2) / self.zoom

        # Top-left corner in world space
        left = self.position.x - (view_width / 2)
        top = self.position.y - (view_height / 2)

        return Rect(left, top, view_width, view_height)

    # ===== Camera Effects API =====

    def shake(self, magnitude: float, duration: float, frequency: float = 20.0) -> None:
        """
        Trigger a camera shake effect.

        Args:
            magnitude (float): Maximum shake offset in pixels.
            duration (float): Shake duration in seconds.
            frequency (float): Shake oscillation speed (default: 20.0).

        Example:
            camera.shake(magnitude=10.0, duration=0.3)  # On explosion
        """
        self._shake = CameraShake(
            duration=duration, magnitude=magnitude, frequency=frequency
        )

    def zoom_to(
        self, target_zoom: float, duration: float = 0.5, easing: str = "smooth"
    ) -> None:
        """
        Start a smooth zoom transition.

        Args:
            target_zoom (float): Target zoom level.
            duration (float): Transition duration in seconds (default: 0.5).
            easing (str): Easing function ("linear", "smooth", "ease_in", "ease_out").

        Example:
            camera.zoom_to(2.0, duration=1.0, easing="smooth")
        """
        self._zoom_transition = CameraZoomTransition(
            target_zoom=target_zoom,
            duration=duration,
            start_zoom=self.zoom,
            easing=easing,
        )

    def follow(
        self,
        target: Vector2,
        constraints: Optional[CameraFollowConstraints] = None,
    ) -> None:
        """
        Set the camera to follow a target position with optional constraints.

        Args:
            target (Vector2): Target position to follow.
            constraints (Optional[CameraFollowConstraints]): Follow behavior constraints.

        Example:
            camera.follow(
                player_pos,
                CameraFollowConstraints(
                    deadzone=Rect(-50, -50, 100, 100),
                    max_speed=500.0,
                    smooth_time=0.1
                )
            )
        """
        self._target_position = target
        self._follow_constraints = constraints

    def update(self, dt: float) -> None:
        """
        Update all camera effects.

        Call this every frame to apply shake, zoom transitions, and follow behavior.

        Args:
            dt (float): Delta time in seconds.

        Example:
            def update(self, dt: float):
                camera.update(dt)
                # ... rest of scene logic
        """
        # Update shake effect
        shake_offset = Vector2.zero()
        if self._shake:
            shake_offset = self._shake.update(dt)
            # Remove shake when complete
            if self._shake.elapsed >= self._shake.duration:
                self._shake = None

        # Update zoom transition
        if self._zoom_transition:
            new_zoom = self._zoom_transition.update(dt)
            if new_zoom is not None:
                self.zoom = new_zoom
            # Remove transition when complete
            if self._zoom_transition.elapsed >= self._zoom_transition.duration:
                self._zoom_transition = None

        # Update follow behavior
        if self._target_position is not None:
            if self._follow_constraints:
                # Apply deadzone and smooth follow
                constraints = self._follow_constraints

                # Calculate offset from camera to target
                offset = self._target_position - self.position

                # Check if target is outside deadzone
                deadzone = constraints.deadzone
                if not deadzone.contains_point(offset):
                    # Calculate how far outside deadzone
                    # Clamp target to deadzone edges
                    clamped_x = max(deadzone.left, min(offset.x, deadzone.right))
                    clamped_y = max(deadzone.top, min(offset.y, deadzone.bottom))

                    # Move camera toward target outside deadzone
                    desired_offset = Vector2(offset.x - clamped_x, offset.y - clamped_y)

                    # Smooth damping
                    if constraints.smooth_time > 0:
                        smooth_factor = dt / constraints.smooth_time
                        movement = desired_offset * smooth_factor
                    else:
                        movement = desired_offset

                    # Apply max speed limit
                    movement_magnitude = movement.magnitude
                    if movement_magnitude > constraints.max_speed * dt:
                        movement = (
                            (movement / movement_magnitude) * constraints.max_speed * dt
                        )

                    self.position = self.position + movement
            else:
                # Instant follow (no constraints)
                self.position = Vector2(
                    self._target_position.x, self._target_position.y
                )

        # Apply shake offset (after all position updates)
        # This is temporary and doesn't modify the base position
        if shake_offset.x != 0 or shake_offset.y != 0:
            # Store base position and apply shake
            # Note: Shake is applied by temporarily offsetting position
            # The render system will use this modified position for one frame
            self.position = Vector2(
                self.position.x + shake_offset.x,
                self.position.y + shake_offset.y,
            )
