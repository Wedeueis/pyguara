"""Audio system types and data structures."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Optional

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
    parent: Optional[str] = None

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


@dataclass
class PlayingSoundInfo:
    """Tracks information about a currently playing sound.

    Used for channel management, priority-based stealing, and spatial updates.
    """

    channel_id: int
    clip_path: str
    priority: AudioPriority
    bus: AudioBusType
    base_volume: float
    position: Optional[Vector2] = None
    is_spatial: bool = False


@dataclass
class AudioBusManager:
    """Manages the audio bus hierarchy and volume calculations.

    Provides a tree structure for audio mixing with automatic
    volume propagation.
    """

    buses: Dict[str, AudioBus] = field(default_factory=dict)

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

    def get_bus(self, name: str) -> Optional[AudioBus]:
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
