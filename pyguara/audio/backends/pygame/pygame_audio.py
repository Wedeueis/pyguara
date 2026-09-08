"""Pygame implementation of the Audio System with spatial audio and bus support."""

import contextlib
import math

import pygame

from pyguara.audio.types import (
    AudioBusManager,
    AudioBusType,
    AudioPriority,
    PlayingSoundInfo,
    SpatialAudioConfig,
)
from pyguara.common.types import Vector2
from pyguara.log import get_logger
from pyguara.resources.meta import AudioMeta
from pyguara.resources.types import AudioClip

logger = get_logger(__name__)


class PygameAudioSystem:
    """Pygame implementation for the PyGuara AudioSystem.

    Features:
    - Spatial audio with distance attenuation and stereo panning
    - Audio bus hierarchy (Master -> SFX/Music/Voice)
    - Priority-based channel management
    - Full volume control at bus and global levels
    """

    def __init__(
        self,
        frequency: int = 44100,
        size: int = -16,
        channels: int = 2,
        buffer: int = 512,
        num_channels: int = 32,
    ):
        """
        Initialize the Pygame mixer with advanced audio features.

        Args:
            frequency: Sample rate (44100 Hz is CD quality).
            size: Sample size (-16 is 16-bit signed).
            channels: Number of audio channels (2 for stereo).
            buffer: Buffer size (512 is low latency).
            num_channels: Number of mixer channels for simultaneous sounds.
        """
        pygame.mixer.init(frequency, size, channels, buffer)
        pygame.mixer.set_num_channels(num_channels)
        self._num_channels = num_channels

        # Bus management
        self._bus_manager = AudioBusManager()

        # Legacy volume properties (backed by bus manager)
        self._master_volume: float = 1.0
        self._sfx_volume: float = 1.0
        self._music_volume: float = 1.0

        # Spatial audio configuration
        self._spatial_config = SpatialAudioConfig()
        self._listener_position = Vector2(0, 0)

        # Channel tracking for priority management. `_channel_sounds` mirrors
        # `_playing_sounds` with the concrete Sound started on each channel, so
        # a recycled channel id can be told apart from the sound it used to
        # carry (see `is_channel_active`).
        self._playing_sounds: dict[int, PlayingSoundInfo] = {}
        self._channel_sounds: dict[int, pygame.mixer.Sound] = {}
        self._shut_down = False

        # Apply initial music volume
        pygame.mixer.music.set_volume(self._get_effective_music_volume())

    # ========== Spatial Audio ==========

    def play_sfx(
        self,
        clip: AudioClip,
        volume: float = 1.0,
        loops: int = 0,
        priority: AudioPriority = AudioPriority.NORMAL,
        bus: AudioBusType = AudioBusType.SFX,
    ) -> int | None:
        """Play a sound effect with priority and bus routing."""
        return self._play_sound(
            clip=clip,
            volume=volume,
            loops=loops,
            priority=priority,
            bus=bus,
            position=None,
        )

    def play_sfx_at_position(
        self,
        clip: AudioClip,
        source_pos: Vector2,
        listener_pos: Vector2,
        volume: float = 1.0,
        loops: int = 0,
        priority: AudioPriority = AudioPriority.NORMAL,
        bus: AudioBusType = AudioBusType.SFX,
    ) -> int | None:
        """Play a sound effect with spatial positioning."""
        # Calculate distance-based attenuation
        distance = math.sqrt(
            (source_pos.x - listener_pos.x) ** 2 + (source_pos.y - listener_pos.y) ** 2
        )
        attenuation = self._spatial_config.calculate_attenuation(distance)

        # Don't play if too far away
        if attenuation <= 0.001:
            return None

        # Calculate stereo panning
        pan = self._spatial_config.calculate_pan(source_pos, listener_pos)

        # Play with calculated volume
        spatial_volume = volume * attenuation

        channel_id = self._play_sound(
            clip=clip,
            volume=spatial_volume,
            loops=loops,
            priority=priority,
            bus=bus,
            position=source_pos,
            pan=pan,
        )

        return channel_id

    def _play_sound(
        self,
        clip: AudioClip,
        volume: float,
        loops: int,
        priority: AudioPriority,
        bus: AudioBusType,
        position: Vector2 | None,
        pan: float = 0.0,
    ) -> int | None:
        """Play a sound with all available options."""
        native_sound = clip.native_handle

        if not (hasattr(native_sound, "set_volume") and hasattr(native_sound, "play")):
            logger.error("Resource '%s' is not a valid Sound", clip.path)
            return None

        base_volume = max(0.0, min(1.0, volume))

        # Per-asset import gain from an AudioMeta sidecar (volume_db), if any.
        import_meta = clip.import_meta
        import_gain = (
            import_meta.get_volume_multiplier()
            if isinstance(import_meta, AudioMeta)
            else 1.0
        )

        # Calculate effective volume through bus hierarchy
        bus_name = self._bus_manager.get_bus_for_type(bus)
        bus_volume = self._bus_manager.get_effective_volume(bus_name)
        effective_volume = max(0.0, min(1.0, base_volume * import_gain * bus_volume))

        # Find available channel or steal one
        channel = self._get_available_channel(priority)
        if channel is None:
            logger.debug("No available channels for sound '%s'", clip.path)
            return None

        try:
            # Loudness and stereo pan go on the CHANNEL, never the Sound: the
            # Sound object is shared by every concurrent play of the same clip
            # (ResourceManager caches it), so `sound.set_volume()` for one
            # spatial instance silently rewrites every other one.
            channel.play(native_sound, loops=loops)
            self._set_channel_volume(channel, effective_volume, pan)
            channel_id: int = channel.id
        except pygame.error as e:
            logger.error("Error playing sound '%s': %s", clip.path, e, exc_info=True)
            return None

        # Track playing sound
        self._playing_sounds[channel_id] = PlayingSoundInfo(
            channel_id=channel_id,
            clip_path=clip.path,
            priority=priority,
            bus=bus,
            base_volume=base_volume,
            position=position,
            is_spatial=position is not None,
        )
        self._channel_sounds[channel_id] = native_sound

        return channel_id

    def _get_available_channel(
        self, priority: AudioPriority
    ) -> pygame.mixer.Channel | None:
        """Get an available channel, potentially stealing from lower priority sounds."""
        # First, try to find a free channel
        # Note: pygame.mixer.find_channel() can return None if no channels available
        channel: pygame.mixer.Channel | None = pygame.mixer.find_channel()
        if channel is not None:
            return channel

        # No free channels - try priority-based stealing
        return self._steal_channel(priority)

    def _steal_channel(self, priority: AudioPriority) -> pygame.mixer.Channel | None:
        """Steal a channel from a lower priority sound."""
        # Find the lowest priority sound that's lower than our priority
        lowest_priority = priority.value
        lowest_channel_id: int | None = None
        finished_channels: list[int] = []

        for channel_id, info in self._playing_sounds.items():
            # Check if channel is still playing
            try:
                channel = pygame.mixer.Channel(channel_id)
                if not channel.get_busy():
                    # Channel finished, mark for cleanup
                    finished_channels.append(channel_id)
                    continue
            except pygame.error:
                finished_channels.append(channel_id)
                continue

            # Check priority for stealing
            if info.priority.value < lowest_priority:
                lowest_priority = info.priority.value
                lowest_channel_id = channel_id

        # Clean up finished channels
        for channel_id in finished_channels:
            self._forget_channel(channel_id)

        # Return a finished channel if available
        if finished_channels:
            try:
                return pygame.mixer.Channel(finished_channels[0])
            except pygame.error:
                pass

        # Steal if we found a lower priority sound
        if lowest_channel_id is not None:
            try:
                channel = pygame.mixer.Channel(lowest_channel_id)
                channel.stop()
                self._forget_channel(lowest_channel_id)
                logger.debug(
                    "Stole channel %d from lower priority sound", lowest_channel_id
                )
                return channel
            except pygame.error:
                pass

        return None

    @staticmethod
    def _channel_stereo(volume: float, pan: float) -> tuple[float, float]:
        """Split a mono volume into (left, right) channel gains for a pan.

        Args:
            volume: Mono loudness (0.0 to 1.0).
            pan: -1.0 = full left, 0.0 = centred, 1.0 = full right.

        Returns:
            (left, right) gains, each `volume` scaled by that side's share.
        """
        pan = max(-1.0, min(1.0, pan))
        if pan >= 0.0:
            return volume * (1.0 - pan), volume
        return volume, volume * (1.0 + pan)

    @classmethod
    def _set_channel_volume(
        cls, channel: pygame.mixer.Channel, volume: float, pan: float
    ) -> None:
        """Apply loudness + pan to a channel.

        A centred sound uses single-argument ``set_volume``, which also clears
        any left/right split the channel kept from a previous, panned sound --
        channels are recycled, so without this a centred sound inherits the
        last one's hard pan.
        """
        if abs(pan) < 1e-3:
            channel.set_volume(volume)
        else:
            left, right = cls._channel_stereo(volume, pan)
            channel.set_volume(left, right)

    def _forget_channel(self, channel_id: int) -> None:
        """Drop all tracking for a channel that is no longer ours."""
        self._playing_sounds.pop(channel_id, None)
        self._channel_sounds.pop(channel_id, None)

    def is_channel_active(self, channel: int) -> bool:
        """Return True only while the sound this system started is still playing.

        Reaps the tracking tables as a side effect when the sound has ended or
        the channel has been recycled by an unrelated one.
        """
        expected = self._channel_sounds.get(channel)
        if expected is not None:
            try:
                pg_channel = pygame.mixer.Channel(channel)
                if pg_channel.get_busy() and pg_channel.get_sound() is expected:
                    return True
            except pygame.error:
                pass
        self._forget_channel(channel)
        return False

    def set_channel_mix(self, channel: int, attenuation: float, pan: float) -> None:
        """Update volume attenuation and stereo pan for an already-playing channel."""
        info = self._playing_sounds.get(channel)
        if info is None or not self.is_channel_active(channel):
            return

        bus_name = self._bus_manager.get_bus_for_type(info.bus)
        bus_volume = self._bus_manager.get_effective_volume(bus_name)
        attenuation = max(0.0, min(1.0, attenuation))
        effective_volume = info.base_volume * attenuation * bus_volume

        with contextlib.suppress(pygame.error):
            self._set_channel_volume(
                pygame.mixer.Channel(channel), effective_volume, pan
            )

    # ========== Basic SFX Control ==========

    def stop_sfx(self, channel: int) -> None:
        """Stop a specific sound effect channel."""
        with contextlib.suppress(pygame.error):
            pygame.mixer.Channel(channel).stop()
        self._forget_channel(channel)

    def pause_sfx(self) -> None:
        """Pause all sound effects."""
        pygame.mixer.pause()

    def resume_sfx(self) -> None:
        """Resume all paused sound effects."""
        pygame.mixer.unpause()

    # ========== Music Control ==========

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """Stream background music from disk."""
        try:
            pygame.mixer.music.load(path)
            loops = -1 if loop else 0
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
            pygame.mixer.music.set_volume(self._get_effective_music_volume())
        except pygame.error as e:
            logger.error("Failed to play music '%s': %s", path, e, exc_info=True)

    def stop_music(self, fade_ms: int = 1000) -> None:
        """Stop the currently playing music."""
        pygame.mixer.music.fadeout(fade_ms)

    def pause_music(self) -> None:
        """Pause the currently playing music."""
        pygame.mixer.music.pause()

    def resume_music(self) -> None:
        """Resume the paused music."""
        pygame.mixer.music.unpause()

    def is_music_playing(self) -> bool:
        """Check if music is currently playing."""
        return bool(pygame.mixer.music.get_busy())

    # ========== Volume Control (Legacy API) ==========

    def set_master_volume(self, volume: float) -> None:
        """Set the global master volume."""
        self._master_volume = max(0.0, min(1.0, volume))
        self._bus_manager.set_bus_volume("master", self._master_volume)
        pygame.mixer.music.set_volume(self._get_effective_music_volume())

    def set_sfx_volume(self, volume: float) -> None:
        """Set the sound effects volume."""
        self._sfx_volume = max(0.0, min(1.0, volume))
        self._bus_manager.set_bus_volume("sfx", self._sfx_volume)

    def set_music_volume(self, volume: float) -> None:
        """Set the music volume."""
        self._music_volume = max(0.0, min(1.0, volume))
        self._bus_manager.set_bus_volume("music", self._music_volume)
        pygame.mixer.music.set_volume(self._get_effective_music_volume())

    def get_master_volume(self) -> float:
        """Get the current master volume."""
        return self._master_volume

    def get_sfx_volume(self) -> float:
        """Get the current SFX volume."""
        return self._sfx_volume

    def get_music_volume(self) -> float:
        """Get the current music volume."""
        return self._music_volume

    def _get_effective_music_volume(self) -> float:
        """Calculate effective music volume from bus hierarchy."""
        return self._bus_manager.get_effective_volume("music")

    # ========== Bus Management ==========

    def set_bus_volume(self, bus: AudioBusType, volume: float) -> None:
        """Set volume for a specific audio bus."""
        bus_name = self._bus_manager.get_bus_for_type(bus)
        self._bus_manager.set_bus_volume(bus_name, volume)

        # Update music volume if music bus changed
        if bus in (AudioBusType.MASTER, AudioBusType.MUSIC):
            pygame.mixer.music.set_volume(self._get_effective_music_volume())

    def get_bus_volume(self, bus: AudioBusType) -> float:
        """Get the volume of a specific audio bus."""
        bus_name = self._bus_manager.get_bus_for_type(bus)
        bus_obj = self._bus_manager.get_bus(bus_name)
        return bus_obj.volume if bus_obj else 1.0

    def set_bus_muted(self, bus: AudioBusType, muted: bool) -> None:
        """Mute or unmute a specific audio bus."""
        bus_name = self._bus_manager.get_bus_for_type(bus)
        self._bus_manager.set_bus_muted(bus_name, muted)

        # Update music if relevant bus
        if bus in (AudioBusType.MASTER, AudioBusType.MUSIC):
            pygame.mixer.music.set_volume(self._get_effective_music_volume())

    def is_bus_muted(self, bus: AudioBusType) -> bool:
        """Check if a bus is muted."""
        bus_name = self._bus_manager.get_bus_for_type(bus)
        bus_obj = self._bus_manager.get_bus(bus_name)
        return bus_obj.muted if bus_obj else False

    # ========== Listener Management ==========

    def set_listener_position(self, position: Vector2) -> None:
        """Set the listener position for spatial audio."""
        self._listener_position = position

    def get_listener_position(self) -> Vector2:
        """Get the current listener position."""
        return self._listener_position

    # ========== Spatial Config ==========

    def set_spatial_config(self, config: SpatialAudioConfig) -> None:
        """Set spatial audio configuration."""
        self._spatial_config = config

    def get_spatial_config(self) -> SpatialAudioConfig:
        """Get current spatial audio configuration."""
        return self._spatial_config

    # ========== Channel Cleanup ==========

    def cleanup_finished_channels(self) -> None:
        """Remove tracking for channels that have finished playing."""
        for channel_id in list(self._playing_sounds):
            self.is_channel_active(channel_id)  # reaps as a side effect

    def shutdown(self) -> None:
        """Stop all audio and release the mixer device. Idempotent."""
        if self._shut_down:
            return
        self._shut_down = True
        try:
            pygame.mixer.stop()
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except pygame.error:
            logger.debug("pygame.mixer already torn down", exc_info=True)
        self._playing_sounds.clear()
        self._channel_sounds.clear()

    def get_active_sound_count(self) -> int:
        """Get number of currently playing sounds."""
        self.cleanup_finished_channels()
        return len(self._playing_sounds)
