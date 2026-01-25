"""Audio components for entity-attached sound.

Provides components for entities that emit or play audio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from pyguara.audio.types import AudioPriority
from pyguara.ecs.component import BaseComponent

if TYPE_CHECKING:
    pass


@dataclass
class AudioSource(BaseComponent):
    """Component for entities that can play audio.

    Attaches audio playback capability to an entity, allowing sounds
    to follow the entity's position (spatial audio) and automatically
    clean up when the entity is destroyed.

    Attributes:
        clip_path: Path to the audio clip to play.
        volume: Base volume level (0.0 to 1.0).
        spatial: Whether to use spatial audio (position-based).
        loop: Whether to loop the sound.
        auto_play: Whether to automatically play when component is added.
        priority: Audio priority for channel management.
        max_distance: Maximum distance for spatial attenuation.
        play_on_awake: Alias for auto_play (Unity-style naming).
    """

    # Allow play/stop methods - these are intentional convenience methods
    _allow_methods: bool = True

    clip_path: str = ""
    volume: float = 1.0
    spatial: bool = True
    loop: bool = False
    auto_play: bool = False
    priority: AudioPriority = AudioPriority.NORMAL
    max_distance: float = 1000.0
    play_on_awake: bool = False  # Alias for auto_play

    # Runtime state (not serialized)
    _channel_id: Optional[int] = field(default=None, repr=False, compare=False)
    _is_playing: bool = field(default=False, repr=False, compare=False)
    _stop_requested: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()
        # Handle play_on_awake alias
        if self.play_on_awake:
            self.auto_play = True

    @property
    def is_playing(self) -> bool:
        """Check if the audio source is currently playing."""
        return self._is_playing

    @property
    def channel_id(self) -> Optional[int]:
        """Get the current channel ID if playing."""
        return self._channel_id

    def play(self) -> None:
        """Request to start playing the audio.

        The actual playback is handled by AudioSourceSystem.
        """
        if not self.clip_path:
            return
        self._is_playing = True
        self._stop_requested = False

    def stop(self) -> None:
        """Request to stop playing the audio.

        The actual stop is handled by AudioSourceSystem.
        """
        self._stop_requested = True

    def on_detach(self) -> None:
        """Request stop when removed from entity.

        Signals AudioSourceSystem to clean up the playing sound.
        """
        self._stop_requested = True
        super().on_detach()


@dataclass
class AudioListener(BaseComponent):
    """Component marking an entity as the audio listener.

    There should typically only be one AudioListener in a scene.
    The listener's position is used for spatial audio calculations.

    Attributes:
        active: Whether this listener is active.
    """

    active: bool = True

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class AudioEmitter(BaseComponent):
    """Component for one-shot sound effects at a position.

    Unlike AudioSource which is for persistent/looping sounds,
    AudioEmitter is for fire-and-forget sound effects.

    Attributes:
        clip_path: Path to the audio clip.
        volume: Volume level (0.0 to 1.0).
        played: Whether the sound has been played.
        remove_after_play: Whether to remove this component after playing.
    """

    # Allow emit method - intentional convenience method
    _allow_methods: bool = True

    clip_path: str = ""
    volume: float = 1.0
    played: bool = False
    remove_after_play: bool = True

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()

    def emit(self) -> None:
        """Request to play the sound effect.

        The actual playback is handled by AudioSourceSystem.
        """
        self.played = False
