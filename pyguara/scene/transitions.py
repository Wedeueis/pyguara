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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, TYPE_CHECKING

from pyguara.common.types import Color, Rect
from pyguara.graphics.protocols import UIRenderer, IRenderer

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

    def __init__(self, config: Optional[TransitionConfig] = None):
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
        config: Optional[TransitionConfig] = None,
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
        config: Optional[TransitionConfig] = None,
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


class CircularWipeTransition(Transition):
    """Circular wipe transition effect.

    Expands a circle from center to reveal/hide the scene.
    """

    def render(
        self,
        world_renderer: IRenderer,
        ui_renderer: UIRenderer,
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Render circular wipe effect."""
        # TODO: Proper circular mask rendering
        # For now, just do a simple fade
        alpha = int(self.get_eased_progress() * 255)
        overlay_color = Color(
            self.config.color.r,
            self.config.color.g,
            self.config.color.b,
            alpha,
        )

        # Draw full screen overlay
        screen_rect = Rect(0, 0, screen_width, screen_height)
        ui_renderer.draw_rect(screen_rect, overlay_color, width=0)


class TransitionManager:
    """Manages scene transitions.

    Handles transition state, rendering, and callbacks.
    """

    def __init__(self) -> None:
        """Initialize transition manager."""
        self.current_transition: Optional[Transition] = None
        self.from_scene: Optional[Scene] = None
        self.to_scene: Optional[Scene] = None
        self.on_complete_callback: Optional[Callable[[], None]] = None
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
        from_scene: Optional[Scene],
        to_scene: Scene,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> None:
        """Start a scene transition.

        Args:
            transition: Transition effect to use
            from_scene: Current scene (can be None for first scene)
            to_scene: Scene to transition to
            on_complete: Optional callback when transition completes
        """
        self.current_transition = transition
        self.from_scene = from_scene
        self.to_scene = to_scene
        self.on_complete_callback = on_complete
        self._phase_switched = False  # Reset flag for new transition

        transition.start()

        # If two-phase, call on_exit on old scene immediately
        if transition.config.two_phase and from_scene:
            from_scene.on_exit()

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

        # Handle phase transitions (only call on_enter once)
        if self.current_transition.config.two_phase:
            if (
                self.current_transition.state == TransitionState.TRANSITIONING_IN
                and not self._phase_switched
                and self.to_scene
            ):
                # Midpoint: switch scenes
                self._phase_switched = True
                self.to_scene.on_enter()
                # Update once to ensure scene is ready
                self.to_scene.update(0.0)

        if complete:
            # Transition finished
            if not self.current_transition.config.two_phase:
                # Single-phase: handle scene change now
                if self.from_scene:
                    self.from_scene.on_exit()
                if self.to_scene:
                    self.to_scene.on_enter()

            if self.on_complete_callback:
                self.on_complete_callback()

            self.current_transition = None
            self.from_scene = None
            self.to_scene = None
            self.on_complete_callback = None
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
