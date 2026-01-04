"""Animation Logic Component."""

from dataclasses import dataclass
from typing import List, Dict, Optional
from pyguara.resources.types import Texture
from pyguara.graphics.components.sprite import Sprite


@dataclass
class AnimationClip:
    """Data for a single animation state (e.g., 'walk_down')."""

    name: str
    frames: List[Texture]
    frame_rate: float = 10.0  # Frames per second
    loop: bool = True


class Animator:
    """
    Component that manages playback of AnimationClips.

    It 'drives' a Sprite component. Every frame, it calculates which texture
    frame should be visible and assigns it to the Sprite.
    """

    def __init__(self, sprite: Sprite) -> None:
        """Initialize the animator with a target sprite.

        Args:
            sprite: The sprite component that this animator will update.
        """
        self._sprite = sprite
        self._clips: Dict[str, AnimationClip] = {}

        self._current_clip: Optional[AnimationClip] = None
        self._current_time: float = 0.0
        self._current_frame_index: int = 0
        self._playing: bool = False

    def add_clip(self, clip: AnimationClip) -> None:
        """Register a new animation state."""
        self._clips[clip.name] = clip

    def play(self, name: str, force_reset: bool = False) -> None:
        """
        Start playing an animation.

        Args:
            name (str): The name of the clip (e.g., 'run').
            force_reset (bool): If True, restarts animation even if already playing it.
        """
        if name not in self._clips:
            print(f"[Animator] Warning: Clip '{name}' not found.")
            return

        # Optimization: Don't restart if we are already playing this clip
        if self._current_clip and self._current_clip.name == name and not force_reset:
            return

        self._current_clip = self._clips[name]
        self._current_time = 0.0
        self._current_frame_index = 0
        self._playing = True

        # Apply first frame immediately
        self._apply_frame()

    def update(self, dt: float) -> None:
        """Advance the animation timer."""
        if not self._playing or not self._current_clip:
            return

        self._current_time += dt

        # Calculate duration of a single frame
        seconds_per_frame = 1.0 / self._current_clip.frame_rate

        if self._current_time >= seconds_per_frame:
            # Move to next frame
            self._current_time -= seconds_per_frame
            self._current_frame_index += 1

            # Handle Looping
            total_frames = len(self._current_clip.frames)

            if self._current_frame_index >= total_frames:
                if self._current_clip.loop:
                    self._current_frame_index = 0
                else:
                    self._current_frame_index = total_frames - 1
                    self._playing = False  # Stop at end

            self._apply_frame()

    def _apply_frame(self) -> None:
        """Update the visual Sprite component with the current texture."""
        # FIX: Check for None to satisfy Mypy
        if self._current_clip is None:
            return

        frame = self._current_clip.frames[self._current_frame_index]
        self._sprite.texture = frame
