"""Audio system types and data structures."""

from dataclasses import dataclass, field
from enum import Enum, Flag, auto
from itertools import count

from pyguara.common.types import Vector2


class AudioPriority(Enum):
    """Priority levels for sound effects when channels are limited.

    When all channels are occupied, lower priority sounds may be stopped
    to make room for higher priority ones (channel stealing).
    """

    LOW = 0  # Ambient sounds, background effects
    NORMAL = 1  # Standard game sounds
    HIGH = 2  # Important feedback (hits, pickups)
    CRITICAL = 3  # Must-play sounds (UI, critical alerts)


class AudioBusType(Enum):
    """Built-in audio bus types.

    Buses form a hierarchy: Master -> SFX/Music/Voice
    Volume changes propagate down the hierarchy.
    """

    MASTER = auto()
    SFX = auto()
    MUSIC = auto()
    VOICE = auto()


@dataclass
class AudioBus:
    """Represents an audio bus in the mixing hierarchy.

    Buses allow grouping sounds for collective volume control.
    The effective volume is: bus_volume * parent_volume * master_volume.

    Attributes:
        name: Unique identifier for this bus.
        volume: Local volume (0.0 to 1.0).
        muted: Whether the bus is muted.
        parent: Parent bus name (None for master).
    """

    name: str
    volume: float = 1.0
    muted: bool = False
    parent: str | None = None

    def get_effective_volume(self, parent_volume: float = 1.0) -> float:
        """Calculate effective volume considering mute state and parent.

        Args:
            parent_volume: Volume from parent bus chain.

        Returns:
            Effective volume (0.0 to 1.0).
        """
        if self.muted:
            return 0.0
        return self.volume * parent_volume


@dataclass
class SpatialAudioConfig:
    """Configuration for spatial audio calculations.

    Controls how sound volume and panning are calculated based on
    distance from the listener.

    Attributes:
        max_distance: Distance at which sound is inaudible (in world units).
        reference_distance: Distance at which volume is 100% (default 1.0).
        rolloff_factor: How quickly sound attenuates (1.0 = realistic, <1 = slower).
        pan_strength: Stereo panning intensity (0.0 = mono, 1.0 = full stereo).
    """

    max_distance: float = 1000.0
    reference_distance: float = 100.0
    rolloff_factor: float = 1.0
    pan_strength: float = 1.0

    def __post_init__(self) -> None:
        """Validate the configuration.

        The attenuation and panning maths divide by ``reference_distance`` and
        ``max_distance`` and assume ``max_distance`` is the outer edge, so a
        zero or inverted range is not a quiet degradation -- it is a
        ``ZeroDivisionError`` in ``calculate_pan`` and a hard volume cliff in
        ``calculate_attenuation``. Reject it at construction instead.

        Raises:
            ValueError: If the distances or factors are out of range.
        """
        if self.reference_distance <= 0.0:
            raise ValueError(
                f"reference_distance must be > 0, got {self.reference_distance}"
            )
        if self.max_distance <= self.reference_distance:
            raise ValueError(
                f"max_distance ({self.max_distance}) must be greater than "
                f"reference_distance ({self.reference_distance})"
            )
        if self.rolloff_factor < 0.0:
            raise ValueError(f"rolloff_factor must be >= 0, got {self.rolloff_factor}")
        if self.pan_strength < 0.0:
            raise ValueError(f"pan_strength must be >= 0, got {self.pan_strength}")

    def calculate_attenuation(self, distance: float) -> float:
        """Calculate volume attenuation based on distance.

        Uses inverse distance attenuation model (like OpenAL).

        Args:
            distance: Distance from listener to sound source.

        Returns:
            Volume multiplier (0.0 to 1.0).
        """
        if distance <= self.reference_distance:
            return 1.0
        if distance >= self.max_distance:
            return 0.0

        # Inverse distance attenuation
        attenuation = self.reference_distance / (
            self.reference_distance
            + self.rolloff_factor * (distance - self.reference_distance)
        )
        return max(0.0, min(1.0, attenuation))

    def calculate_pan(self, source_pos: Vector2, listener_pos: Vector2) -> float:
        """Calculate stereo panning based on relative position.

        Args:
            source_pos: World position of the sound source.
            listener_pos: World position of the listener.

        Returns:
            Pan value (-1.0 = full left, 0.0 = center, 1.0 = full right).
        """
        dx = source_pos.x - listener_pos.x
        distance = abs(dx)

        if distance < 1.0:  # Very close, center it
            return 0.0

        # Normalize and apply pan strength
        # Clamp to max_distance for panning calculation
        normalized = min(distance / self.max_distance, 1.0)
        pan = (1.0 if dx > 0 else -1.0) * normalized * self.pan_strength

        return max(-1.0, min(1.0, pan))


