"""The clip the native audio backend plays."""

from __future__ import annotations

from typing import Any

from pyguara.resources.types import AudioClip


class NativeAudioClip(AudioClip):
    """A decoded clip: stereo float at the mixer's rate, held by the mixer.

    The samples live in a `MixerClip`, shared by reference with every voice
    playing them, so a clip costs its decoded size once however many times
    it is playing.
    """

    def __init__(self, path: str, samples: Any, rate: int) -> None:
        """Initialize the clip.

        Args:
            path: The source file path.
            samples: The `MixerClip` holding the decoded audio.
            rate: The mixer rate the samples are at.
        """
        super().__init__(path)
        self._samples = samples
        self._rate = rate
        self.gain = 1.0

    @property
    def duration(self) -> float:
        """Return the duration in seconds."""
        return float(self._samples.frames) / self._rate

    @property
    def frames(self) -> int:
        """The length in mixer frames."""
        return int(self._samples.frames)

    @property
    def native_handle(self) -> Any:
        """Return the `MixerClip` the mixer plays."""
        return self._samples

    def set_volume(self, volume: float) -> None:
        """Scale every future play of this clip (0.0 to 1.0).

        A play already under way keeps its loudness, as with pygame, where
        a `Sound`'s volume applied to the channels it was started on.
        """
        self.gain = max(0.0, min(1.0, volume))
