"""Audio subsystem exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyguara.audio.types import AudioCapability


class AudioError(Exception):
    """Base class for every error raised by `pyguara.audio`."""


class UnsupportedAudioCapability(AudioError):
    """A backend was asked for something it cannot do.

    Raised rather than ignored. A mixer that cannot pitch-shift and
    accepts `pitch=1.2` anyway reports success for a sound that plays at
    its original speed, and the caller has no way to find out -- the same
    "guard that returns a wrong answer" the engine has removed elsewhere.

    Every capability has a default value that means "not asked for"
    (`pitch=1.0`, `loop_start=None`, no bus effects), so this can only
    fire for a caller that asked on purpose. A caller that would rather
    degrade than fail reads `IAudioSystem.capabilities` first.

    Attributes:
        capability: The capability that was requested.
        backend: Class name of the audio system that declined it.
    """

    def __init__(self, capability: AudioCapability, backend: str) -> None:
        """Build the error.

        Args:
            capability: The capability that was requested.
            backend: Class name of the audio system that declined it.
        """
        self.capability = capability
        self.backend = backend
        super().__init__(
            f"{backend} does not support "
            f"{capability.name or capability!s}. "
            f"Check IAudioSystem.capabilities before asking for it."
        )
