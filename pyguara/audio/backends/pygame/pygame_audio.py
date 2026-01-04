"""Pygame implementation of the Audio System."""

import pygame
from pyguara.audio.audio_system import IAudioSystem
from pyguara.resources.types import AudioClip


class PygameAudioSystem(IAudioSystem):
    """Pygame implementation for the PyGuara AudioSystem."""

    def __init__(
        self,
        frequency: int = 44100,
        size: int = -16,
        channels: int = 2,
        buffer: int = 512,
    ):
        """
        Initialize the Pygame mixer.

        Args adjusted for low latency (small buffer).
        """
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency, size, channels, buffer)
            # Alocates enough channels for simultaneos sounds
            pygame.mixer.set_num_channels(32)

    def play_sfx(self, clip: AudioClip, volume: float = 1.0) -> None:
        """
        Play a sound effect "fire and forget".

        Uses Pygame audio format and mixer.

        Args:
            clip (AudioClip): The resource loaded via ResourceManager.
            volume (float): Playback volume (multiplied by master volume).
        """
        try:
            native_sound = clip.native_handle

            # Type guard opcional se você quiser ser muito seguro
            if isinstance(native_sound, pygame.mixer.Sound):
                native_sound.set_volume(volume)
                native_sound.play()
        except AttributeError:
            print(f"[AudioSystem] Error: Resource {clip.path} is not a valid Sound.")

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """
        Stream background music from disk (does not use AudioClip resources usually).

        Uses pygame mixer to stream from a file.

        Args:
            path (str): File path to the music file.
            loop (bool): Whether to restart when finished.
            fade_ms (int): Fade-in duration in milliseconds.
        """
        try:
            pygame.mixer.music.load(path)
            loops = -1 if loop else 0
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
        except pygame.error as e:
            print(f"[AudioSystem] Failed to play music '{path}': {e}")

    def stop_music(self, fade_ms: int = 1000) -> None:
        """Stop the currently playing music."""
        pygame.mixer.music.fadeout(fade_ms)

    def set_master_volume(self, volume: float) -> None:
        """Set the global volume (0.0 to 1.0)."""
        # Pygame only implements a global volume for music
        # TODO: implement a global volume for SFX and channel groups
        pygame.mixer.music.set_volume(volume)
