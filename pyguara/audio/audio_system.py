"""Core interfaces for the Audio Subsystem."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pyguara.audio.exceptions import UnsupportedAudioCapability
from pyguara.audio.types import (
    AudioBusType,
    AudioCapability,
    AudioEffect,
    AudioPriority,
    SoundHandle,
)
from pyguara.common.types import Vector2
from pyguara.resources.meta import AudioMeta
from pyguara.resources.types import AudioClip


@runtime_checkable
class IAudioSystem(Protocol):
    """
    The main contract for playing audio in the engine.

    Abstracts away the concept of 'Channels' and 'Streams'.

    Features:
    - Basic sound effect and music playback
    - Spatial audio with distance attenuation and stereo panning
    - Audio bus hierarchy for grouped volume control
    - Priority-based channel management
    - Declared capabilities for what a backend cannot express

    Playing sounds are addressed by `SoundHandle`, not by channel number:
    see that type for why. Three features -- pitch, loop points and bus
    DSP -- are optional and declared through `capabilities`; asking a
    backend for one it does not have raises `UnsupportedAudioCapability`
    rather than silently doing nothing.
    """

    @property
    def capabilities(self) -> AudioCapability:
        """What this backend can do beyond plain playback.

        A game that wants to degrade instead of failing tests this
        before asking. See `AudioCapability`.

        Returns:
            The flags this backend honours; `AudioCapability.NONE` if it
            honours none of them.
        """
        ...

    def play_sfx(
        self,
        clip: AudioClip,
        volume: float = 1.0,
        loops: int = 0,
        priority: AudioPriority = AudioPriority.NORMAL,
        bus: AudioBusType = AudioBusType.SFX,
        pitch: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> SoundHandle | None:
        """
        Play a sound effect.

        Args:
            clip: The resource loaded via ResourceManager.
            volume: Playback volume (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).
            priority: Sound priority for channel stealing.
            bus: Audio bus to route the sound through.
            pitch: Playback rate multiplier; 1.0 is the clip's own rate,
                2.0 an octave up. Needs `AudioCapability.PITCH` for any
                value other than 1.0.
            loop_start: Seconds into the clip that a loop returns to.
                Ignored when `loops` is 0 -- a one-shot has no loop to
                place. Needs `AudioCapability.LOOP_POINTS`.
            loop_end: Seconds into the clip that a loop restarts from;
                `None` means the end of the clip.

        Returns:
            A handle for the playing sound, or None if no channel was
            available.

        Raises:
            UnsupportedAudioCapability: If `pitch` or the loop points are
                given values this backend cannot honour.
            ValueError: If the loop range is negative or inverted.
        """
        ...

    def play_sfx_at_position(
        self,
        clip: AudioClip,
        source_pos: Vector2,
        listener_pos: Vector2,
        volume: float = 1.0,
        loops: int = 0,
        priority: AudioPriority = AudioPriority.NORMAL,
        bus: AudioBusType = AudioBusType.SFX,
        pitch: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> SoundHandle | None:
        """
        Play a sound effect with spatial positioning.

        Calculates volume attenuation based on distance and stereo panning
        based on relative position to the listener.

        Args:
            clip: The resource loaded via ResourceManager.
            source_pos: World position of the sound source.
            listener_pos: World position of the listener (usually camera).
            volume: Base volume before spatial attenuation (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).
            priority: Sound priority for channel stealing.
            bus: Audio bus to route the sound through.
            pitch: Playback rate multiplier; see `play_sfx`.
            loop_start: Seconds into the clip that a loop returns to; see
                `play_sfx`.
            loop_end: Seconds into the clip that a loop restarts from.

        Returns:
            A handle for the playing sound, or None if the source was out
            of earshot or no channel was available.

        Raises:
            UnsupportedAudioCapability: If `pitch` or the loop points are
                given values this backend cannot honour.
            ValueError: If the loop range is negative or inverted.
        """
        ...

    def stop_sfx(self, sound: SoundHandle) -> None:
        """
        Stop one playing sound.

        A handle whose sound has already ended is a no-op, which is what
        makes this safe to call from teardown without checking first.

        Args:
            sound: The handle returned by play_sfx.
        """
        ...

    def is_sound_active(self, sound: SoundHandle) -> bool:
        """
        Check whether the sound a handle refers to is still playing.

        A one-shot sound finishes on its own with no callback, so a caller
        holding a handle cannot otherwise tell "still playing" from
        "finished". This answers exactly that, and -- unlike a channel
        number -- cannot be confused by an unrelated sound taking the
        channel over.

        Args:
            sound: The handle returned by play_sfx/play_sfx_at_position.

        Returns:
            True if that sound is still playing, False otherwise.
        """
        ...

    def pause_sfx(self) -> None:
        """Pause all sound effects."""
        ...

    def resume_sfx(self) -> None:
        """Resume all paused sound effects."""
        ...

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """
        Stream background music from disk.

        Args:
            path: File path to the music file.
            loop: Whether to restart when finished.
            fade_ms: Fade-in duration in milliseconds.
        """
        ...

    def stop_music(self, fade_ms: int = 1000) -> None:
        """
        Stop the currently playing music.

        Args:
            fade_ms: Fade-out duration in milliseconds.
        """
        ...

    def pause_music(self) -> None:
        """Pause the currently playing music."""
        ...

    def resume_music(self) -> None:
        """Resume the paused music."""
        ...

    def is_music_playing(self) -> bool:
        """Check if music is currently playing."""
        ...

    def set_master_volume(self, volume: float) -> None:
        """
        Set the global master volume (0.0 to 1.0).

        Args:
            volume: Master volume level.
        """
        ...

    def set_sfx_volume(self, volume: float) -> None:
        """
        Set the sound effects volume (0.0 to 1.0).

        Args:
            volume: SFX volume level.
        """
        ...

    def set_music_volume(self, volume: float) -> None:
        """
        Set the music volume (0.0 to 1.0).

        Args:
            volume: Music volume level.
        """
        ...

    def get_master_volume(self) -> float:
        """Get the current master volume."""
        ...

    def get_sfx_volume(self) -> float:
        """Get the current SFX volume."""
        ...

    def get_music_volume(self) -> float:
        """Get the current music volume."""
        ...

    # ========== Bus Management ==========

    def set_bus_volume(self, bus: AudioBusType, volume: float) -> None:
        """
        Set volume for a specific audio bus.

        Args:
            bus: The bus to adjust.
            volume: Volume level (0.0 to 1.0).
        """
        ...

    def get_bus_volume(self, bus: AudioBusType) -> float:
        """
        Get the volume of a specific audio bus.

        Args:
            bus: The bus to query.

        Returns:
            Current volume level (0.0 to 1.0).
        """
        ...

    def set_bus_muted(self, bus: AudioBusType, muted: bool) -> None:
        """
        Mute or unmute a specific audio bus.

        Args:
            bus: The bus to mute/unmute.
            muted: True to mute, False to unmute.
        """
        ...

    def is_bus_muted(self, bus: AudioBusType) -> bool:
        """
        Check if a bus is muted.

        Args:
            bus: The bus to check.

        Returns:
            True if muted, False otherwise.
        """
        ...

    def set_bus_effects(
        self, bus: AudioBusType, effects: Sequence[AudioEffect]
    ) -> None:
        """
        Replace the DSP chain on a bus.

        The chain is applied in order, so `[LowPassFilter(800), Reverb()]`
        reverberates a signal that has already been muffled. An empty
        sequence clears the bus, and is the one call a backend without
        `AudioCapability.BUS_EFFECTS` accepts -- clearing nothing is
        truthfully a no-op, where installing something is not.

        Args:
            bus: The bus to configure.
            effects: The chain, in application order.

        Raises:
            UnsupportedAudioCapability: If `effects` is non-empty and this
                backend lacks `AudioCapability.BUS_EFFECTS`.
        """
        ...

    def get_bus_effects(self, bus: AudioBusType) -> tuple[AudioEffect, ...]:
        """
        Get the DSP chain installed on a bus.

        Args:
            bus: The bus to query.

        Returns:
            The chain in application order; empty if the bus has none, or
            if this backend cannot hold one.
        """
        ...

    def set_sound_mix(self, sound: SoundHandle, attenuation: float, pan: float) -> None:
        """
        Update volume attenuation and stereo pan for an already-playing sound.

        Used to keep spatial audio in sync as a sound source or the listener moves
        during playback, without restarting the sound.

        Args:
            sound: The handle returned by play_sfx/play_sfx_at_position.
            attenuation: Distance-based volume multiplier (0.0 to 1.0).
            pan: Stereo pan (-1.0 = left, 0.0 = center, 1.0 = right).
        """
        ...

    # ========== Listener Management ==========

    def set_listener_position(self, position: Vector2) -> None:
        """
        Set the listener position for spatial audio.

        All spatial sounds will be calculated relative to this position.

        Args:
            position: World position of the listener.
        """
        ...

    def shutdown(self) -> None:
        """
        Stop all audio and release the underlying device.

        Idempotent: a second call is a no-op. After this, playback methods
        must not raise but need not produce sound.
        """
        ...


def require_capability(system: IAudioSystem, capability: AudioCapability) -> None:
    """Raise unless `system` advertises `capability`.

    Lives beside the protocol rather than inside a backend so that every
    backend declines in the same words, and so the contract has one
    implementation to test.

    Args:
        system: The audio system being asked.
        capability: The single capability required.

    Raises:
        UnsupportedAudioCapability: If `system` does not advertise it.
    """
    if capability not in system.capabilities:
        raise UnsupportedAudioCapability(capability, type(system).__name__)


def resolve_loop_points(
    clip: AudioClip,
    loop_start: float | None,
    loop_end: float | None,
) -> tuple[float | None, float | None, bool]:
    """Work out which loop points apply to a play, and who asked for them.

    An explicit argument wins over the clip's `.meta` sidecar, and the
    difference matters to the caller of this function: an argument is a
    programmer asking at a call site, where a sidecar is an asset
    describing itself. A backend that cannot honour loop points should
    raise for the first and warn for the second -- refusing to play a
    clip because somebody wrote loop points in its sidecar would make one
    line of metadata silence a sound that used to work.

    Args:
        clip: The clip being played, read for an `AudioMeta` sidecar.
        loop_start: Explicit start, or None to fall back to the sidecar.
        loop_end: Explicit end, or None to fall back to the sidecar.

    Returns:
        `(start, end, explicit)`. `start` is None when neither source
        supplies loop points, in which case nothing was requested.
        `explicit` is True when the values came from the arguments.

    Raises:
        ValueError: If the resolved range is negative or inverted.
    """
    explicit = loop_start is not None or loop_end is not None
    if not explicit:
        meta = clip.import_meta
        if isinstance(meta, AudioMeta):
            loop_start, loop_end = meta.loop_start, meta.loop_end

    if loop_start is None and loop_end is None:
        return None, None, False

    # An end with no start means "loop from the top to here", which is a
    # real request and not a half-filled one.
    start = 0.0 if loop_start is None else loop_start
    if start < 0.0:
        raise ValueError(f"loop_start must be >= 0, got {start}")
    if loop_end is not None and loop_end <= start:
        raise ValueError(
            f"loop_end ({loop_end}) must be greater than loop_start ({start})"
        )
    return start, loop_end, explicit
