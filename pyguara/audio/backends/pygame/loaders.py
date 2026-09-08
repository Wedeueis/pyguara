"""Resource Loader strategy for Audio files."""

import pygame

from pyguara.log import get_logger
from pyguara.resources.meta import AssetMeta, AudioLoadMode, AudioMeta
from pyguara.resources.types import Resource

from .types import PygameAudioClip

logger = get_logger(__name__)


class PygameSoundLoader:
    """Load .wav, .ogg and .mp3 files into PygameAudioClip objects.

    ogg/wav are preferred over mp3 for loops and SFX.

    Meta-aware: an ``AudioMeta`` sidecar is resolved and attached to the clip
    as ``clip.import_meta``. The audio system reads ``volume_db`` from there
    per play. A clip is always fully decoded into memory; ``load_mode:
    stream`` is only meaningful for music (``play_music``), so it is warned
    about rather than honoured here.
    """

    @property
    def supported_extensions(self) -> list[str]:
        """Return the list of supported audio formats."""
        return [".wav", ".ogg", ".mp3"]

    def load(self, path: str) -> Resource:
        """Load the sound file into memory with default settings."""
        return self.load_with_meta(path, None)

    def load_with_meta(self, path: str, meta: AssetMeta | None) -> Resource:
        """Load the sound file into memory.

        Args:
            path: Full path to the audio file.
            meta: Optional AudioMeta sidecar settings.

        Raises:
            pygame.error: If the format is unsupported or file is corrupted.
        """
        if isinstance(meta, AudioMeta) and meta.get_load_mode() is AudioLoadMode.STREAM:
            logger.warning(
                "'%s' requests load_mode 'stream', but clips loaded via "
                "ResourceManager are always fully decoded. Use play_music() "
                "for streamed audio.",
                path,
            )

        sound = pygame.mixer.Sound(path)
        return PygameAudioClip(path, sound)
