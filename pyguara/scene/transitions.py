"""Scene transition effects system.

This module provides visual transition effects when switching between scenes,
including fade, slide, wipe, and zoom effects with customizable easing.

Example:
    >>> from pyguara.scene.transitions import FadeTransition, TransitionManager
    >>>
    >>> transition_manager = TransitionManager()
    >>> fade = FadeTransition(duration=0.5)
    >>> transition_manager.start_transition(fade, from_scene, to_scene, on_complete)
    >>> # In update loop:
    >>> transition_manager.update(dt)
    >>> # In render:
    >>> transition_manager.render(renderer, ui_renderer)
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from pyguara.common.types import Color, Rect
from pyguara.graphics.protocols import IRenderer, UIRenderer

if TYPE_CHECKING:
    from pyguara.scene.base import Scene


class TransitionState(Enum):
    """State of transition progression."""

    IDLE = auto()
    TRANSITIONING_OUT = auto()  # Old scene fading out
    TRANSITIONING_IN = auto()  # New scene fading in
    COMPLETE = auto()


class EasingFunction(Enum):
    """Easing functions for smooth transitions."""

    LINEAR = auto()
    EASE_IN = auto()
    EASE_OUT = auto()
    EASE_IN_OUT = auto()
    EASE_IN_QUAD = auto()
    EASE_OUT_QUAD = auto()
    EASE_IN_OUT_QUAD = auto()


def apply_easing(t: float, easing: EasingFunction) -> float:
    """Apply easing function to normalized time value.

    Args:
        t: Time value between 0.0 and 1.0
        easing: Easing function to apply

    Returns:
        Eased time value between 0.0 and 1.0
    """
    t = max(0.0, min(1.0, t))  # Clamp to [0, 1]

    if easing == EasingFunction.LINEAR:
        return t
    elif easing == EasingFunction.EASE_IN:
        return t * t
    elif easing == EasingFunction.EASE_OUT:
        return t * (2.0 - t)
    elif easing == EasingFunction.EASE_IN_OUT:
        return t * t * (3.0 - 2.0 * t)
    elif easing == EasingFunction.EASE_IN_QUAD:
        return t * t
    elif easing == EasingFunction.EASE_OUT_QUAD:
        return 1.0 - (1.0 - t) * (1.0 - t)
    elif easing == EasingFunction.EASE_IN_OUT_QUAD:
        if t < 0.5:
            return 2.0 * t * t
        return 1.0 - 2.0 * (1.0 - t) * (1.0 - t)

    return t  # type: ignore[unreachable]  # Fallback for future easing functions


@dataclass
class TransitionConfig:
    """Configuration for a scene transition.

    Attributes:
        duration: Total transition duration in seconds
        easing: Easing function for smooth animation
        color: Color used for transition effects
        two_phase: If True, transition out then in; if False, simultaneous
    """

    duration: float = 0.5
    easing: EasingFunction = EasingFunction.EASE_IN_OUT
    color: Color = field(default_factory=lambda: Color(0, 0, 0, 255))
    two_phase: bool = True


class Transition(ABC):
    """Base class for scene transition effects.

    Subclasses implement specific visual effects like fade, slide, wipe, etc.
    """

    def __init__(self, config: TransitionConfig | None = None):
        """Initialize transition.

        Args:
            config: Transition configuration, uses defaults if None
        """
        self.config = config or TransitionConfig()
        self.progress = 0.0  # 0.0 to 1.0
        self.state = TransitionState.IDLE

    def start(self) -> None:
        """Start the transition."""
        self.progress = 0.0
        self.state = TransitionState.TRANSITIONING_OUT

    def update(self, dt: float) -> bool:
        """Update transition progress.

        Args:
            dt: Delta time in seconds

        Returns:
            True if transition is complete, False otherwise
        """
        if self.state == TransitionState.IDLE or self.state == TransitionState.COMPLETE:
            return self.state == TransitionState.COMPLETE

        # Update progress
        self.progress += dt / self.config.duration
        self.progress = min(self.progress, 1.0)

        # Handle two-phase transitions
        if self.config.two_phase:
            # Check phase transition at midpoint (>= 0.5)
            if self.state == TransitionState.TRANSITIONING_OUT and self.progress >= 0.5:
                self.state = TransitionState.TRANSITIONING_IN
            # Check completion separately (not elif) to handle same-frame transition+complete
            if self.progress >= 1.0:
                self.state = TransitionState.COMPLETE
                return True
        else:
            if self.progress >= 1.0:
                self.state = TransitionState.COMPLETE
                return True

        return False

    def get_eased_progress(self) -> float:
        """Get progress with easing applied.

        Returns:
            Eased progress value between 0.0 and 1.0
        """
        if self.config.two_phase:
            # Split into two phases
            if self.state == TransitionState.TRANSITIONING_OUT:
                # First half: 0.0 to 0.5 maps to 0.0 to 1.0
                t = self.progress * 2.0
            else:
                # Second half: 0.5 to 1.0 maps to 1.0 to 0.0
                t = 1.0 - (self.progress - 0.5) * 2.0
        else:
            t = self.progress

        return apply_easing(t, self.config.easing)

    @abstractmethod
    def render(
        self,
        world_renderer: IRenderer,
        ui_renderer: UIRenderer,
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Render the transition effect.

        Args:
            world_renderer: World rendering interface
            ui_renderer: UI rendering interface
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
        """
        pass


