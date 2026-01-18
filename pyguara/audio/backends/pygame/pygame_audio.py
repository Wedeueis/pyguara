"""Pygame implementation of the Audio System with spatial audio and bus support."""

import logging
import math
import pygame
from typing import Optional, Dict, List

from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.types import (
    AudioPriority,
    AudioBusType,
    AudioBusManager,
    SpatialAudioConfig,
    PlayingSoundInfo,
)
from pyguara.common.types import Vector2
from pyguara.resources.types import AudioClip

logger = logging.getLogger(__name__)


class PygameAudioSystem(IAudioSystem):
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

        # Channel tracking for priority management
        self._playing_sounds: Dict[int, PlayingSoundInfo] = {}

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
    ) -> Optional[int]:
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
    ) -> Optional[int]:
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
        position: Optional[Vector2],
        pan: float = 0.0,
    ) -> Optional[int]:
        """Play a sound with all available options."""
        try:
            native_sound = clip.native_handle

            if not (
                hasattr(native_sound, "set_volume") and hasattr(native_sound, "play")
            ):
                logger.error("Resource '%s' is not a valid Sound", clip.path)
                return None

            # Calculate effective volume through bus hierarchy
            bus_name = self._bus_manager.get_bus_for_type(bus)
            bus_volume = self._bus_manager.get_effective_volume(bus_name)
            effective_volume = volume * bus_volume

            # Find available channel or steal one
            channel = self._get_available_channel(priority)
            if channel is None:
                logger.debug("No available channels for sound '%s'", clip.path)
                return None

            # Set volume on the sound
            native_sound.set_volume(effective_volume)

            # Play on specific channel
            played_channel = native_sound.play(loops=loops)
            if played_channel is None:
                return None

            channel_id: int = played_channel.get_id()

            # Apply stereo panning if supported and needed
            if abs(pan) > 0.01:
                self._apply_pan(played_channel, pan)

            # Track playing sound
            self._playing_sounds[channel_id] = PlayingSoundInfo(
                channel_id=channel_id,
                clip_path=clip.path,
                priority=priority,
                bus=bus,
                base_volume=volume,
                position=position,
                is_spatial=position is not None,
            )

            return channel_id

        except (AttributeError, Exception) as e:
            logger.error("Error playing sound '%s': %s", clip.path, e, exc_info=True)
            return None

    def _get_available_channel(
        self, priority: AudioPriority
    ) -> Optional[pygame.mixer.Channel]:
        """Get an available channel, potentially stealing from lower priority sounds."""
        # First, try to find a free channel
        # Note: pygame.mixer.find_channel() can return None if no channels available
        channel: Optional[pygame.mixer.Channel] = pygame.mixer.find_channel()
        if channel is not None:
            return channel

        # No free channels - try priority-based stealing
        return self._steal_channel(priority)

    def _steal_channel(self, priority: AudioPriority) -> Optional[pygame.mixer.Channel]:
        """Steal a channel from a lower priority sound."""
        # Find the lowest priority sound that's lower than our priority
        lowest_priority = priority.value
        lowest_channel_id: Optional[int] = None
        finished_channels: List[int] = []

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
            del self._playing_sounds[channel_id]

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
                del self._playing_sounds[lowest_channel_id]
                logger.debug(
                    "Stole channel %d from lower priority sound", lowest_channel_id
                )
                return channel
            except pygame.error:
                pass

        return None

    def _apply_pan(self, channel: pygame.mixer.Channel, pan: float) -> None:
        """Apply stereo panning to a channel.

        Args:
            channel: The pygame channel.
            pan: Pan value (-1.0 = left, 0.0 = center, 1.0 = right).
        """
        # Convert pan to left/right volumes
        # pan = -1: left = 1.0, right = 0.0
        # pan = 0: left = 1.0, right = 1.0
        # pan = 1: left = 0.0, right = 1.0
        if pan < 0:
            left = 1.0
            right = 1.0 + pan  # pan is negative, so this reduces right
        else:
            left = 1.0 - pan
            right = 1.0

        channel.set_volume(left, right)

    # ========== Basic SFX Control ==========

    def stop_sfx(self, channel: int) -> None:
        """Stop a specific sound effect channel."""
        try:
            pygame.mixer.Channel(channel).stop()
            if channel in self._playing_sounds:
                del self._playing_sounds[channel]
        except pygame.error:
            pass

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
        finished = []
        for channel_id in self._playing_sounds:
            try:
                channel = pygame.mixer.Channel(channel_id)
                if not channel.get_busy():
                    finished.append(channel_id)
            except pygame.error:
                finished.append(channel_id)

        for channel_id in finished:
            del self._playing_sounds[channel_id]

    def get_active_sound_count(self) -> int:
        """Get number of currently playing sounds."""
        self.cleanup_finished_channels()
        return len(self._playing_sounds)
