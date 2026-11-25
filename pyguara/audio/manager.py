"""High-level Audio Manager for game audio management."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.exceptions import UnsupportedAudioCapability
from pyguara.audio.types import AudioCapability, SoundHandle
from pyguara.common.random import RandomStream
from pyguara.events.dispatcher import EventDispatcher
from pyguara.log import get_logger
from pyguara.random.service import RandomService
from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import AudioClip

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SfxLimit:
    """How much of one sound may play at once. See `AudioManager.set_sfx_limit`.

    Attributes:
        max_voices: The most copies playing together, or None for no cap.
        min_interval: Seconds that must pass between two starts.
    """

    max_voices: int | None = None
    min_interval: float = 0.0


VARIATION_STREAM = "audio.variation"
"""The `RandomService` stream sound variations draw from."""


@dataclass(frozen=True, slots=True)
class SoundVariation:
    """Several takes of one sound, and how much each play may differ.

    A footstep or a hit heard hundreds of times a run sounds mechanical as
    one clip at one pitch. Each play picks a take and a pitch and volume
    in these ranges. See `AudioManager.set_sfx_variation`.

    Attributes:
        paths: The takes, as `play_sfx` names them.
        pitch: The lowest and highest playback rate.
        volume: The lowest and highest volume, multiplying the play's own.
        avoid_repeat: Never pick the take played last, when there are two
            or more.
    """

    paths: tuple[str, ...]
    pitch: tuple[float, float] = (1.0, 1.0)
    volume: tuple[float, float] = (1.0, 1.0)
    avoid_repeat: bool = True

    def __post_init__(self) -> None:
        """Check the takes and ranges.

        Raises:
            ValueError: If there are no takes, or a range is not finite,
                runs backwards, has a pitch at or below 0, or a volume
                outside 0 to 1.
        """
        paths: object = self.paths
        if not isinstance(paths, tuple) or not paths:
            raise ValueError("a sound variation needs a tuple of at least one path")
        for name, (low, high) in (("pitch", self.pitch), ("volume", self.volume)):
            if not (math.isfinite(low) and math.isfinite(high)) or low > high:
                raise ValueError(
                    f"{name} must be a finite (low, high) range, got {(low, high)}"
                )
        if self.pitch[0] <= 0.0:
            raise ValueError(f"pitch must be above 0, got {self.pitch}")
        if self.volume[0] < 0.0 or self.volume[1] > 1.0:
            raise ValueError(f"volume must be within 0 to 1, got {self.volume}")

    @property
    def varies_pitch(self) -> bool:
        """Whether any play is at a rate other than 1."""
        return self.pitch != (1.0, 1.0)


class AudioManager:
    """High-level audio manager that coordinates the audio system.

    Provides:
    - Convenient resource loading and playback
    - Volume management (master, SFX, music)
    - Music playback control (play, pause, stop)
    - Sound effect playback with tracking
    - Event integration for audio state changes

    Example:
        >>> audio_mgr = AudioManager(audio_system, resource_mgr, event_dispatcher)
        >>> audio_mgr.play_sfx("sounds/jump.wav", volume=0.8)
        >>> audio_mgr.play_music("music/bgm.ogg", loop=True)
        >>> audio_mgr.set_master_volume(0.7)
    """

    def __init__(
        self,
        audio_system: IAudioSystem,
        resource_manager: ResourceManager | None = None,
        event_dispatcher: EventDispatcher | None = None,
        clock: Callable[[], float] = time.monotonic,
        random: RandomService | None = None,
    ) -> None:
        """Initialize the audio manager.

        Args:
            audio_system: The underlying audio system implementation.
            resource_manager: Optional resource manager for loading audio clips.
            event_dispatcher: Optional event dispatcher for audio events.
            clock: Seconds, for `SfxLimit.min_interval`. Real time, because a
                sound is heard in real time; a test passes its own.
            random: Where sound variations draw from, as its
                `VARIATION_STREAM` stream, apart from gameplay's. Without
                one, an unseeded stream of the manager's own.
        """
        self._audio_system = audio_system
        self._resource_manager = resource_manager
        self._event_dispatcher = event_dispatcher

        # Track loaded audio clips
        self._loaded_clips: dict[str, AudioClip] = {}

        # Current music track
        self._current_music: str | None = None

        # Per-sound limits, by clip path, and what each limited sound is doing.
        self._clock = clock
        self._limits: dict[str, SfxLimit] = {}
        self._voices: dict[str, list[SoundHandle]] = {}
        self._last_start: dict[str, float] = {}

        # Sound variations by name, the take each played last, and the
        # stream every pick is drawn from.
        self._variations: dict[str, SoundVariation] = {}
        self._last_take: dict[str, int] = {}
        self._variation_random = (
            random.stream(VARIATION_STREAM) if random is not None else RandomStream()
        )

    # ========== Capabilities ==========

    @property
    def capabilities(self) -> AudioCapability:
        """What the backend underneath can do beyond plain playback.

        Read this before asking for `pitch` or loop points if the game
        should degrade rather than fail: on a backend without them, those
        arguments raise `UnsupportedAudioCapability`.

        Returns:
            The flags the backend honours.
        """
        return self._audio_system.capabilities

    # ========== SFX Methods ==========

    def play_sfx(
        self,
        path: str,
        volume: float = 1.0,
        loops: int = 0,
        pitch: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> SoundHandle | None:
        """Play a sound effect by path.

        Automatically loads the clip if not already loaded.

        Args:
            path: Path to the sound file.
            volume: Playback volume (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).
            pitch: Playback rate multiplier; needs `AudioCapability.PITCH`
                for any value other than 1.0.
            loop_start: Seconds into the clip a loop returns to; needs
                `AudioCapability.LOOP_POINTS`.
            loop_end: Seconds into the clip a loop restarts from.

        Returns:
            A handle for the playing sound, or None if the clip could not
            be loaded, its `SfxLimit` held it back, or no channel was free.

        Raises:
            UnsupportedAudioCapability: If `pitch` or the loop points ask
                for something the backend cannot do.
        """
        clip = self._get_clip(path)
        if clip:
            return self.play_sfx_clip(
                clip,
                volume,
                loops,
                pitch=pitch,
                loop_start=loop_start,
                loop_end=loop_end,
            )
        return None

    def play_sfx_clip(
        self,
        clip: AudioClip,
        volume: float = 1.0,
        loops: int = 0,
        pitch: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> SoundHandle | None:
        """Play a pre-loaded sound effect clip.

        Args:
            clip: The audio clip to play.
            volume: Playback volume (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).
            pitch: Playback rate multiplier; see `play_sfx`.
            loop_start: Seconds into the clip a loop returns to.
            loop_end: Seconds into the clip a loop restarts from.

        Returns:
            A handle for the playing sound, or None if its `SfxLimit` held it
            back or no channel was free.

        Raises:
            UnsupportedAudioCapability: If `pitch` or the loop points ask
                for something the backend cannot do.
        """
        limit = self._limits.get(clip.path)
        now = self._clock()
        if limit is not None and not self._admits(clip.path, limit, now):
            return None
        sound = self._audio_system.play_sfx(
            clip,
            volume,
            loops,
            pitch=pitch,
            loop_start=loop_start,
            loop_end=loop_end,
        )
        if limit is not None and sound is not None:
            self._last_start[clip.path] = now
            if limit.max_voices is not None:
                self._voices.setdefault(clip.path, []).append(sound)
        return sound

    def set_sfx_limit(
        self, path: str, *, max_voices: int | None = None, min_interval: float = 0.0
    ) -> None:
        """Limit how much of one sound plays at once.

        Ten hits landing in one frame would otherwise start ten copies of the
        same clip together, which is one sound, much louder. A play the limit
        holds back is dropped, not queued: the copies already playing are the
        sound of that moment, and a late one would be heard after it.

        Both arguments at their defaults remove the limit.

        Args:
            path: The sound, as `play_sfx` names it. `play_sfx_clip` is
                limited by its clip's path.
            max_voices: The most copies playing together, or None for no cap.
            min_interval: Seconds that must pass between two starts.

        Raises:
            ValueError: If `max_voices` is below 1, or `min_interval` is
                negative or not finite.
        """
        if max_voices is not None and max_voices < 1:
            raise ValueError(f"max_voices must be at least 1, got {max_voices}.")
        if not math.isfinite(min_interval) or min_interval < 0.0:
            raise ValueError(
                f"min_interval must be a finite number of seconds, at least 0, "
                f"got {min_interval}."
            )
        self._voices.pop(path, None)
        self._last_start.pop(path, None)
        if max_voices is None and min_interval == 0.0:
            self._limits.pop(path, None)
            return
        self._limits[path] = SfxLimit(max_voices, min_interval)

    def get_sfx_limit(self, path: str) -> SfxLimit | None:
        """Return the limit set on a sound, or None if it has none."""
        return self._limits.get(path)

    def _admits(self, path: str, limit: SfxLimit, now: float) -> bool:
        last = self._last_start.get(path)
        if last is not None and now - last < limit.min_interval:
            return False
        if limit.max_voices is None:
            return True
        playing = [
            sound
            for sound in self._voices.get(path, ())
            if self._audio_system.is_sound_active(sound)
        ]
        self._voices[path] = playing
        return len(playing) < limit.max_voices

    def set_sfx_variation(self, name: str, variation: SoundVariation | None) -> None:
        """Name a set of takes `play_sfx_variation` picks from, or forget one.

        Each take is still its own sound to `set_sfx_limit`, so a limit on
        a take holds back only that take.

        Args:
            name: What `play_sfx_variation` calls it.
            variation: The takes and ranges, or None to remove the name.

        Raises:
            UnsupportedAudioCapability: If the variation changes pitch and
                the backend cannot.
        """
        self._last_take.pop(name, None)
        if variation is None:
            self._variations.pop(name, None)
            return
        if variation.varies_pitch and not (self.capabilities & AudioCapability.PITCH):
            raise UnsupportedAudioCapability(
                AudioCapability.PITCH, type(self._audio_system).__name__
            )
        self._variations[name] = variation

    def get_sfx_variation(self, name: str) -> SoundVariation | None:
        """Return the variation set under a name, or None if there is none."""
        return self._variations.get(name)

    def play_sfx_variation(self, name: str, volume: float = 1.0) -> SoundHandle | None:
        """Play one take of a named variation, at a picked pitch and volume.

        Args:
            name: As `set_sfx_variation` named it.
            volume: The play's volume, which the picked volume multiplies.

        Returns:
            A handle for the playing sound, or None as `play_sfx` returns it.

        Raises:
            KeyError: If no variation has that name.
        """
        variation = self._variations.get(name)
        if variation is None:
            raise KeyError(f"no sound variation is named {name!r}")
        draw = self._variation_random
        count = len(variation.paths)
        last = self._last_take.get(name)
        if variation.avoid_repeat and count > 1 and last is not None:
            take = draw.randint(0, count - 2)
            take += take >= last
        else:
            take = draw.randint(0, count - 1)
        pitch = draw.uniform(*variation.pitch)
        loudness = draw.uniform(*variation.volume)
        self._last_take[name] = take
        return self.play_sfx(variation.paths[take], volume * loudness, pitch=pitch)

    def stop_sfx(self, sound: SoundHandle) -> None:
        """Stop one playing sound effect.

        Args:
            sound: The handle returned by play_sfx.
        """
        self._audio_system.stop_sfx(sound)

    def pause_all_sfx(self) -> None:
        """Pause all currently playing sound effects."""
        self._audio_system.pause_sfx()

    def resume_all_sfx(self) -> None:
        """Resume all paused sound effects."""
        self._audio_system.resume_sfx()

    # ========== Music Methods ==========

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """Play background music from a file.

        Args:
            path: Path to the music file.
            loop: Whether to loop the music.
            fade_ms: Fade-in duration in milliseconds.
        """
        self._audio_system.play_music(path, loop, fade_ms)
        self._current_music = path

    def stop_music(self, fade_ms: int = 1000) -> None:
        """Stop the currently playing music.

        Args:
            fade_ms: Fade-out duration in milliseconds.
        """
        self._audio_system.stop_music(fade_ms)
        self._current_music = None

    def pause_music(self) -> None:
        """Pause the currently playing music."""
        self._audio_system.pause_music()

    def resume_music(self) -> None:
        """Resume the paused music."""
        self._audio_system.resume_music()

    def is_music_playing(self) -> bool:
        """Check if music is currently playing."""
        return self._audio_system.is_music_playing()

    def get_current_music(self) -> str | None:
        """Get the path of the currently playing music, if any."""
        return self._current_music

    # ========== Volume Control ==========

    def set_master_volume(self, volume: float) -> None:
        """Set the master volume (affects both SFX and music).

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._audio_system.set_master_volume(volume)

    def set_sfx_volume(self, volume: float) -> None:
        """Set the sound effects volume.

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._audio_system.set_sfx_volume(volume)

    def set_music_volume(self, volume: float) -> None:
        """Set the music volume.

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._audio_system.set_music_volume(volume)

    def get_master_volume(self) -> float:
        """Get the current master volume."""
        return self._audio_system.get_master_volume()

    def get_sfx_volume(self) -> float:
        """Get the current SFX volume."""
        return self._audio_system.get_sfx_volume()

    def get_music_volume(self) -> float:
        """Get the current music volume."""
        return self._audio_system.get_music_volume()

    # ========== Resource Management ==========

    def preload_sfx(self, path: str) -> AudioClip | None:
        """Preload a sound effect into memory.

        Args:
            path: Path to the sound file.

        Returns:
            The loaded AudioClip if successful, None otherwise.
        """
        return self._get_clip(path)

    def unload_sfx(self, path: str) -> None:
        """Unload a previously loaded sound effect.

        Args:
            path: Path to the sound file to unload.
        """
        if path in self._loaded_clips:
            del self._loaded_clips[path]

    def _get_clip(self, path: str) -> AudioClip | None:
        """Get an audio clip, loading it if necessary.

        Args:
            path: Path to the audio file.

        Returns:
            The AudioClip if successful, None otherwise.
        """
        # Check cache first
        if path in self._loaded_clips:
            return self._loaded_clips[path]

        # Try to load via resource manager
        if self._resource_manager:
            try:
                clip = self._resource_manager.load(path, AudioClip)  # type: ignore[type-abstract]
                self._loaded_clips[path] = clip
                return clip
            except Exception as e:
                logger.error(
                    "Failed to load audio clip '%s': %s", path, e, exc_info=True
                )
                return None

        logger.warning("No resource manager available to load '%s'", path)
        return None

    # ========== Cleanup ==========

    def cleanup(self) -> None:
        """Stop music and drop cached clips.

        Playing sound effects are owned by ``AudioSourceSystem`` and released
        by its own ``cleanup()``; tearing down the shared mixer device is
        ``IAudioSystem.shutdown()``, called at application shutdown.
        """
        self.stop_music(fade_ms=0)
        self._loaded_clips.clear()
        self._current_music = None
        self._voices.clear()
        self._last_start.clear()