class FadeTransition(Transition):
    """Fade to black/color transition effect."""

    def render(
        self,
        world_renderer: IRenderer,
        ui_renderer: UIRenderer,
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Render fade overlay."""
        alpha = int(self.get_eased_progress() * 255)
        overlay_color = Color(
            self.config.color.r,
            self.config.color.g,
            self.config.color.b,
            alpha,
        )

        # Draw full-screen overlay
        screen_rect = Rect(0, 0, screen_width, screen_height)
        ui_renderer.draw_rect(screen_rect, overlay_color, width=0)


class SlideTransition(Transition):
    """Slide transition effect.

    Slides the new scene in from a specific direction.
    """

    def __init__(
        self,
        config: TransitionConfig | None = None,
        direction: str = "left",
    ):
        """Initialize slide transition.

        Args:
            config: Transition configuration
            direction: Slide direction: "left", "right", "up", "down"
        """
        super().__init__(config)
        self.direction = direction

    def render(
        self,
        world_renderer: IRenderer,
        ui_renderer: UIRenderer,
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Render slide effect with black bars."""
        progress = self.get_eased_progress()

        # Draw black bars to cover the sliding area
        if self.direction == "left":
            # Slide from right to left
            x_offset = int(screen_width * (1.0 - progress))
            cover_rect = Rect(0, 0, x_offset, screen_height)
        elif self.direction == "right":
            # Slide from left to right
            x_offset = int(screen_width * progress)
            cover_rect = Rect(x_offset, 0, screen_width - x_offset, screen_height)
        elif self.direction == "up":
            # Slide from bottom to top
            y_offset = int(screen_height * (1.0 - progress))
            cover_rect = Rect(0, 0, screen_width, y_offset)
        else:  # down
            # Slide from top to bottom
            y_offset = int(screen_height * progress)
            cover_rect = Rect(0, y_offset, screen_width, screen_height - y_offset)

        ui_renderer.draw_rect(cover_rect, self.config.color, width=0)


class WipeTransition(Transition):
    """Wipe transition effect.

    A wipe that reveals the new scene from one edge.
    """

    def __init__(
        self,
        config: TransitionConfig | None = None,
        direction: str = "left_to_right",
    ):
        """Initialize wipe transition.

        Args:
            config: Transition configuration
            direction: Wipe direction: "left_to_right", "right_to_left",
                      "top_to_bottom", "bottom_to_top"
        """
        super().__init__(config)
        self.direction = direction

    def render(
        self,
        world_renderer: IRenderer,
        ui_renderer: UIRenderer,
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Render wipe effect."""
        progress = self.get_eased_progress()

        if self.direction == "left_to_right":
            width = int(screen_width * progress)
            wipe_rect = Rect(0, 0, width, screen_height)
        elif self.direction == "right_to_left":
            width = int(screen_width * progress)
            wipe_rect = Rect(screen_width - width, 0, width, screen_height)
        elif self.direction == "top_to_bottom":
            height = int(screen_height * progress)
            wipe_rect = Rect(0, 0, screen_width, height)
        else:  # bottom_to_top
            height = int(screen_height * progress)
            wipe_rect = Rect(0, screen_height - height, screen_width, height)

        ui_renderer.draw_rect(wipe_rect, self.config.color, width=0)


DEFAULT_WIPE_SEGMENTS = 64
"""Sides in the polygon approximating a circular wipe's edge.

At 64 the error against a true circle is sub-pixel at any window size the
engine is likely to see: the worst case is the sagitta of one chord,
`r * (1 - cos(pi / 64))`, which is 0.9 px at the 735 px radius a 1280x720
window needs. Doubling it halves that and doubles nothing that matters --
the cost is one polygon either way -- but 64 is already below what a
viewer can see on a moving edge.
"""


def fully_revealed_radius(
    screen_width: int,
    screen_height: int,
    segments: int = DEFAULT_WIPE_SEGMENTS,
) -> float:
    """Return the radius at which a wipe's cover vanishes entirely.

    Not the half-diagonal, which is the intuitive answer and leaves a
    visible artefact. An inscribed polygon touches the circle at its
    *vertices* and falls inside it everywhere else, so a 64-gon of radius
    exactly the half-diagonal still cuts the corners off: measured, 2131 of
    a 1280x720 window's pixels stayed covered at what should have been full
    reveal -- four dark slivers, at the one moment the effect is supposed to
    be invisible. Scaling by `1 / cos(pi / segments)` puts the polygon's
    *edges* through the corners instead.

    Args:
        screen_width: Window width in pixels.
        screen_height: Window height in pixels.
        segments: Sides in the approximating polygon.

    Returns:
        The radius, in pixels, at which nothing is covered.
    """
    half_diagonal = math.hypot(screen_width / 2.0, screen_height / 2.0)
    return half_diagonal / math.cos(math.pi / max(segments, 3))


def circular_cover_points(
    center_x: float,
    center_y: float,
    radius: float,
    screen_width: int,
    screen_height: int,
    segments: int = DEFAULT_WIPE_SEGMENTS,
) -> list[tuple[int, int]]:
    """Return one polygon covering the screen *except* a circular hole.

    The shape a circular wipe needs is an annulus -- everything outside the
    revealed circle -- and a polygon with a hole in it is not something
    `UIRenderer.draw_polygon` can express directly. It is expressed as a
    single self-touching outline instead: round the window rectangle, in
    along a seam to the circle, round the circle **in the opposite
    winding**, and back out along the same seam. A scanline fill counts two
    crossings to reach the hole and leaves it empty, and the two coincident
    seam edges cancel, so no scar is left behind.

    The alternative decompositions were both measured and both lose. A fan
    of 68 quads between the arc and the window edge costs 1.04 ms at
    1280x720, but adjacent quads share an edge and `pygame.draw.polygon`
    fills boundary pixels, so a translucent cover is blended **twice**
    along every seam -- visibly, as a spoke pattern: a 50%-black cover over
    green measured (0, 50, 0) on the seams against (0, 100, 0) everywhere
    else. Non-overlapping scanline rects, two per row, have no seam but
    cost 1440 draw calls and 2.62 ms opaque or 5.89 ms translucent. This is
    one call, 0.3 ms, and measures exactly two distinct colours over a
    translucent cover at every radius.

    Both real `UIRenderer` implementations rasterise polygons with
    `pygame.draw.polygon` -- the ModernGL one draws widgets onto an
    offscreen pygame surface and uploads the result -- so the fill rule
    this relies on is the same one on both backends.

    Args:
        center_x: Centre of the revealed circle, in pixels.
        center_y: Centre of the revealed circle, in pixels.
        radius: Radius of the revealed circle. Clamped at both ends: at or
            below zero the whole window is covered, and at or above
            `fully_revealed_radius` nothing is.
        screen_width: Window width in pixels.
        screen_height: Window height in pixels.
        segments: Sides in the approximating polygon.

    Returns:
        Points for a single `draw_polygon` call, or an empty list when
        there is nothing to cover -- which the caller must treat as "draw
        nothing" rather than passing on, since a polygon of no points is
        not a thing to ask a backend for.
    """
    sides = max(segments, 3)
    if radius >= fully_revealed_radius(screen_width, screen_height, sides):
        return []

    if radius <= 0.0:
        # No hole to cut, so no seam either. The plain rectangle is both
        # cheaper and immune to whatever a zero-radius ring would do.
        return [
            (0, 0),
            (screen_width, 0),
            (screen_width, screen_height),
            (0, screen_height),
        ]

    # The outer loop is the window *inflated to contain the circle*, not
    # the window itself. For most of a wipe the circle is larger than the
    # window -- at 1280x720 it starts at radius 735 against a half-height
    # of 360 -- so it crosses the window's edges, and the cover stops
    # being an annulus: it becomes two regions, or four. A scanline fill
    # mostly copes, but not at the rows where the window edge and the
    # circle meet, where it left a 42-pixel band of cover colour across
    # the top of the revealed scene. Keeping the circle strictly inside
    # the outer loop keeps the topology a ring at every radius, and the
    # backend clips the overhang for free.
    left = min(0.0, center_x - radius) - 1.0
    top = min(0.0, center_y - radius) - 1.0
    right = max(float(screen_width), center_x + radius) + 1.0
    bottom = max(float(screen_height), center_y + radius) + 1.0
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]

    ring = [
        (
            center_x + math.cos(2.0 * math.pi * i / sides) * radius,
            center_y + math.sin(2.0 * math.pi * i / sides) * radius,
        )
        for i in range(sides)
    ]
    # Reversed, so the hole winds against the rectangle around it.
    ring.reverse()

    # Rotated so the ring begins at its leftmost vertex, which is where
    # the seam meets it. Without this the ring began wherever the
    # construction happened to put vertex zero -- the *right* of the
    # circle -- and the seam ran from the window's left edge straight
    # across the hole to reach it. Its two traversals coincide and ought
    # to cancel, but a scanline fill counts a vertex sitting exactly on a
    # row inconsistently, so what actually appeared was a dotted line of
    # cover colour through the middle of the revealed scene. Every test
    # passed: it is inside the revealed circle, so a distinct-colour check
    # still sees two colours, and it is about 0.3% of the area, under an
    # area assertion's tolerance. It was found by looking at the frame.
    start = min(range(len(ring)), key=lambda i: ring[i][0])
    ring = ring[start:] + ring[:start]

    # The seam runs from the outer loop's left edge to the nearest point
    # on the circle, along the circle's own centre line, so it lies
    # entirely outside the hole. It is traversed twice.
    seam = (left, center_y)
    outline: list[tuple[float, float]] = [seam]
    outline.extend(corners)
    outline.append(seam)
    outline.extend(ring)
    outline.append(ring[0])

    return [(int(round(x)), int(round(y))) for x, y in outline]


class CircularWipeTransition(Transition):
    """An iris wipe: a circular hole that closes on the centre and reopens.

    The scene stays visible inside a circle centred on the window. The
    circle contracts to nothing -- covering the frame from the corners
    inwards -- and then expands again over the new scene, which is the
    "expands a circle from center" half of what this class used to promise.

    It used to promise exactly that and draw a **full-screen fade**, behind
    a `# TODO: Proper circular mask rendering`. Not approximately a fade:
    its output was byte-identical to `FadeTransition`'s at the same
    progress, so the two classes were the same effect under different
    names, and no test covered this one at all.

    The cover is drawn opaque at `config.color`, matching `WipeTransition`
    and `SlideTransition` rather than `FadeTransition` -- a wipe whose
    cover is translucent is a fade with extra steps. A translucent
    `config.color` is still honoured and still correct, because the cover
    is a single polygon rather than a decomposition with seams to
    double-blend; see `circular_cover_points`.

    Attributes:
        segments: Sides in the polygon approximating the circle. See
            `DEFAULT_WIPE_SEGMENTS` for why 64.
    """

    def __init__(
        self,
        config: TransitionConfig | None = None,
        segments: int = DEFAULT_WIPE_SEGMENTS,
    ):
        """Initialize the iris wipe.

        Args:
            config: Transition configuration.
            segments: Sides in the approximating polygon; at least 3.
        """
        super().__init__(config)
        self.segments = max(segments, 3)

    def revealed_radius(self, screen_width: int, screen_height: int) -> float:
        """Return the radius of the still-visible circle, in pixels.

        Separated from `render` so the geometry can be asserted without a
        renderer, and because it is the one number that says what the
        effect is doing at a given moment.

        Args:
            screen_width: Window width in pixels.
            screen_height: Window height in pixels.

        Returns:
            `fully_revealed_radius` at eased progress 0, shrinking to 0 at
            eased progress 1.
        """
        maximum = fully_revealed_radius(screen_width, screen_height, self.segments)
        return (1.0 - self.get_eased_progress()) * maximum

    def render(
        self,
        world_renderer: IRenderer,
        ui_renderer: UIRenderer,
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Cover everything outside the revealed circle."""
        points = circular_cover_points(
            screen_width / 2.0,
            screen_height / 2.0,
            self.revealed_radius(screen_width, screen_height),
            screen_width,
            screen_height,
            self.segments,
        )
        if not points:
            return
        ui_renderer.draw_polygon(points, self.config.color, width=0)


class TransitionManager:
    """Manages scene transitions.

    Handles transition state, rendering, and callbacks.
    """

    def __init__(self) -> None:
        """Initialize transition manager."""
        self.current_transition: Transition | None = None
        self.from_scene: Scene | None = None
        self.to_scene: Scene | None = None
        self.on_complete_callback: Callable[[], None] | None = None
        self._on_from_hidden: Callable[[], None] | None = None
        self._on_to_shown: Callable[[], None] | None = None
        self.screen_width = 800
        self.screen_height = 600
        self._phase_switched = False  # Track if we've switched to IN phase

    def set_screen_size(self, width: int, height: int) -> None:
        """Set screen dimensions for rendering.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
        """
        self.screen_width = width
        self.screen_height = height

    def start_transition(
        self,
        transition: Transition,
        from_scene: Scene | None,
        to_scene: Scene,
        on_complete: Callable[[], None] | None = None,
        on_from_hidden: Callable[[], None] | None = None,
        on_to_shown: Callable[[], None] | None = None,
    ) -> None:
        """Start a scene transition.

        Args:
            transition: Transition effect to use
            from_scene: Current scene (can be None for first scene)
            to_scene: Scene to transition to
            on_complete: Optional callback when transition completes
            on_from_hidden: Optional callback fired the moment render() stops
                showing from_scene -- at the two-phase midpoint, or
                immediately for a single-phase transition.
            on_to_shown: Optional callback fired the moment render() starts
                showing to_scene -- same timing as on_from_hidden.
        """
        self.current_transition = transition
        self.from_scene = from_scene
        self.to_scene = to_scene
        self.on_complete_callback = on_complete
        self._on_from_hidden = on_from_hidden
        self._on_to_shown = on_to_shown
        self._phase_switched = False  # Reset flag for new transition

        transition.start()

        if not transition.config.two_phase:
            # Single-phase: render() shows to_scene from frame one and never
            # shows from_scene at all, so both callbacks fire now rather
            # than at completion -- lifecycle-equivalent to an immediate
            # switch, just with a cosmetic overlay on top.
            if self._on_from_hidden:
                self._on_from_hidden()
            if self._on_to_shown:
                self._on_to_shown()

    def is_transitioning(self) -> bool:
        """Check if a transition is currently active.

        Returns:
            True if transition is in progress
        """
        return (
            self.current_transition is not None
            and self.current_transition.state
            not in (TransitionState.IDLE, TransitionState.COMPLETE)
        )

    def update(self, dt: float) -> None:
        """Update transition progress.

        Args:
            dt: Delta time in seconds
        """
        if not self.current_transition:
            return

        complete = self.current_transition.update(dt)

        # Two-phase: both callbacks fire together at the phase-flip
        # midpoint -- exactly when render() swaps which scene it shows.
        if self.current_transition.config.two_phase:
            if (
                self.current_transition.state == TransitionState.TRANSITIONING_IN
                and not self._phase_switched
            ):
                self._phase_switched = True
                if self._on_from_hidden:
                    self._on_from_hidden()
                if self._on_to_shown:
                    self._on_to_shown()
                if self.to_scene:
                    # Update once to ensure scene is ready
                    self.to_scene.update(0.0)

        if complete:
            # Single-phase already fired both callbacks in start_transition().
            if self.on_complete_callback:
                self.on_complete_callback()

            self.current_transition = None
            self.from_scene = None
            self.to_scene = None
            self.on_complete_callback = None
            self._on_from_hidden = None
            self._on_to_shown = None
            self._phase_switched = False

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render transition effect.

        Args:
            world_renderer: World rendering interface
            ui_renderer: UI rendering interface
        """
        if not self.current_transition:
            return

        # Render appropriate scene(s)
        if self.current_transition.config.two_phase:
            if self.current_transition.state == TransitionState.TRANSITIONING_OUT:
                # Show old scene
                if self.from_scene:
                    self.from_scene.render(world_renderer, ui_renderer)
            else:
                # Show new scene
                if self.to_scene:
                    self.to_scene.render(world_renderer, ui_renderer)
        else:
            # Single-phase: show new scene
            if self.to_scene:
                self.to_scene.render(world_renderer, ui_renderer)

        # Render transition overlay
        self.current_transition.render(
            world_renderer, ui_renderer, self.screen_width, self.screen_height
        )
