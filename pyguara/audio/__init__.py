"""Audio system to manage audio file loading and SFX and music reproduction.

Provides:
- Low-level audio playback via IAudioSystem
- High-level AudioManager for game audio
- Entity-attached audio via AudioSource component
- Spatial audio support
"""

from pyguara.audio.audio_source_system import AudioSourceSystem
from pyguara.audio.audio_system import (
    IAudioSystem,
    require_capability,
    resolve_loop_points,
)
from pyguara.audio.components import AudioEmitter, AudioListener, AudioSource
from pyguara.audio.exceptions import AudioError, UnsupportedAudioCapability
from pyguara.audio.manager import AudioManager
from pyguara.audio.types import (
    AudioBus,
    AudioBusManager,
    AudioBusType,
    AudioCapability,
    AudioEffect,
    AudioPriority,
    HighPassFilter,
    LowPassFilter,
    PlayingSoundInfo,
    Reverb,
    SoundHandle,
    SpatialAudioConfig,
    new_sound_handle,
)

__all__ = [
    # Core system
    "IAudioSystem",
    "AudioManager",
    "AudioSourceSystem",
    "require_capability",
    "resolve_loop_points",
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
    # Capabilities, handles and bus DSP
    "AudioCapability",
    "SoundHandle",
    "new_sound_handle",
    "AudioEffect",
    "LowPassFilter",
    "HighPassFilter",
    "Reverb",
    # Errors
    "AudioError",
    "UnsupportedAudioCapability",
]
