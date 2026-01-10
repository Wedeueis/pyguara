"""Core interfaces for the Audio Subsystem."""

from typing import Protocol, Optional
from pyguara.resources.types import AudioClip


class IAudioSystem(Protocol):
    """
    The main contract for playing audio in the engine.

    Abstracts away the concept of 'Channels' and 'Streams'.
    """

    def play_sfx(
        self, clip: AudioClip, volume: float = 1.0, loops: int = 0
    ) -> Optional[int]:
        """
        Play a sound effect.

        Args:
            clip: The resource loaded via ResourceManager.
            volume: Playback volume (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).

        Returns:
            Channel ID if available, None otherwise.
        """
        ...

    def stop_sfx(self, channel: int) -> None:
        """
        Stop a specific sound effect channel.

        Args:
            channel: The channel ID returned by play_sfx.
        """
        ...

    def pause_sfx(self) -> None:
        """Pause all sound effects."""
        ...

    def resume_sfx(self) -> None:
        """Resume all paused sound effects."""
        ...

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """
        Stream background music from disk.

        Args:
            path: File path to the music file.
            loop: Whether to restart when finished.
            fade_ms: Fade-in duration in milliseconds.
        """
        ...

    def stop_music(self, fade_ms: int = 1000) -> None:
        """
        Stop the currently playing music.

        Args:
            fade_ms: Fade-out duration in milliseconds.
        """
        ...

    def pause_music(self) -> None:
        """Pause the currently playing music."""
        ...

    def resume_music(self) -> None:
        """Resume the paused music."""
        ...

    def is_music_playing(self) -> bool:
        """Check if music is currently playing."""
        ...

    def set_master_volume(self, volume: float) -> None:
        """
        Set the global master volume (0.0 to 1.0).

        Args:
            volume: Master volume level.
        """
        ...

    def set_sfx_volume(self, volume: float) -> None:
        """
        Set the sound effects volume (0.0 to 1.0).

        Args:
            volume: SFX volume level.
        """
        ...

    def set_music_volume(self, volume: float) -> None:
        """
        Set the music volume (0.0 to 1.0).

        Args:
            volume: Music volume level.
        """
        ...

    def get_master_volume(self) -> float:
        """Get the current master volume."""
        ...

    def get_sfx_volume(self) -> float:
        """Get the current SFX volume."""
        ...

    def get_music_volume(self) -> float:
        """Get the current music volume."""
        ...
