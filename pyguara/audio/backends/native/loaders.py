"""Resource loader for the native audio backend."""

from __future__ import annotations

from typing import Any

from pyguara import native
from pyguara.log import get_logger
from pyguara.resources.meta import AssetMeta, AudioLoadMode, AudioMeta
from pyguara.resources.types import Resource

from .types import NativeAudioClip

logger = get_logger(__name__)


class NativeSoundLoader:
    """Decode audio files in Rust into clips for one mixer.

    Registered instead of `PygameSoundLoader` when `AudioConfig.backend` is
    `NATIVE`, given the `NativeAudioSystem`'s mixer: a clip is converted to
    the rate that mixer runs at, which on a device is the device's own. A
    clip is always fully decoded; see `PygameSoundLoader` for what that
    means for `load_mode: stream`.
    """

    def __init__(self, mixer: Any) -> None:
        """Load for a mixer.

        Args:
            mixer: The `NativeMixer` the clips will play on.
        """
        self._mixer = mixer

    @property
    def supported_extensions(self) -> list[str]:
        """Return the list of supported audio formats."""
        return [".wav", ".ogg", ".mp3", ".flac"]

    def load(self, path: str) -> Resource:
        """Load the sound file with default settings."""
        return self.load_with_meta(path, None)

    def load_with_meta(self, path: str, meta: AssetMeta | None) -> Resource:
        """Decode the file and convert it to the mixer's format.

        Args:
            path: Full path to the audio file.
            meta: Optional AudioMeta sidecar settings.

        Returns:
            A `NativeAudioClip`.

        Raises:
            OSError: If the file cannot be read or decoded.
        """
        if isinstance(meta, AudioMeta) and meta.get_load_mode() is AudioLoadMode.STREAM:
            logger.warning(
                "'%s' requests load_mode 'stream', but clips loaded via "
                "ResourceManager are always fully decoded. Use play_music() "
                "for streamed audio.",
                path,
            )
        module = native.require_extension("the native audio backend")
        pcm, rate, channels = module.decode_audio(path)
        samples = self._mixer.clip(pcm, rate, channels)
        return NativeAudioClip(path, samples, int(self._mixer.rate))
