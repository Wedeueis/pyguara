"""Type definitions for the replay system.

Provides data structures for recording and playing back input events
for deterministic replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class InputEventType(Enum):
    """Types of input events that can be recorded."""

    KEY_DOWN = auto()
    KEY_UP = auto()
    MOUSE_DOWN = auto()
    MOUSE_UP = auto()
    MOUSE_MOVE = auto()
    GAMEPAD_BUTTON_DOWN = auto()
    GAMEPAD_BUTTON_UP = auto()
    GAMEPAD_AXIS = auto()
    ACTION = auto()  # High-level action events


@dataclass
class RecordedInputEvent:
    """A single recorded input event.

    Attributes:
        event_type: Type of input event.
        device: Device type string (keyboard, mouse, gamepad).
        code: Key/button code or axis index.
        value: Event value (1.0 for press, 0.0 for release, or axis value).
        action: Optional action name if this is an action event.
        position: Optional mouse position for mouse events.
    """

    event_type: InputEventType
    device: str
    code: int
    value: float = 1.0
    action: Optional[str] = None
    position: Optional[tuple[float, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        data: Dict[str, Any] = {
            "event_type": self.event_type.name,
            "device": self.device,
            "code": self.code,
            "value": self.value,
        }
        if self.action:
            data["action"] = self.action
        if self.position:
            data["position"] = list(self.position)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RecordedInputEvent:
        """Create from dictionary."""
        position = None
        if "position" in data:
            position = tuple(data["position"])
        return cls(
            event_type=InputEventType[data["event_type"]],
            device=data["device"],
            code=data["code"],
            value=data.get("value", 1.0),
            action=data.get("action"),
            position=position,
        )


@dataclass
class InputFrame:
    """A single frame of recorded input.

    Attributes:
        frame_id: Sequential frame number.
        timestamp: Time in seconds from start of recording.
        delta_time: Time since previous frame.
        events: List of input events that occurred this frame.
    """

    frame_id: int
    timestamp: float
    delta_time: float = 0.0
    events: List[RecordedInputEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "delta_time": self.delta_time,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InputFrame:
        """Create from dictionary."""
        return cls(
            frame_id=data["frame_id"],
            timestamp=data["timestamp"],
            delta_time=data.get("delta_time", 0.0),
            events=[RecordedInputEvent.from_dict(e) for e in data.get("events", [])],
        )


@dataclass
class ReplayMetadata:
    """Metadata about a replay recording.

    Attributes:
        version: Replay format version.
        seed: Random seed used for the session.
        start_scene: Name of the starting scene.
        engine_version: PyGuara version used.
        recorded_at: ISO timestamp of recording.
        duration: Total duration in seconds.
        frame_count: Total number of frames.
        description: Optional description of the replay.
    """

    version: int = 1
    seed: int = 0
    start_scene: str = ""
    engine_version: str = "0.0.0"
    recorded_at: str = ""
    duration: float = 0.0
    frame_count: int = 0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "version": self.version,
            "seed": self.seed,
            "start_scene": self.start_scene,
            "engine_version": self.engine_version,
            "recorded_at": self.recorded_at,
            "duration": self.duration,
            "frame_count": self.frame_count,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReplayMetadata:
        """Create from dictionary."""
        return cls(
            version=data.get("version", 1),
            seed=data.get("seed", 0),
            start_scene=data.get("start_scene", ""),
            engine_version=data.get("engine_version", "0.0.0"),
            recorded_at=data.get("recorded_at", ""),
            duration=data.get("duration", 0.0),
            frame_count=data.get("frame_count", 0),
            description=data.get("description", ""),
        )


@dataclass
class ReplayData:
    """Complete replay data structure.

    Attributes:
        metadata: Replay metadata.
        frames: List of input frames.
    """

    metadata: ReplayMetadata = field(default_factory=ReplayMetadata)
    frames: List[InputFrame] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "frames": [f.to_dict() for f in self.frames],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReplayData:
        """Create from dictionary."""
        return cls(
            metadata=ReplayMetadata.from_dict(data.get("metadata", {})),
            frames=[InputFrame.from_dict(f) for f in data.get("frames", [])],
        )


class ReplayState(Enum):
    """Current state of the replay system."""

    IDLE = auto()  # Not recording or playing
    RECORDING = auto()  # Currently recording input
    PLAYING = auto()  # Currently playing back input
    PAUSED = auto()  # Playback is paused
