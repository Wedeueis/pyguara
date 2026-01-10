"""High-level Audio Manager for game audio management."""

from typing import Optional, Dict
from pyguara.audio.audio_system import IAudioSystem
from pyguara.resources.types import AudioClip
from pyguara.resources.manager import ResourceManager
from pyguara.events.dispatcher import EventDispatcher


class AudioManager:
    """
    High-level audio manager that coordinates the audio system.

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
        resource_manager: Optional[ResourceManager] = None,
        event_dispatcher: Optional[EventDispatcher] = None,
    ) -> None:
        """
        Initialize the audio manager.

        Args:
            audio_system: The underlying audio system implementation.
            resource_manager: Optional resource manager for loading audio clips.
            event_dispatcher: Optional event dispatcher for audio events.
        """
        self._audio_system = audio_system
        self._resource_manager = resource_manager
        self._event_dispatcher = event_dispatcher

        # Track loaded audio clips
        self._loaded_clips: Dict[str, AudioClip] = {}

        # Track active sound channels
        self._active_channels: Dict[str, int] = {}

        # Current music track
        self._current_music: Optional[str] = None

    # ========== SFX Methods ==========

    def play_sfx(self, path: str, volume: float = 1.0, loops: int = 0) -> Optional[int]:
        """
        Play a sound effect by path.

        Automatically loads the clip if not already loaded.

        Args:
            path: Path to the sound file.
            volume: Playback volume (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).

        Returns:
            Channel ID if successful, None otherwise.
        """
        clip = self._get_clip(path)
        if clip:
            return self._audio_system.play_sfx(clip, volume, loops)
        return None

    def play_sfx_clip(
        self, clip: AudioClip, volume: float = 1.0, loops: int = 0
    ) -> Optional[int]:
        """
        Play a pre-loaded sound effect clip.

        Args:
            clip: The audio clip to play.
            volume: Playback volume (0.0 to 1.0).
            loops: Number of times to loop (-1 for infinite).

        Returns:
            Channel ID if successful, None otherwise.
        """
        return self._audio_system.play_sfx(clip, volume, loops)

    def stop_sfx(self, channel: int) -> None:
        """
        Stop a specific sound effect channel.

        Args:
            channel: The channel ID returned by play_sfx.
        """
        self._audio_system.stop_sfx(channel)

    def pause_all_sfx(self) -> None:
        """Pause all currently playing sound effects."""
        self._audio_system.pause_sfx()

    def resume_all_sfx(self) -> None:
        """Resume all paused sound effects."""
        self._audio_system.resume_sfx()

    # ========== Music Methods ==========

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """
        Play background music from a file.

        Args:
            path: Path to the music file.
            loop: Whether to loop the music.
            fade_ms: Fade-in duration in milliseconds.
        """
        self._audio_system.play_music(path, loop, fade_ms)
        self._current_music = path

    def stop_music(self, fade_ms: int = 1000) -> None:
        """
        Stop the currently playing music.

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

    def get_current_music(self) -> Optional[str]:
        """Get the path of the currently playing music, if any."""
        return self._current_music

    # ========== Volume Control ==========

    def set_master_volume(self, volume: float) -> None:
        """
        Set the master volume (affects both SFX and music).

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._audio_system.set_master_volume(volume)

    def set_sfx_volume(self, volume: float) -> None:
        """
        Set the sound effects volume.

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._audio_system.set_sfx_volume(volume)

    def set_music_volume(self, volume: float) -> None:
        """
        Set the music volume.

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

    def preload_sfx(self, path: str) -> Optional[AudioClip]:
        """
        Preload a sound effect into memory.

        Args:
            path: Path to the sound file.

        Returns:
            The loaded AudioClip if successful, None otherwise.
        """
        return self._get_clip(path)

    def unload_sfx(self, path: str) -> None:
        """
        Unload a previously loaded sound effect.

        Args:
            path: Path to the sound file to unload.
        """
        if path in self._loaded_clips:
            del self._loaded_clips[path]

    def _get_clip(self, path: str) -> Optional[AudioClip]:
        """
        Get an audio clip, loading it if necessary.

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
                print(f"[AudioManager] Failed to load audio clip '{path}': {e}")
                return None

        print(f"[AudioManager] No resource manager available to load '{path}'")
        return None

    # ========== Cleanup ==========

    def cleanup(self) -> None:
        """Clean up resources and stop all audio."""
        self.stop_music(fade_ms=0)
        self._loaded_clips.clear()
        self._active_channels.clear()
        self._current_music = None
