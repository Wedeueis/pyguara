"""Audio system to manage audio file loading and SFX and music reproduction.

Provides:
- Low-level audio playback via IAudioSystem
- High-level AudioManager for game audio
- Entity-attached audio via AudioSource component
- Spatial audio support
"""

from pyguara.audio.audio_source_system import AudioSourceSystem
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.components import AudioEmitter, AudioListener, AudioSource
from pyguara.audio.manager import AudioManager
from pyguara.audio.types import (
    AudioBus,
    AudioBusManager,
    AudioBusType,
    AudioPriority,
    PlayingSoundInfo,
    SpatialAudioConfig,
)

__all__ = [
    # Core system
    "IAudioSystem",
    "AudioManager",
    "AudioSourceSystem",
    # Components
    "AudioSource",
    "AudioListener",
    "AudioEmitter",
    # Types
    "AudioBus",
    "AudioBusManager",
    "AudioBusType",
    "AudioPriority",
    "PlayingSoundInfo",
    "SpatialAudioConfig",
]