class AudioCapability(Flag):
    """What an audio backend can actually do.

    Three of the protocol's features cannot be expressed by every mixer,
    and the engine ships exactly one backend that expresses none of them.
    Rather than let `IAudioSystem` advertise methods that quietly do
    nothing, a backend declares what it supports here and raises
    `UnsupportedAudioCapability` for the rest.

    Every capability has a request that means "not asked for" --
    `pitch=1.0`, `loop_start=None`, an empty effect list -- so a game
    that uses none of them runs on any backend. One that uses them reads
    `IAudioSystem.capabilities` to find out whether it can.

    Attributes:
        NONE: No optional capability. What `PygameAudioSystem` reports.
        PITCH: Per-play playback-rate change (`pitch` on `play_sfx`).
        LOOP_POINTS: Looping between two points inside a clip rather than
            over the whole file.
        BUS_EFFECTS: DSP attached to a bus (`set_bus_effects`).
    """

    NONE = 0
    PITCH = auto()
    LOOP_POINTS = auto()
    BUS_EFFECTS = auto()


@dataclass(frozen=True, slots=True)
class SoundHandle:
    """An opaque reference to one playing sound.

    `token` is minted by the audio system, means nothing to a caller, and
    is never reused within a process -- which is the entire point. A
    mixer channel number is recycled the instant its sound ends, so an
    int held for a few frames can address a sound the holder never
    started: `stop_sfx(7)` stops whatever is on channel 7 now. A handle
    that has ended simply stops resolving, and the methods that take one
    become no-ops.

    Attributes:
        token: Process-unique identifier. Treat it as opaque; its value
            carries no information and may change meaning between
            releases.
    """

    token: int


# A process-wide counter, so a handle is unique across every audio system
# in the process rather than merely within one. `count.__next__` is a
# single C call, which makes it atomic under CPython -- sounds are started
# from gameplay code on the main thread, but a loader thread firing a cue
# must not be able to mint a duplicate.
_next_token = count(1).__next__


def new_sound_handle() -> SoundHandle:
    """Mint a handle no other sound in this process will share.

    Returns:
        A fresh `SoundHandle`.
    """
    return SoundHandle(_next_token())


@dataclass
class PlayingSoundInfo:
    """Tracks information about a currently playing sound.

    Used for channel management, priority-based stealing, and spatial updates.

    `handle` is the identity callers hold; `channel_id` is where the sound
    happens to be playing, which the mixer owns and recycles.
    """

    handle: SoundHandle
    channel_id: int
    clip_path: str
    priority: AudioPriority
    bus: AudioBusType
    base_volume: float
    position: Vector2 | None = None
    is_spatial: bool = False


