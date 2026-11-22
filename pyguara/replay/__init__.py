"""Replay system for deterministic input recording and playback.

Provides tools for recording game input and playing it back deterministically,
useful for debugging, testing, and sharing gameplay.
"""

from pyguara.replay.controls import ReplayControls
from pyguara.replay.library import ReplayEntry, ReplayLibrary
from pyguara.replay.player import ReplayPlayer
from pyguara.replay.recorder import ReplayRecorder
from pyguara.replay.serializer import (
    ReplaySerializer,
    load_replay,
    save_replay,
)
from pyguara.replay.types import (
    InputEventType,
    InputFrame,
    RecordedInputEvent,
    ReplayData,
    ReplayMetadata,
    ReplayState,
)

__all__ = [
    # Types
    "InputEventType",
    "InputFrame",
    "RecordedInputEvent",
    "ReplayData",
    "ReplayMetadata",
    "ReplayState",
    # Library
    "ReplayEntry",
    "ReplayLibrary",
    # Recorder
    "ReplayRecorder",
    # Player
    "ReplayControls",
    "ReplayPlayer",
    # Serializer
    "ReplaySerializer",
    "load_replay",
    "save_replay",
]
