"""The clip the native audio backend plays."""

import pygame

from pyguara.resources.types import AudioClip


class NativeAudioClip(AudioClip):
    """A decoded clip, held as a `pygame.mixer.Sound` at the mixer's format.

    The samples live only in the `Sound`, which copies its buffer, so a clip
    costs its decoded size once rather than twice. A pitched variant reads
    them back with `get_raw()`, which is a copy, but only on a cache miss.
    """

    def __init__(self, path: str, sound: pygame.mixer.Sound) -> None:
        """Initialize the clip.

        Args:
            path: The source file path.
            sound: The decoded sound, already at the mixer's format.
        """
        super().__init__(path)
        self._sound = sound

    @property
    def duration(self) -> float:
        """Return the duration in seconds."""
        return float(self._sound.get_length())

    @property
    def native_handle(self) -> pygame.mixer.Sound:
        """Return the sound the mixer plays."""
        return self._sound

    def set_volume(self, volume: float) -> None:
        """Set the volume for this specific clip (0.0 to 1.0)."""
        self._sound.set_volume(volume)
