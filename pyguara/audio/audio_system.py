"""Core interfaces for the Audio Subsystem."""

from typing import Protocol, Optional
from pyguara.resources.types import AudioClip
from pyguara.common.types import Vector2
from pyguara.audio.types import AudioPriority, AudioBusType


class IAudioSystem(Protocol):
    """
    The main contract for playing audio in the engine.

    Abstracts away the concept of 'Channels' and 'Streams'.

    Features:
    - Basic sound effect and music playback
    - Spatial audio with distance attenuation and stereo panning
    - Audio bus hierarchy for grouped volume control
    - Priority-based channel management
    """

    def play_sfx(
        self,
        clip: AudioClip,
        volume: float = 1.0,
        loops: int = 0,
        priority: AudioPriority = AudioPriority.NORMAL,
        bus: AudioBusType = AudioBusType.SFX,
    ) -> Optional[int]:
        """
        Play a sound effect.

        Args:
            clip: The resource loaded via ResourceManager.
            volume: Playback volume (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).
            priority: Sound priority for channel stealing.
            bus: Audio bus to route the sound through.

        Returns:
            Channel ID if available, None otherwise.
        """
        ...

    def play_sfx_at_position(
        self,
        clip: AudioClip,
        source_pos: Vector2,
        listener_pos: Vector2,
        volume: float = 1.0,
        loops: int = 0,
        priority: AudioPriority = AudioPriority.NORMAL,
        bus: AudioBusType = AudioBusType.SFX,
    ) -> Optional[int]:
        """
        Play a sound effect with spatial positioning.

        Calculates volume attenuation based on distance and stereo panning
        based on relative position to the listener.

        Args:
            clip: The resource loaded via ResourceManager.
            source_pos: World position of the sound source.
            listener_pos: World position of the listener (usually camera).
            volume: Base volume before spatial attenuation (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).
            priority: Sound priority for channel stealing.
            bus: Audio bus to route the sound through.

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

    # ========== Bus Management ==========

    def set_bus_volume(self, bus: AudioBusType, volume: float) -> None:
        """
        Set volume for a specific audio bus.

        Args:
            bus: The bus to adjust.
            volume: Volume level (0.0 to 1.0).
        """
        ...

    def get_bus_volume(self, bus: AudioBusType) -> float:
        """
        Get the volume of a specific audio bus.

        Args:
            bus: The bus to query.

        Returns:
            Current volume level (0.0 to 1.0).
        """
        ...

    def set_bus_muted(self, bus: AudioBusType, muted: bool) -> None:
        """
        Mute or unmute a specific audio bus.

        Args:
            bus: The bus to mute/unmute.
            muted: True to mute, False to unmute.
        """
        ...

    def is_bus_muted(self, bus: AudioBusType) -> bool:
        """
        Check if a bus is muted.

        Args:
            bus: The bus to check.

        Returns:
            True if muted, False otherwise.
        """
        ...

    # ========== Listener Management ==========

    def set_listener_position(self, position: Vector2) -> None:
        """
        Set the listener position for spatial audio.

        All spatial sounds will be calculated relative to this position.

        Args:
            position: World position of the listener.
        """
        ...
