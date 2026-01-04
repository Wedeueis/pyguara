"""Resource Loader strategy for Audio files."""

from typing import List
import pygame
from pyguara.resources.loader import IResourceLoader
from pyguara.resources.types import Resource
from .types import PygameAudioClip


class PygameSoundLoader(IResourceLoader):
    """
    Loads .wav and .ogg files into PygameAudioClip objects.

    Pygame suporta mp3, mas ogg/wav são preferidos para loops e SFX.
    """

    @property
    def supported_extensions(self) -> List[str]:
        """Return the list of support audio formats."""
        return [".wav", ".ogg", ".mp3"]

    def load(self, path: str) -> Resource:
        """
        Load the sound file into memory.

        Raises:
            pygame.error: If the format is unsupported or file is corrupted.
        """
        sound = pygame.mixer.Sound(path)
        return PygameAudioClip(path, sound)
