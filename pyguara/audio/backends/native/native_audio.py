"""The audio backend with pitch and loop points."""

import contextlib
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import pygame

from pyguara import native
from pyguara.audio.audio_system import resolve_loop_points
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.audio.types import (
    AudioBusType,
    AudioCapability,
    AudioPriority,
    SoundHandle,
)
from pyguara.common.types import Vector2
from pyguara.log import get_logger
from pyguara.resources.types import AudioClip

from .types import NativeAudioClip

logger = get_logger(__name__)

MIN_PITCH = 0.25
"""Two octaves down. Below this a clip is too stretched to be a variation."""

MAX_PITCH = 4.0
"""Two octaves up. Linear resampling aliases audibly well before this."""

PITCH_STEP = 0.01
"""Pitches are rendered to the nearest 1%, about 17 cents.

A continuous pitch would allocate a buffer per play on the most frequently
played sounds in a game. Quantised, a variation range of a few percent is a
handful of buffers, and nobody hears the difference between 1.003 and 1.

The cache key is this step, so it also bounds how many entries one clip can
occupy at 375.
"""

DEFAULT_CACHE_BYTES = 32 * 1024 * 1024
"""What rendered pitch and loop buffers may hold, over the clips themselves."""

_MIN_LOOP_SEGMENT_SECONDS = 1.0
"""A queued loop segment is at least this long, in whole laps.

`Channel.queue` is one deep, so the next segment has to be queued while the
current one plays, and the segment's length is the slack for that. A 50 ms
loop would otherwise need re-queueing every 50 ms from a frame loop that can
stall for longer than that. Baking laps together is measured sample-exact in
`tests/integration/test_audio_output.py`.
"""

_BYTES_PER_SAMPLE = 2


def _is_unity(pitch: float) -> bool:
    """Return whether `pitch` rounds to the clip's own rate."""
    return round(pitch / PITCH_STEP) == round(1.0 / PITCH_STEP)


@dataclass(slots=True)
class _LoopBuffers:
    """The rendered sounds a looping play moves through."""

    intro: pygame.mixer.Sound
    segment: pygame.mixer.Sound
    laps_per_segment: int
    lap: pygame.mixer.Sound


@dataclass(slots=True)
class _Loop:
    """A sound playing an intro and then laps of a region."""

    channel_id: int
    buffers: _LoopBuffers
    remaining: int
    """Laps still to queue, or -1 for forever."""


