"""
Defines the Camera component for 2D coordinate transformations.

This module provides the `Camera2D` class, which is responsible for converting
coordinates between World Space (game logic) and Screen Space (pixels).
It serves as a data container used by the RenderPipeline, decoupling the math
of "viewing" from the logic of "drawing".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2

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
        rng (RandomStream): Random stream driving the shake angle. Defaults
            to a fresh, unseeded stream per shake instance.
    """

    duration: float
    magnitude: float
    frequency: float = 20.0
    elapsed: float = 0.0
    rng: RandomStream = field(default_factory=RandomStream)

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
        angle = self.rng.uniform(0, 360)
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

    def update(self, dt: float) -> float | None:
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
        lookahead (float): Seconds of the target's own velocity to lead by.
            The camera derives that velocity from how far the followed point
            moved since the last frame -- the caller does not have to hand
            it over -- and smooths it with `smooth_time`, because a raw
            per-frame delta is noisy enough to make the view jitter. 0
            disables lookahead; 0.2-0.4 is the usual range for a runner,
            where the point is to show more of what the player is about to
            hit than of what they have already passed.
    """

    deadzone: Rect
    max_speed: float = float("inf")
    smooth_time: float = 0.1
    lookahead: float = 0.0


@dataclass
class CameraFraming:
    """A request to keep several points on screen at once.

    The co-op camera: two players walking apart zoom the view out until both
    fit, and walking back together zooms it in again.

    Attributes:
        targets: The world points to keep in view. At least one.
        padding: World-space margin kept around the targets' bounding box, so
            a player at the edge is not clipped by their own sprite.
        min_zoom: Floor for the computed zoom -- how far out the camera is
            willing to go before it gives up and lets someone off screen.
        max_zoom: Ceiling, so a single target (a zero-size box) does not
            zoom to infinity.
        smooth_time: Seconds of exponential smoothing on both position and
            zoom. 0 snaps.
        adjust_zoom: When False the camera only centres the targets and
            leaves zoom alone, for a game that wants a fixed scale.
    """

    targets: list[Vector2]
    padding: float = 0.0
    min_zoom: float = 0.1
    max_zoom: float = 4.0
    smooth_time: float = 0.0
    adjust_zoom: bool = True


class Camera2D:
    """
    A 2D Camera component that defines the viewable area of the game world.

    It handles Zoom and Panning math. It does NOT render anything; it simply
    provides the transformation the renderer applies.

    There is one world-to-screen transform: ``screen * = world * zoom +
    screen_offset(viewport)``. ``world_to_screen`` / ``screen_to_world`` /
    ``get_view_bounds`` are conveniences built on that same
    ``screen_offset``, so the picture on screen and any hit-testing against
    it cannot disagree. Rotation is deliberately not supported -- the render
    path never rotated, so a ``rotation`` attribute would have been a silent
    no-op (see issue #23).

    Attributes:
        position (Vector2): The center of the camera in World Coordinates.
        zoom (float): The scale factor (1.0 = 100%, 2.0 = 200%).
    """

    def __init__(self, width: int, height: int):
        """
        Initialize the Camera with a default viewport size.

        Args:
            width (int): Width of the target viewport/screen, used as the
                fallback viewport for ``world_to_screen`` and friends when no
                explicit viewport is passed.
            height (int): Height of the target viewport/screen.
        """
        self.position: Vector2 = Vector2.zero()
        self._default_viewport: Rect = Rect(0, 0, width, height)
        self._zoom: float = 1.0

        # Camera effects
        self._shake: CameraShake | None = None
        self._zoom_transition: CameraZoomTransition | None = None
        self._target_position: Vector2 | None = None
        self._follow_constraints: CameraFollowConstraints | None = None
        self._follow_velocity: Vector2 = Vector2.zero()

        # This frame's shake displacement, recomputed by `update()` and read
        # through `view_position`. Separate from `position` because shake
        # used to be *added into* it: the offset oscillates around zero but
        # never subtracted what it added last frame, so every shake left the
        # camera permanently somewhere else -- a random walk across a scene
        # with explosions in it.
        self._shake_offset: Vector2 = Vector2.zero()

        # Framing: the level box the view may not leave, and the multi-target
        # framing request, if any.
        self._bounds: Rect | None = None
        self._framing: CameraFraming | None = None

        # Derived target velocity, for `CameraFollowConstraints.lookahead`.
        self._follow_last_target: Vector2 | None = None
        self._follow_target_velocity: Vector2 = Vector2.zero()

    @property
    def view_position(self) -> Vector2:
        """Where the camera actually looks this frame.

        `position` plus the current shake displacement. Every transform --
        `screen_offset`, and `get_view_bounds` through it -- is expressed
        against this, not against `position`, so a shake moves the picture
        without moving the camera: `position` stays the value `follow()`,
        `frame_targets()` or the game last set, and bounds clamping has a
        stable thing to clamp.
        """
        return self.position + self._shake_offset

    @property
    def bounds(self) -> Rect | None:
        """The world box the view is kept inside, or None for unbounded."""
        return self._bounds

    @property
    def zoom(self) -> float:
        """The scale factor: 1.0 is natural size, 2.0 twice as large."""
        return self._zoom

    @zoom.setter
    def zoom(self, value: float) -> None:
        """Set the scale factor.

        Args:
            value: The new scale factor. Must be positive.

        Raises:
            ValueError: If `value` is zero or negative. A zero used to be
                accepted and then handled three different ways: world_to_screen
                collapsed every point onto the screen centre, screen_to_world
                substituted 0.001 and returned coordinates six orders of
                magnitude out, and get_view_bounds raised ZeroDivisionError. A
                negative silently mirrored the world. Rejecting it here means
                the invariant holds everywhere downstream.
        """
        if value <= 0:
            raise ValueError(
                f"Camera zoom must be positive, got {value}. Zoom is a scale "
                f"factor; use a small positive value to zoom out."
            )
        self._zoom = value

    def set_viewport_size(self, width: int, height: int) -> None:
        """
        Update the fallback viewport used when no explicit one is passed.

        Call this when the window is resized. Render-path callers pass the
        real viewport to ``screen_offset`` directly and are unaffected.

        Args:
            width (int): New width in pixels.
            height (int): New height in pixels.
        """
        self._default_viewport = Rect(0, 0, width, height)

    def screen_offset(self, viewport: Rect) -> Vector2:
        """Compute the translation mapping a zoomed world point into a viewport.

        Screen position is `world * zoom + offset`, so a caller batching many
        points computes this once and adds it per point.

        `viewport.center_vec` is `(centerx, centery)` and already absolute --
        it carries the viewport's origin. Adding `viewport.position` on top of
        it double-counts that origin, which is what the batcher used to do;
        a fullscreen viewport hid it because its origin is (0, 0).

        This is the single world-to-screen definition. `world_to_screen`,
        `screen_to_world` and `get_view_bounds` are all expressed in terms of
        it, and the batcher / particle system / light pass call it directly.

        Args:
            viewport: The region being drawn into.

        Returns:
            The offset to add to every zoomed world position.
        """
        return viewport.center_vec - (self.view_position * self.zoom)

    def world_to_screen(
        self, world_pos: Vector2, viewport: Rect | None = None
    ) -> Vector2:
        """
        Transform a point from World Space to Screen Space.

        Formula: ``world_pos * zoom + screen_offset(viewport)``.

        Args:
            world_pos (Vector2): The coordinate in the game world.
            viewport (Rect | None): The region being drawn into. Defaults to
                the camera's fallback viewport (its constructed size at the
                window origin) -- correct for a fullscreen view; pass the real
                viewport for a letterboxed or split-screen one.

        Returns:
            Vector2: The pixel coordinate on the screen.
        """
        vp = viewport if viewport is not None else self._default_viewport
        return world_pos * self.zoom + self.screen_offset(vp)

    def screen_to_world(
        self, screen_pos: Vector2, viewport: Rect | None = None
    ) -> Vector2:
        """
        Transform a point from Screen Space (e.g., Mouse) to World Space.

        The exact inverse of `world_to_screen`:
        ``(screen_pos - screen_offset(viewport)) / zoom``.

        Args:
            screen_pos (Vector2): The pixel coordinate (e.g. the mouse position).
            viewport (Rect | None): See `world_to_screen`.

        Returns:
            Vector2: The coordinate in the game world.
        """
        vp = viewport if viewport is not None else self._default_viewport
        # No zero guard needed: the zoom setter rejects non-positive values.
        return (screen_pos - self.screen_offset(vp)) * (1.0 / self.zoom)

    def get_view_bounds(self, viewport: Rect | None = None) -> Rect:
        """
        Calculate the visible rectangle of the world in World Coordinates.

        Useful for Culling (not rendering objects outside this rect) or
        keeping the player inside bounds.

        Args:
            viewport (Rect | None): See `world_to_screen`.

        Returns:
            Rect: The rectangle representing the visible world area.
        """
        vp = viewport if viewport is not None else self._default_viewport
        view_width = vp.width / self.zoom
        view_height = vp.height / self.zoom

        left = self.view_position.x - (view_width / 2)
        top = self.view_position.y - (view_height / 2)

        return Rect(int(left), int(top), int(view_width), int(view_height))

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
            target_zoom (float): Target zoom level. Must be positive.
            duration (float): Transition duration in seconds (default: 0.5).
            easing (str): Easing function ("linear", "smooth", "ease_in", "ease_out").

        Raises:
            ValueError: If `target_zoom` is not positive. Checked here rather
                than only when the transition lands, so the bad value is
                reported at the call that supplied it.

        Example:
            camera.zoom_to(2.0, duration=1.0, easing="smooth")
        """
        if target_zoom <= 0:
            raise ValueError(
                f"Camera zoom must be positive, got {target_zoom}. Zoom is a "
                f"scale factor; use a small positive value to zoom out."
            )
        self._zoom_transition = CameraZoomTransition(
            target_zoom=target_zoom,
            duration=duration,
            start_zoom=self.zoom,
            easing=easing,
        )

    def follow(
        self,
        target: Vector2,
        constraints: CameraFollowConstraints | None = None,
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
        # Framing decides `position` too; see `frame_targets()`.
        self._framing = None

    def set_bounds(self, bounds: Rect | None) -> None:
        """Keep the view inside a world box -- "do not show past the wall".

        Clamped in `update()`, against `position` rather than the shaken
        view, so a shake still reads as a shake at the edge of a room.

        When the view is *larger* than the box on an axis -- a room narrower
        than the screen -- the camera centres on the box instead of picking
        one edge, which is the only choice that does not show more wall on
        one side than the other.

        Sized from the camera's fallback viewport, so a split-screen camera
        must declare its real size with `set_viewport_size()` for the clamp
        to be right.

        Args:
            bounds: The world rectangle, or None to go back to unbounded.
        """
        self._bounds = bounds

    def frame_targets(
        self,
        targets: list[Vector2],
        padding: float = 0.0,
        min_zoom: float = 0.1,
        max_zoom: float = 4.0,
        smooth_time: float = 0.0,
        adjust_zoom: bool = True,
    ) -> None:
        """Keep several points on screen at once, zooming to fit.

        The co-op camera. Call it every frame with the players' current
        positions; the camera centres their bounding box and picks the zoom
        that fits it, between `min_zoom` and `max_zoom`.

        Framing and `follow()` are mutually exclusive -- both decide
        `position`, so holding both would make the result depend on the
        order of two lines inside `update()`. Starting one cancels the
        other. With `adjust_zoom`, framing also cancels an in-flight
        `zoom_to()`, which it would otherwise overwrite every frame.

        Args:
            targets: World points to keep in view.
            padding: World-space margin around their bounding box.
            min_zoom: How far out the camera will go before letting someone
                off screen.
            max_zoom: Ceiling, so one target does not zoom to infinity.
            smooth_time: Seconds of smoothing on position and zoom; 0 snaps.
            adjust_zoom: False to centre the targets without touching zoom.

        Raises:
            ValueError: If `targets` is empty, or the zoom range is not a
                positive interval.
        """
        if not targets:
            raise ValueError(
                "frame_targets() needs at least one target. Call "
                "stop_framing() to stop framing instead of passing an empty "
                "list, which has no centre to aim at."
            )
        if min_zoom <= 0 or max_zoom <= 0:
            raise ValueError(
                f"Camera zoom must be positive, got min_zoom={min_zoom}, "
                f"max_zoom={max_zoom}."
            )
        if min_zoom > max_zoom:
            raise ValueError(
                f"min_zoom ({min_zoom}) is above max_zoom ({max_zoom}); the "
                f"range would be empty."
            )

        self._target_position = None
        self._follow_constraints = None
        self._follow_last_target = None
        self._follow_target_velocity = Vector2.zero()
        if adjust_zoom:
            self._zoom_transition = None

        self._framing = CameraFraming(
            targets=list(targets),
            padding=padding,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            smooth_time=smooth_time,
            adjust_zoom=adjust_zoom,
        )

    def stop_framing(self) -> None:
        """Stop multi-target framing, leaving position and zoom where they are."""
        self._framing = None

    def _clamp_to_bounds(self) -> None:
        """Pull `position` back inside `bounds`, if any is set."""
        if self._bounds is None:
            return

        viewport = self._default_viewport
        half_width = (viewport.width / self.zoom) / 2.0
        half_height = (viewport.height / self.zoom) / 2.0
        box = self._bounds

        if half_width * 2.0 >= box.width:
            x = float(box.centerx)
        else:
            x = min(max(self.position.x, box.left + half_width), box.right - half_width)

        if half_height * 2.0 >= box.height:
            y = float(box.centery)
        else:
            y = min(
                max(self.position.y, box.top + half_height), box.bottom - half_height
            )

        self.position = Vector2(x, y)

    def _update_framing(self, framing: CameraFraming, dt: float) -> None:
        """Centre the framed targets and, optionally, zoom to fit them.

        Args:
            framing: The active framing request.
            dt: Delta time in seconds.
        """
        xs = [target.x for target in framing.targets]
        ys = [target.y for target in framing.targets]
        desired_position = Vector2((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

        blend = (
            1.0 if framing.smooth_time <= 0.0 else min(1.0, dt / framing.smooth_time)
        )
        self.position = self.position + (desired_position - self.position) * blend

        if not framing.adjust_zoom:
            return

        viewport = self._default_viewport
        span_x = (max(xs) - min(xs)) + framing.padding * 2.0
        span_y = (max(ys) - min(ys)) + framing.padding * 2.0

        # A single target with no padding spans nothing; that is a request to
        # zoom in as far as allowed, not to divide by zero.
        fit_x = framing.max_zoom if span_x <= 0.0 else viewport.width / span_x
        fit_y = framing.max_zoom if span_y <= 0.0 else viewport.height / span_y
        desired_zoom = min(framing.max_zoom, max(framing.min_zoom, min(fit_x, fit_y)))

        self.zoom = self._zoom + (desired_zoom - self._zoom) * blend

    def _lead_target(
        self, target: Vector2, constraints: CameraFollowConstraints | None, dt: float
    ) -> Vector2:
        """Offset a followed point by the velocity it is moving at.

        The camera measures that velocity itself, from the movement of the
        point it was given last frame, so a caller already passing
        `player.transform.position` every frame needs to pass nothing more.
        It is smoothed with the follow's own `smooth_time`, because the raw
        per-frame delta of a physics body is noisy enough to visibly jitter
        the view.

        Args:
            target: The point being followed.
            constraints: The follow constraints, or None.
            dt: Delta time in seconds.

        Returns:
            The point the camera should actually aim at.
        """
        previous = self._follow_last_target
        self._follow_last_target = Vector2(target.x, target.y)

        if constraints is None or constraints.lookahead == 0.0:
            self._follow_target_velocity = Vector2.zero()
            return target

        raw = (
            (target - previous) * (1.0 / dt)
            if previous is not None and dt > 0.0
            else Vector2.zero()
        )
        blend = (
            1.0
            if constraints.smooth_time <= 0.0
            else min(1.0, dt / constraints.smooth_time)
        )
        self._follow_target_velocity = (
            self._follow_target_velocity + (raw - self._follow_target_velocity) * blend
        )
        return target + self._follow_target_velocity * constraints.lookahead

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

        # Update multi-target framing
        if self._framing is not None:
            self._update_framing(self._framing, dt)

        # Update follow behavior
        if self._target_position is not None:
            aim = self._lead_target(self._target_position, self._follow_constraints, dt)
            if self._follow_constraints:
                # Apply deadzone and smooth follow
                constraints = self._follow_constraints

                # Calculate offset from camera to target
                offset = aim - self.position

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
                self.position = Vector2(aim.x, aim.y)

        # Clamp before the shake, not after: `position` is the camera, and
        # shake is a displacement of the picture. Suppressing it at a wall
        # would make an explosion next to one look like a stutter, which is
        # more visually wrong than a few pixels of overscan.
        self._clamp_to_bounds()

        # Recorded, not added into `position`. See `view_position`.
        self._shake_offset = shake_offset
