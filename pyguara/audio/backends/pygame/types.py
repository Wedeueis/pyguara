"""Pygame-specific implementations for Audio resources."""

import pygame
from pyguara.resources.types import AudioClip


class PygameAudioClip(AudioClip):
    """
    Concrete wrapper for a pygame.mixer.Sound object.

    Used for Sound Effects (SFX) that need low latency and polyphony.
    """

    def __init__(self, path: str, sound: pygame.mixer.Sound):
        """
        Initialize the Pygame sound.

        Args:
            path (str): The source file path.
            sound (pygame.mixer.Sound): The loaded Pygame sound object.
        """
        super().__init__(path)
        self._sound = sound

    @property
    def duration(self) -> float:
        """Return the duration in seconds."""
        return float(self._sound.get_length())

    @property
    def native_handle(self) -> pygame.mixer.Sound:
        """Return the internal pygame Sound object for the mixer."""
        return self._sound

    def set_volume(self, volume: float) -> None:
        """Set the volume for this specific clip (0.0 to 1.0)."""
        self._sound.set_volume(volume)