class NativeAudioSystem(PygameAudioSystem):
    """`PygameAudioSystem`, plus pitch and loop points rendered in Rust.

    Output is still `pygame.mixer`: this backend changes what is handed to a
    channel and nothing about how it reaches a speaker, so spatial audio, buses
    and channel stealing are all inherited. `BUS_EFFECTS` is declined because
    it needs post-mix ownership of the device, which `pygame.mixer` has no hook
    for and `cpal` would link ALSA to get.

    **Selected by `AudioConfig.backend`, not by `native_acceleration`.** Nothing
    in Python can stand in for it, so `PYGUARA_NO_NATIVE=1` must not change what
    a game is allowed to ask for: `PYGUARA_AUDIO_BACKEND=pygame` is what isolates
    a bug here. See ADR 0004, Decision 4.

    Pitch is resampling, so **it changes duration as well**: 2.0 is an octave up
    and half as long. Loop points need `update()` called once a frame, which
    `Application` does.
    """

    def __init__(
        self,
        frequency: int = 44100,
        size: int = -16,
        channels: int = 2,
        buffer: int = 512,
        num_channels: int = 32,
        cache_bytes: int = DEFAULT_CACHE_BYTES,
    ) -> None:
        """Open the mixer, having checked the extension is there to use it.

        Args:
            frequency: Sample rate.
            size: Sample size. Must be -16, which is all this backend renders.
            channels: Number of audio channels.
            buffer: Buffer size.
            num_channels: Number of mixer channels for simultaneous sounds.
            cache_bytes: The most rendered buffers may hold; the least recently
                used go first. A sound that is playing outlives its eviction.

        Raises:
            RuntimeError: If the extension cannot be imported.
            ValueError: If `size` is anything but signed 16-bit.
        """
        self._native = native.require_extension("the native audio backend")
        if size != -16:
            raise ValueError(
                f"NativeAudioSystem renders signed 16-bit, so size must be -16, "
                f"got {size}."
            )
        super().__init__(frequency, size, channels, buffer, num_channels)
        self._cache_bytes = cache_bytes
        self._cached_bytes = 0
        self._cache: OrderedDict[tuple[Any, ...], tuple[Any, int]] = OrderedDict()
        self._loops: dict[SoundHandle, _Loop] = {}

    @property
    def capabilities(self) -> AudioCapability:
        """Report pitch and loop points."""
        return AudioCapability.PITCH | AudioCapability.LOOP_POINTS

    def _decline_unsupported(
        self,
        clip: AudioClip,
        loops: int,
        pitch: float,
        loop_start: float | None,
        loop_end: float | None,
    ) -> None:
        """Reject what no backend could honour, which is all that is left.

        Args:
            clip: The clip about to play.
            loops: The requested loop count.
            pitch: The requested playback rate.
            loop_start: Explicit loop start, if any.
            loop_end: Explicit loop end, if any.

        Raises:
            ValueError: If `pitch` is outside `MIN_PITCH`-`MAX_PITCH`, or the
                loop range is negative or inverted.
        """
        if not MIN_PITCH <= pitch <= MAX_PITCH:
            raise ValueError(
                f"pitch must be between {MIN_PITCH} and {MAX_PITCH}, got {pitch}"
            )
        resolve_loop_points(clip, loop_start, loop_end)

    def _play_sound(
        self,
        clip: AudioClip,
        volume: float,
        loops: int,
        priority: AudioPriority,
        bus: AudioBusType,
        position: Vector2 | None,
        pan: float = 0.0,
        pitch: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
        sound: pygame.mixer.Sound | None = None,
    ) -> SoundHandle | None:
        """Render whatever the request needs, then play it on a channel."""
        start, end, _explicit = resolve_loop_points(clip, loop_start, loop_end)

        if start is None or loops == 0:
            played = None if _is_unity(pitch) else self._pitched(clip, pitch)
            return super()._play_sound(
                clip, volume, loops, priority, bus, position, pan, sound=played
            )

        buffers = self._loop_buffers(clip, pitch, start, end)
        handle = super()._play_sound(
            clip, volume, 0, priority, bus, position, pan, sound=buffers.intro
        )
        if handle is not None:
            channel_id = self._playing_sounds[handle].channel_id
            self._loops[handle] = _Loop(channel_id, buffers, remaining=loops)
            self._queue_next(handle)
        return handle

    def _pcm_of(self, clip: AudioClip) -> bytes:
        """Read a clip's samples back from its sound.

        Raises:
            TypeError: If the clip came from another backend's loader, whose
                sound this one has no way to know the format of.
        """
        if not isinstance(clip, NativeAudioClip):
            raise TypeError(
                f"'{clip.path}' is a {type(clip).__name__}, and pitch and loop "
                "points need a NativeAudioClip. Load it through a ResourceManager "
                "bootstrapped with AudioConfig.backend = NATIVE."
            )
        return bytes(clip.native_handle.get_raw())

    def _cached(self, key: tuple[Any, ...]) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        self._cache.move_to_end(key)
        return entry[0]

    def _remember(self, key: tuple[Any, ...], value: Any, size: int) -> None:
        self._cache[key] = (value, size)
        self._cached_bytes += size
        while self._cached_bytes > self._cache_bytes and len(self._cache) > 1:
            _key, (_value, evicted) = self._cache.popitem(last=False)
            self._cached_bytes -= evicted

    def _render(self, clip: AudioClip, pitch: float) -> bytes:
        """Return a clip's samples at `pitch`, at the mixer's own rate."""
        rate, _format, channels = pygame.mixer.get_init()
        pcm = self._pcm_of(clip)
        if _is_unity(pitch):
            return pcm
        rendered: bytes = self._native.resample_pcm(
            pcm, rate, channels, rate, channels, pitch
        )
        return rendered

    def _pitched(self, clip: AudioClip, pitch: float) -> pygame.mixer.Sound:
        """Return the cached sound for a clip at a quantised pitch."""
        key = ("pitch", clip.path, round(pitch / PITCH_STEP))
        cached = self._cached(key)
        if cached is not None:
            result: pygame.mixer.Sound = cached
            return result
        pcm = self._render(clip, pitch)
        sound = pygame.mixer.Sound(buffer=pcm)
        self._remember(key, sound, len(pcm))
        return sound

    def _loop_buffers(
        self, clip: AudioClip, pitch: float, start: float, end: float | None
    ) -> _LoopBuffers:
        """Return the sounds for a region, rendered once per pitch and region."""
        key = ("loop", clip.path, round(pitch / PITCH_STEP), start, end)
        cached = self._cached(key)
        if cached is not None:
            result: _LoopBuffers = cached
            return result

        rate, _format, channels = pygame.mixer.get_init()
        frame = channels * _BYTES_PER_SAMPLE
        pcm = self._render(clip, pitch)
        frames = len(pcm) // frame
        # Seconds name positions in the clip, and a pitched clip reaches each
        # one sooner.
        # Rounded, because a whole number of frames in seconds rarely survives
        # the round trip through a float, and one frame out is an audible click.
        first = min(round(start * rate / pitch), frames)
        last = frames if end is None else min(round(end * rate / pitch), frames)
        if last <= first:
            raise ValueError(
                f"Loop region {start}-{end} s is empty in '{clip.path}', which is "
                f"{clip.duration:.3f} s long."
            )
        lap_pcm = pcm[first * frame : last * frame]
        laps = max(1, int(_MIN_LOOP_SEGMENT_SECONDS * rate / (last - first)) + 1)
        intro_pcm = pcm[: last * frame]
        # Nothing past the loop end is ever heard, so none of it is kept.
        buffers = _LoopBuffers(
            intro=pygame.mixer.Sound(buffer=intro_pcm),
            segment=pygame.mixer.Sound(buffer=lap_pcm * laps),
            laps_per_segment=laps,
            lap=pygame.mixer.Sound(buffer=lap_pcm),
        )
        size = len(intro_pcm) + len(lap_pcm) * (laps + 1)
        self._remember(key, buffers, size)
        return buffers

    def _queue_next(self, handle: SoundHandle) -> None:
        """Queue the next segment of a loop, if the channel has room for one."""
        loop = self._loops[handle]
        buffers = loop.buffers
        channel = pygame.mixer.Channel(loop.channel_id)
        if channel.get_queue() is not None or loop.remaining == 0:
            return
        if loop.remaining < 0:
            channel.queue(buffers.segment)
        elif loop.remaining >= buffers.laps_per_segment:
            channel.queue(buffers.segment)
            loop.remaining -= buffers.laps_per_segment
        else:
            channel.queue(buffers.lap)
            loop.remaining -= 1

    def update(self) -> None:
        """Keep every looping sound's queue topped up.

        Reaps a loop whose sound has ended, so a channel that stopped on its
        own or was recycled does not get a stale segment queued onto it.
        """
        for handle in list(self._loops):
            if self.is_sound_active(handle):
                with contextlib.suppress(pygame.error):
                    self._queue_next(handle)

    def is_sound_active(self, sound: SoundHandle) -> bool:
        """Return True only while the sound this handle refers to is playing.

        A loop moves through three `Sound` objects on one channel, so it is
        told apart from an unrelated sound by membership rather than identity.
        """
        loop = self._loops.get(sound)
        if loop is None:
            return super().is_sound_active(sound)
        with contextlib.suppress(pygame.error):
            channel = pygame.mixer.Channel(loop.channel_id)
            current = channel.get_sound()
            buffers = loop.buffers
            if channel.get_busy() and any(
                current is playing
                for playing in (buffers.intro, buffers.segment, buffers.lap)
            ):
                return True
        self._forget(sound)
        return False

    def _forget(self, sound: SoundHandle) -> None:
        """Drop all tracking for a sound that is no longer ours."""
        self._loops.pop(sound, None)
        super()._forget(sound)

    def shutdown(self) -> None:
        """Stop all audio, release the mixer, and drop the rendered buffers."""
        super().shutdown()
        self._loops.clear()
        self._cache.clear()
        self._cached_bytes = 0
