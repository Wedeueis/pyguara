"""Pygame implementation of the Audio System."""

import pygame
from typing import Optional
from pyguara.audio.audio_system import IAudioSystem
from pyguara.resources.types import AudioClip


class PygameAudioSystem(IAudioSystem):
    """Pygame implementation for the PyGuara AudioSystem with full volume control."""

    def __init__(
        self,
        frequency: int = 44100,
        size: int = -16,
        channels: int = 2,
        buffer: int = 512,
    ):
        """
        Initialize the Pygame mixer.

        Args:
            frequency: Sample rate (44100 Hz is CD quality).
            size: Sample size (-16 is 16-bit signed).
            channels: Number of audio channels (2 for stereo).
            buffer: Buffer size (512 is low latency).
        """
        pygame.mixer.init(frequency, size, channels, buffer)
        # Allocate enough channels for simultaneous sounds
        pygame.mixer.set_num_channels(32)

        # Volume tracking
        self._master_volume: float = 1.0
        self._sfx_volume: float = 1.0
        self._music_volume: float = 1.0

        # Apply initial music volume
        pygame.mixer.music.set_volume(self._master_volume * self._music_volume)

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
        try:
            native_sound = clip.native_handle

            # Check if native_sound has the required methods
            if hasattr(native_sound, "set_volume") and hasattr(native_sound, "play"):
                # Apply master and SFX volume
                effective_volume = volume * self._sfx_volume * self._master_volume
                native_sound.set_volume(effective_volume)

                # Play and return channel
                channel = native_sound.play(loops=loops)
                if channel and hasattr(channel, "get_id"):
                    channel_id: int = channel.get_id()
                    return channel_id
                return None
            else:
                print(
                    f"[AudioSystem] Error: Resource {clip.path} is not a valid Sound."
                )
                return None
        except (AttributeError, Exception) as e:
            print(f"[AudioSystem] Error playing sound '{clip.path}': {e}")
            return None

    def stop_sfx(self, channel: int) -> None:
        """
        Stop a specific sound effect channel.

        Args:
            channel: The channel ID returned by play_sfx.
        """
        try:
            pygame.mixer.Channel(channel).stop()
        except pygame.error:
            pass  # Channel may already be stopped

    def pause_sfx(self) -> None:
        """Pause all sound effects."""
        pygame.mixer.pause()

    def resume_sfx(self) -> None:
        """Resume all paused sound effects."""
        pygame.mixer.unpause()

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """
        Stream background music from disk.

        Args:
            path: File path to the music file.
            loop: Whether to restart when finished.
            fade_ms: Fade-in duration in milliseconds.
        """
        try:
            pygame.mixer.music.load(path)
            loops = -1 if loop else 0
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)

            # Ensure music volume is applied
            effective_volume = self._music_volume * self._master_volume
            pygame.mixer.music.set_volume(effective_volume)
        except pygame.error as e:
            print(f"[AudioSystem] Failed to play music '{path}': {e}")

    def stop_music(self, fade_ms: int = 1000) -> None:
        """
        Stop the currently playing music.

        Args:
            fade_ms: Fade-out duration in milliseconds.
        """
        pygame.mixer.music.fadeout(fade_ms)

    def pause_music(self) -> None:
        """Pause the currently playing music."""
        pygame.mixer.music.pause()

    def resume_music(self) -> None:
        """Resume the paused music."""
        pygame.mixer.music.unpause()

    def is_music_playing(self) -> bool:
        """Check if music is currently playing."""
        return bool(pygame.mixer.music.get_busy())

    def set_master_volume(self, volume: float) -> None:
        """
        Set the global master volume (0.0 to 1.0).

        Args:
            volume: Master volume level.
        """
        self._master_volume = max(0.0, min(1.0, volume))

        # Update music volume immediately
        effective_music_volume = self._music_volume * self._master_volume
        pygame.mixer.music.set_volume(effective_music_volume)

    def set_sfx_volume(self, volume: float) -> None:
        """
        Set the sound effects volume (0.0 to 1.0).

        Args:
            volume: SFX volume level.
        """
        self._sfx_volume = max(0.0, min(1.0, volume))
        # Note: SFX volume is applied per-sound when playing

    def set_music_volume(self, volume: float) -> None:
        """
        Set the music volume (0.0 to 1.0).

        Args:
            volume: Music volume level.
        """
        self._music_volume = max(0.0, min(1.0, volume))

        # Update music volume immediately
        effective_volume = self._music_volume * self._master_volume
        pygame.mixer.music.set_volume(effective_volume)

    def get_master_volume(self) -> float:
        """Get the current master volume."""
        return self._master_volume

    def get_sfx_volume(self) -> float:
        """Get the current SFX volume."""
        return self._sfx_volume

    def get_music_volume(self) -> float:
        """Get the current music volume."""
        return self._music_volume
