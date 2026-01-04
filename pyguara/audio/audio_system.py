"""Core interfaces for the Audio Subsystem."""

from typing import Protocol
from pyguara.resources.types import AudioClip


class IAudioSystem(Protocol):
    """
    The main contract for playing audio in the engine.

    Abstracts away the concept of 'Channels' and 'Streams'.
    """

    def play_sfx(self, clip: AudioClip, volume: float = 1.0) -> None:
        """
        Play a sound effect "fire and forget".

        Args:
            clip (AudioClip): The resource loaded via ResourceManager.
            volume (float): Playback volume (multiplied by master volume).
        """
        ...

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """
        Stream background music from disk (does not use AudioClip resources usually).

        Args:
            path (str): File path to the music file.
            loop (bool): Whether to restart when finished.
            fade_ms (int): Fade-in duration in milliseconds.
        """
        ...

    def stop_music(self, fade_ms: int = 1000) -> None:
        """Stop the currently playing music."""
        ...

    def set_master_volume(self, volume: float) -> None:
        """Set the global volume (0.0 to 1.0)."""
        ...
