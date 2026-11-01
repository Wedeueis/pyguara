"""Resource loader for the native audio backend."""

import pygame

from pyguara import native
from pyguara.log import get_logger
from pyguara.resources.meta import AssetMeta, AudioLoadMode, AudioMeta
from pyguara.resources.types import Resource

from .types import NativeAudioClip

logger = get_logger(__name__)


class NativeSoundLoader:
    """Decode audio files in Rust and render them to the mixer's format.

    Registered instead of `PygameSoundLoader` when `AudioConfig.backend` is
    `NATIVE`. A clip is always fully decoded; see `PygameSoundLoader` for what
    that means for `load_mode: stream`.
    """

    @property
    def supported_extensions(self) -> list[str]:
        """Return the list of supported audio formats."""
        return [".wav", ".ogg", ".mp3", ".flac"]

    def load(self, path: str) -> Resource:
        """Load the sound file with default settings."""
        return self.load_with_meta(path, None)

    def load_with_meta(self, path: str, meta: AssetMeta | None) -> Resource:
        """Decode the file and render it to the format the mixer was opened at.

        Args:
            path: Full path to the audio file.
            meta: Optional AudioMeta sidecar settings.

        Returns:
            A `NativeAudioClip`.

        Raises:
            OSError: If the file cannot be read or decoded.
            RuntimeError: If the extension or the mixer is not available.
        """
        if isinstance(meta, AudioMeta) and meta.get_load_mode() is AudioLoadMode.STREAM:
            logger.warning(
                "'%s' requests load_mode 'stream', but clips loaded via "
                "ResourceManager are always fully decoded. Use play_music() "
                "for streamed audio.",
                path,
            )

        init = pygame.mixer.get_init()
        if init is None:
            raise RuntimeError(f"Cannot load '{path}': the mixer is not open.")
        rate, _format, channels = init

        module = native.require_extension("the native audio backend")
        pcm, source_rate, source_channels = module.decode_audio(path)
        rendered = module.resample_pcm(
            pcm, source_rate, source_channels, rate, channels
        )
        return NativeAudioClip(path, pygame.mixer.Sound(buffer=rendered))