@dataclass
class AudioBusManager:
    """Manages the audio bus hierarchy and volume calculations.

    Provides a tree structure for audio mixing with automatic
    volume propagation.
    """

    buses: dict[str, AudioBus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize default bus hierarchy."""
        if not self.buses:
            self._create_default_buses()

    def _create_default_buses(self) -> None:
        """Create the default bus hierarchy: Master -> SFX/Music/Voice."""
        self.buses = {
            "master": AudioBus("master", volume=1.0, parent=None),
            "sfx": AudioBus("sfx", volume=1.0, parent="master"),
            "music": AudioBus("music", volume=1.0, parent="master"),
            "voice": AudioBus("voice", volume=1.0, parent="master"),
        }

    def get_bus(self, name: str) -> AudioBus | None:
        """Get a bus by name."""
        return self.buses.get(name)

    def set_bus_volume(self, name: str, volume: float) -> None:
        """Set volume for a specific bus."""
        if name in self.buses:
            self.buses[name].volume = max(0.0, min(1.0, volume))

    def set_bus_muted(self, name: str, muted: bool) -> None:
        """Mute or unmute a specific bus."""
        if name in self.buses:
            self.buses[name].muted = muted

    def get_effective_volume(self, bus_name: str) -> float:
        """Calculate effective volume for a bus considering the hierarchy.

        Traverses the bus hierarchy to calculate final volume.

        Args:
            bus_name: Name of the bus to calculate volume for.

        Returns:
            Effective volume (0.0 to 1.0).
        """
        bus = self.buses.get(bus_name)
        if not bus:
            return 1.0

        # Walk up the parent chain
        volume = bus.volume if not bus.muted else 0.0
        parent_name = bus.parent

        while parent_name:
            parent = self.buses.get(parent_name)
            if not parent:
                break
            if parent.muted:
                return 0.0
            volume *= parent.volume
            parent_name = parent.parent

        return volume

    def get_bus_for_type(self, bus_type: AudioBusType) -> str:
        """Get bus name for a bus type enum."""
        return bus_type.name.lower()


@dataclass(frozen=True, slots=True)
class LowPassFilter:
    """Attenuate everything above `cutoff_hz`.

    The muffled-while-stunned and behind-a-wall effect.

    Attributes:
        cutoff_hz: Corner frequency in hertz. Above the audible range
            means no audible effect.
    """

    cutoff_hz: float = 20_000.0

    def __post_init__(self) -> None:
        """Reject a cutoff no filter can realise.

        Raises:
            ValueError: If `cutoff_hz` is not positive.
        """
        if self.cutoff_hz <= 0.0:
            raise ValueError(f"cutoff_hz must be > 0, got {self.cutoff_hz}")


@dataclass(frozen=True, slots=True)
class HighPassFilter:
    """Attenuate everything below `cutoff_hz`.

    Thins a bus out -- a radio voice, or keeping ambience out of the way
    of the music's low end.

    Attributes:
        cutoff_hz: Corner frequency in hertz. Below the audible range
            means no audible effect.
    """

    cutoff_hz: float = 20.0

    def __post_init__(self) -> None:
        """Reject a cutoff no filter can realise.

        Raises:
            ValueError: If `cutoff_hz` is not positive.
        """
        if self.cutoff_hz <= 0.0:
            raise ValueError(f"cutoff_hz must be > 0, got {self.cutoff_hz}")


@dataclass(frozen=True, slots=True)
class Reverb:
    """A room around everything on the bus.

    The parameter set is Freeverb's, which is what the free DSP libraries
    a second backend would reach for expose -- so a backend can implement
    this without inventing a mapping.

    Attributes:
        room_size: 0.0 (a closet) to 1.0 (a cathedral).
        damping: 0.0 (bright, tiled) to 1.0 (dead, carpeted).
        wet: How much reverberated signal to mix in (0.0 to 1.0).
        dry: How much of the original to keep (0.0 to 1.0).
    """

    room_size: float = 0.5
    damping: float = 0.5
    wet: float = 0.33
    dry: float = 0.67

    def __post_init__(self) -> None:
        """Reject parameters outside the unit range.

        Raises:
            ValueError: If any parameter is outside 0.0 to 1.0.
        """
        for name in ("room_size", "damping", "wet", "dry"):
            value: float = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within 0.0..1.0, got {value}")


AudioEffect = LowPassFilter | HighPassFilter | Reverb
"""One DSP effect on a bus.

A closed union rather than a protocol: an effect is a description a
backend interprets, not behaviour it calls, and a backend has to match on
the kind to configure its own DSP chain either way. Adding an effect is
therefore a deliberate protocol change, which is what stops one backend
inventing an effect the others cannot see.
"""
