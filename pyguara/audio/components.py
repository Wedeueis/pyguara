"""Audio components for entity-attached sound.

Provides components for entities that emit or play audio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pyguara.audio.types import AudioPriority
from pyguara.ecs.component import StrictComponent

if TYPE_CHECKING:
    pass


@dataclass
class AudioSource(StrictComponent):
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

    clip_path: str = ""
    volume: float = 1.0
    spatial: bool = True
    loop: bool = False
    auto_play: bool = False
    priority: AudioPriority = AudioPriority.NORMAL
    max_distance: float = 1000.0
    play_on_awake: bool = False  # Alias for auto_play

    # Runtime state (not serialized)
    _channel_id: int | None = field(default=None, repr=False, compare=False)
    _is_playing: bool = field(default=False, repr=False, compare=False)
    _stop_requested: bool = field(default=False, repr=False, compare=False)
    # Latches once auto_play has fired, so a one-shot sound that ends is not
    # immediately restarted by the auto_play path on the next frame.
    _auto_played: bool = field(default=False, repr=False, compare=False)

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
    def channel_id(self) -> int | None:
        """Get the current channel ID if playing."""
        return self._channel_id

    def on_detach(self) -> None:
        """Request stop when removed from entity.

        Signals AudioSourceSystem to clean up the playing sound.
        """
        self._stop_requested = True
        super().on_detach()


@dataclass
class AudioListener(StrictComponent):
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
class AudioEmitter(StrictComponent):
    """Component for one-shot sound effects at a position.

    Unlike AudioSource which is for persistent/looping sounds,
    AudioEmitter is for fire-and-forget sound effects.

    Attributes:
        clip_path: Path to the audio clip.
        volume: Volume level (0.0 to 1.0).
        played: Whether the sound has been played.
        remove_after_play: Whether to remove this component after playing.
    """

    clip_path: str = ""
    volume: float = 1.0
    played: bool = False
    remove_after_play: bool = True

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


# --- Requesting playback -------------------------------------------
#
# These set flags; `AudioSourceSystem` is what reaches the backend. They
# are free functions rather than methods because they mutate, which is
# the same line `Transform`/`set_parent` and `Health`/`apply_damage`
# draw. The issue that tracked this (#75, CC-6) recorded them as
# "reaching the audio backend from the component" -- they do not, and
# have not for some time.


def play(source: AudioSource) -> None:
    """Ask for `source` to start playing.

    A request, not the playback: `AudioSourceSystem` picks it up on its
    next tick and talks to the backend. A source with no clip is ignored,
    so a component configured but not yet given a clip stays silent
    rather than half-starting.

    Args:
        source: The source to start.
    """
    if not source.clip_path:
        return
    source._is_playing = True
    source._stop_requested = False


def stop(source: AudioSource) -> None:
    """Ask for `source` to stop.

    Args:
        source: The source to stop.
    """
    source._stop_requested = True


def emit(emitter: AudioEmitter) -> None:
    """Ask for `emitter`'s one-shot to play again.

    Clears the played latch; `AudioSourceSystem` fires it on its next
    tick and sets the latch back.

    Args:
        emitter: The emitter to re-fire.
    """
    emitter.played = False
