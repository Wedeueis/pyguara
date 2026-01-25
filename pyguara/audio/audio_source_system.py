"""Audio source system for processing entity audio components.

Updates spatial audio positions and handles audio lifecycle.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.components import AudioEmitter, AudioListener, AudioSource
from pyguara.audio.types import SpatialAudioConfig
from pyguara.common.components import Transform
from pyguara.common.types import Vector2

if TYPE_CHECKING:
    from pyguara.ecs.manager import EntityManager
    from pyguara.resources.manager import ResourceManager
    from pyguara.resources.types import AudioClip

logger = logging.getLogger(__name__)


class AudioSourceSystem:
    """System that processes AudioSource components.

    Responsibilities:
    - Play/stop audio based on component state
    - Update spatial audio positions each frame
    - Handle auto-play on component attach
    - Clean up audio when entities are destroyed

    Example:
        system = AudioSourceSystem(entity_manager, audio_system, resource_manager)

        # In game loop
        system.update(dt)
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        audio_system: IAudioSystem,
        resource_manager: Optional[ResourceManager] = None,
    ) -> None:
        """Initialize the audio source system.

        Args:
            entity_manager: Entity manager to query for components.
            audio_system: Audio system for playback.
            resource_manager: Optional resource manager for loading clips.
        """
        self._entity_manager = entity_manager
        self._audio_system = audio_system
        self._resource_manager = resource_manager
        self._spatial_config = SpatialAudioConfig()
        self._listener_position = Vector2(0, 0)
        self._clip_cache: dict[str, AudioClip] = {}

    @property
    def listener_position(self) -> Vector2:
        """Get the current listener position."""
        return self._listener_position

    def set_spatial_config(self, config: SpatialAudioConfig) -> None:
        """Set the spatial audio configuration.

        Args:
            config: Spatial audio settings.
        """
        self._spatial_config = config

    def update(self, dt: float) -> None:
        """Update all audio sources.

        Args:
            dt: Delta time since last update.
        """
        # Update listener position from AudioListener entities
        self._update_listener_position()

        # Process AudioSource components
        self._process_audio_sources()

        # Process AudioEmitter components
        self._process_audio_emitters()

    def _update_listener_position(self) -> None:
        """Find and update listener position from AudioListener entity."""
        for entity in self._entity_manager.get_entities_with(AudioListener, Transform):
            listener = entity.get_component(AudioListener)
            if listener and listener.active:
                transform = entity.get_component(Transform)
                if transform:
                    self._listener_position = transform.position
                    self._audio_system.set_listener_position(self._listener_position)
                    break  # Only one active listener

    def _process_audio_sources(self) -> None:
        """Process all AudioSource components."""
        for entity in self._entity_manager.get_entities_with(AudioSource):
            source = entity.get_component(AudioSource)
            if not source:
                continue

            # Handle stop requests
            if source._stop_requested:
                self._stop_source(source)
                continue

            # Handle auto-play
            if source.auto_play and not source._is_playing and not source._channel_id:
                source.play()

            # Handle play requests
            if source._is_playing and source._channel_id is None:
                self._play_source(source, entity)

            # Update spatial position for playing sources
            if source._channel_id is not None and source.spatial:
                transform = entity.get_component(Transform)
                if transform:
                    self._update_spatial_position(source, transform.position)

    def _process_audio_emitters(self) -> None:
        """Process AudioEmitter components for one-shot sounds."""
        entities_to_remove_emitter = []

        for entity in self._entity_manager.get_entities_with(AudioEmitter):
            emitter = entity.get_component(AudioEmitter)
            if not emitter or emitter.played:
                if emitter and emitter.remove_after_play and emitter.played:
                    entities_to_remove_emitter.append((entity, emitter))
                continue

            # Play the sound
            clip = self._get_clip(emitter.clip_path)
            if clip:
                transform = (
                    entity.get_component(Transform)
                    if entity.has_component(Transform)
                    else None
                )
                if transform:
                    self._audio_system.play_sfx_at_position(
                        clip,
                        transform.position,
                        self._listener_position,
                        volume=emitter.volume,
                    )
                else:
                    self._audio_system.play_sfx(clip, volume=emitter.volume)

            emitter.played = True

        # Remove emitters that should be removed after playing
        for entity, emitter in entities_to_remove_emitter:
            entity.remove_component(type(emitter))

    def _play_source(self, source: AudioSource, entity: object) -> None:
        """Start playing an audio source.

        Args:
            source: The AudioSource component.
            entity: The entity with the source.
        """
        if not source.clip_path:
            source._is_playing = False
            return

        clip = self._get_clip(source.clip_path)
        if not clip:
            logger.warning(f"Could not load audio clip: {source.clip_path}")
            source._is_playing = False
            return

        loops = -1 if source.loop else 0

        if source.spatial:
            transform = getattr(entity, "get_component", lambda t: None)(Transform)
            if transform:
                source._channel_id = self._audio_system.play_sfx_at_position(
                    clip,
                    transform.position,
                    self._listener_position,
                    volume=source.volume,
                    loops=loops,
                    priority=source.priority,
                )
            else:
                source._channel_id = self._audio_system.play_sfx(
                    clip,
                    volume=source.volume,
                    loops=loops,
                    priority=source.priority,
                )
        else:
            source._channel_id = self._audio_system.play_sfx(
                clip,
                volume=source.volume,
                loops=loops,
                priority=source.priority,
            )

        logger.debug(f"Started audio source: {source.clip_path}")

    def _stop_source(self, source: AudioSource) -> None:
        """Stop an audio source.

        Args:
            source: The AudioSource component to stop.
        """
        if source._channel_id is not None:
            self._audio_system.stop_sfx(source._channel_id)
            logger.debug(f"Stopped audio source: {source.clip_path}")

        source._channel_id = None
        source._is_playing = False
        source._stop_requested = False

    def _update_spatial_position(self, source: AudioSource, position: Vector2) -> None:
        """Update the spatial position of a playing source.

        Args:
            source: The AudioSource component.
            position: Current world position.
        """
        # Calculate attenuation and panning
        distance = position.distance_to(self._listener_position)
        _attenuation = self._spatial_config.calculate_attenuation(distance)
        _pan = self._spatial_config.calculate_pan(position, self._listener_position)

        # Apply to channel
        # Note: This requires the audio backend to support dynamic channel updates
        # For now, we just update on next play
        # TODO: Add channel volume/pan update to IAudioSystem using _attenuation/_pan

    def _get_clip(self, path: str) -> Optional[AudioClip]:
        """Get or load an audio clip.

        Args:
            path: Path to the audio file.

        Returns:
            The AudioClip, or None if loading failed.
        """
        if path in self._clip_cache:
            return self._clip_cache[path]

        if self._resource_manager:
            try:
                from pyguara.resources.types import AudioClip

                clip = self._resource_manager.load(path, AudioClip)  # type: ignore[type-abstract]
                self._clip_cache[path] = clip
                return clip
            except Exception as e:
                logger.error(f"Failed to load audio clip '{path}': {e}")
                return None

        return None

    def cleanup(self) -> None:
        """Stop all playing audio sources."""
        for entity in self._entity_manager.get_entities_with(AudioSource):
            source = entity.get_component(AudioSource)
            if source and source._channel_id is not None:
                self._stop_source(source)

        self._clip_cache.clear()
