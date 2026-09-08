"""Tests for the audio component system."""

from unittest.mock import MagicMock

import pytest

from pyguara.audio.audio_source_system import AudioSourceSystem
from pyguara.audio.components import AudioEmitter, AudioListener, AudioSource
from pyguara.audio.types import AudioPriority, SpatialAudioConfig
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager


class TestAudioSource:
    """Tests for AudioSource component."""

    def test_create_with_defaults(self):
        """Test creating AudioSource with default values."""
        source = AudioSource()

        assert source.clip_path == ""
        assert source.volume == 1.0
        assert source.spatial is True
        assert source.loop is False
        assert source.auto_play is False
        assert source.priority == AudioPriority.NORMAL
        assert source.max_distance == 1000.0
        assert source._channel_id is None
        assert source._is_playing is False
        assert source._stop_requested is False

    def test_create_with_custom_values(self):
        """Test creating AudioSource with custom values."""
        source = AudioSource(
            clip_path="sounds/explosion.wav",
            volume=0.5,
            spatial=False,
            loop=True,
            auto_play=True,
            priority=AudioPriority.HIGH,
            max_distance=500.0,
        )

        assert source.clip_path == "sounds/explosion.wav"
        assert source.volume == 0.5
        assert source.spatial is False
        assert source.loop is True
        assert source.auto_play is True
        assert source.priority == AudioPriority.HIGH
        assert source.max_distance == 500.0

    def test_play_on_awake_alias(self):
        """Test that play_on_awake sets auto_play."""
        source = AudioSource(play_on_awake=True)
        assert source.auto_play is True

    def test_play_sets_playing_flag(self):
        """Test that play() sets the playing flag."""
        source = AudioSource(clip_path="sounds/test.wav")
        source.play()

        assert source._is_playing is True
        assert source._stop_requested is False

    def test_play_without_clip_does_nothing(self):
        """Test that play() does nothing without clip_path."""
        source = AudioSource()
        source.play()

        assert source._is_playing is False

    def test_stop_sets_stop_flag(self):
        """Test that stop() sets the stop flag."""
        source = AudioSource(clip_path="sounds/test.wav")
        source.play()
        source.stop()

        assert source._stop_requested is True

    def test_is_playing_property(self):
        """Test is_playing property."""
        source = AudioSource(clip_path="sounds/test.wav")
        assert source.is_playing is False

        source._is_playing = True
        assert source.is_playing is True

    def test_channel_id_property(self):
        """Test channel_id property."""
        source = AudioSource()
        assert source.channel_id is None

        source._channel_id = 5
        assert source.channel_id == 5

    def test_on_detach_requests_stop(self):
        """Test that on_detach requests stop."""
        source = AudioSource(clip_path="sounds/test.wav")
        source.play()

        source.on_detach()

        assert source._stop_requested is True


class TestAudioListener:
    """Tests for AudioListener component."""

    def test_create_with_defaults(self):
        """Test creating AudioListener with default values."""
        listener = AudioListener()
        assert listener.active is True

    def test_create_inactive(self):
        """Test creating inactive AudioListener."""
        listener = AudioListener(active=False)
        assert listener.active is False


class TestAudioEmitter:
    """Tests for AudioEmitter component."""

    def test_create_with_defaults(self):
        """Test creating AudioEmitter with default values."""
        emitter = AudioEmitter()

        assert emitter.clip_path == ""
        assert emitter.volume == 1.0
        assert emitter.played is False
        assert emitter.remove_after_play is True

    def test_create_with_custom_values(self):
        """Test creating AudioEmitter with custom values."""
        emitter = AudioEmitter(
            clip_path="sounds/hit.wav",
            volume=0.8,
            remove_after_play=False,
        )

        assert emitter.clip_path == "sounds/hit.wav"
        assert emitter.volume == 0.8
        assert emitter.remove_after_play is False

    def test_emit_resets_played(self):
        """Test that emit() resets the played flag."""
        emitter = AudioEmitter(clip_path="sounds/test.wav")
        emitter.played = True

        emitter.emit()

        assert emitter.played is False


class TestAudioSourceSystem:
    """Tests for AudioSourceSystem."""

    @pytest.fixture
    def entity_manager(self):
        """Create an entity manager."""
        return EntityManager()

    @pytest.fixture
    def audio_system(self):
        """Create a mock audio system.

        `is_channel_active` defaults to True: unless a test says otherwise the
        sound is treated as still playing, so the frame-by-frame reconcile in
        AudioSourceSystem is a no-op.
        """
        mock = MagicMock()
        mock.play_sfx.return_value = 1  # Return channel ID
        mock.play_sfx_at_position.return_value = 2
        mock.is_channel_active.return_value = True
        return mock

    @pytest.fixture
    def resource_manager(self):
        """Create a mock resource manager."""
        mock = MagicMock()
        mock.load.return_value = MagicMock()  # Return mock clip
        return mock

    @pytest.fixture
    def system(self, entity_manager, audio_system, resource_manager):
        """Create an AudioSourceSystem."""
        return AudioSourceSystem(entity_manager, audio_system, resource_manager)

    def test_create_system(self, entity_manager, audio_system):
        """Test creating AudioSourceSystem."""
        system = AudioSourceSystem(entity_manager, audio_system)

        assert system._entity_manager is entity_manager
        assert system._audio_system is audio_system
        assert system._resource_manager is None

    def test_create_system_with_resource_manager(
        self, entity_manager, audio_system, resource_manager
    ):
        """Test creating AudioSourceSystem with resource manager."""
        system = AudioSourceSystem(entity_manager, audio_system, resource_manager)

        assert system._resource_manager is resource_manager

    def test_listener_position_property(self, system):
        """Test listener_position property."""
        assert system.listener_position == Vector2(0, 0)

    def test_set_spatial_config(self, system):
        """Test setting spatial audio config."""
        config = SpatialAudioConfig(max_distance=500.0)
        system.set_spatial_config(config)

        assert system._spatial_config.max_distance == 500.0

    def test_update_listener_position(
        self, entity_manager, audio_system, resource_manager
    ):
        """Test that listener position is updated from AudioListener entity."""
        system = AudioSourceSystem(entity_manager, audio_system, resource_manager)

        # Create listener entity
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(100, 200)))
        entity.add_component(AudioListener(active=True))

        system.update(0.016)

        assert system._listener_position == Vector2(100, 200)
        audio_system.set_listener_position.assert_called_with(Vector2(100, 200))

    def test_inactive_listener_ignored(self, entity_manager, audio_system):
        """Test that inactive listeners are ignored."""
        system = AudioSourceSystem(entity_manager, audio_system)

        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(100, 200)))
        entity.add_component(AudioListener(active=False))

        system.update(0.016)

        assert system._listener_position == Vector2(0, 0)
        audio_system.set_listener_position.assert_not_called()

    def test_auto_play_source(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test auto_play triggers playback."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(
            clip_path="sounds/music.wav", auto_play=True, spatial=False
        )
        entity.add_component(source)

        system.update(0.016)

        assert source._is_playing is True
        audio_system.play_sfx.assert_called()

    def test_play_source_request(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test manual play request."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="sounds/sfx.wav", spatial=False)
        entity.add_component(source)

        source.play()
        system.update(0.016)

        assert source._channel_id is not None
        audio_system.play_sfx.assert_called()

    def test_stop_source_request(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test stop request."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="sounds/sfx.wav", spatial=False)
        entity.add_component(source)

        source.play()
        system.update(0.016)

        channel_id = source._channel_id
        source.stop()
        system.update(0.016)

        audio_system.stop_sfx.assert_called_with(channel_id)
        assert source._channel_id is None
        assert source._is_playing is False

    def test_spatial_audio_playback(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test spatial audio playback."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(50, 100)))
        source = AudioSource(clip_path="sounds/sfx.wav", spatial=True)
        entity.add_component(source)

        source.play()
        system.update(0.016)

        audio_system.play_sfx_at_position.assert_called()

    def test_spatial_source_updates_channel_mix_each_frame(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """A playing spatial source pushes attenuation/pan updates via
        set_channel_mix as it (or the listener) moves, using its real channel."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(50, 100)))
        source = AudioSource(clip_path="sounds/sfx.wav", spatial=True)
        entity.add_component(source)

        source.play()
        system.update(0.016)  # Starts playback, channel_id becomes 2.
        system.update(0.016)  # Source still playing: pushes a mix update.

        assert source._channel_id == 2
        audio_system.set_channel_mix.assert_called()
        channel, attenuation, pan = audio_system.set_channel_mix.call_args[0]
        assert channel == 2
        assert 0.0 <= attenuation <= 1.0
        assert -1.0 <= pan <= 1.0

    def test_non_spatial_source_never_updates_channel_mix(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """A non-spatial source has no position to mix against, so it must
        never call set_channel_mix."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="sounds/sfx.wav", spatial=False)
        entity.add_component(source)

        source.play()
        system.update(0.016)
        system.update(0.016)

        audio_system.set_channel_mix.assert_not_called()

    def test_looping_source(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test looping playback."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="sounds/loop.wav", loop=True, spatial=False)
        entity.add_component(source)

        source.play()
        system.update(0.016)

        # Check that loops=-1 was passed (infinite loop)
        call_kwargs = audio_system.play_sfx.call_args
        assert call_kwargs[1]["loops"] == -1

    def test_audio_emitter_one_shot(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test AudioEmitter one-shot playback."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(25, 75)))
        emitter = AudioEmitter(clip_path="sounds/explosion.wav")
        entity.add_component(emitter)

        system.update(0.016)

        assert emitter.played is True
        audio_system.play_sfx_at_position.assert_called()

    def test_emitter_remove_after_play(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test emitter removal after playing."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        emitter = AudioEmitter(clip_path="sounds/pickup.wav", remove_after_play=True)
        entity.add_component(emitter)

        # First update plays the sound
        system.update(0.016)
        assert emitter.played is True

        # Second update removes the component
        system.update(0.016)
        assert not entity.has_component(AudioEmitter)

    def test_emitter_keep_after_play(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test emitter kept after playing when remove_after_play=False."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        emitter = AudioEmitter(clip_path="sounds/effect.wav", remove_after_play=False)
        entity.add_component(emitter)

        system.update(0.016)
        system.update(0.016)

        # Component should still exist
        assert entity.has_component(AudioEmitter)

    def test_cleanup_stops_all_sources(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test cleanup stops all playing sources."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="sounds/test.wav", spatial=False)
        entity.add_component(source)

        source.play()
        system.update(0.016)

        channel_id = source._channel_id
        system.cleanup()

        audio_system.stop_sfx.assert_called_with(channel_id)
        assert source._channel_id is None

    def test_missing_clip_logs_warning(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test that missing clip path logs warning."""
        resource_manager.load.side_effect = Exception("File not found")

        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="sounds/missing.wav", spatial=False)
        entity.add_component(source)

        source.play()
        system.update(0.016)

        # Should not crash, source should not be playing
        assert source._is_playing is False
        assert source._channel_id is None

    def test_clip_caching(self, entity_manager, audio_system, resource_manager, system):
        """Test that clips are cached."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="sounds/cached.wav", spatial=False)
        entity.add_component(source)

        source.play()
        system.update(0.016)

        # Reset source to play again
        source._channel_id = None
        source.play()
        system.update(0.016)

        # Should only load once (cached)
        assert resource_manager.load.call_count == 1

    def test_emitter_without_transform(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Test emitter without Transform plays non-spatial."""
        entity = entity_manager.create_entity()
        emitter = AudioEmitter(clip_path="sounds/ui_click.wav")
        entity.add_component(emitter)

        system.update(0.016)

        assert emitter.played is True
        audio_system.play_sfx.assert_called()  # Non-spatial
        audio_system.play_sfx_at_position.assert_not_called()

    # ---- finished-sound reconciliation (D8) -------------------------------

    def _play_started_source(self, entity_manager, system, **source_kwargs):
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="s.wav", spatial=False, **source_kwargs)
        entity.add_component(source)
        source.play()
        system.update(0.016)
        return entity, source

    def test_finished_oneshot_is_reconciled(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """When the backend reports the channel is no longer active, the
        source stops claiming it is playing (a one-shot ends with no
        callback, so nothing else clears this)."""
        _, source = self._play_started_source(entity_manager, system)
        assert source._channel_id is not None and source.is_playing

        audio_system.is_channel_active.return_value = False
        system.update(0.016)

        assert source._channel_id is None
        assert source.is_playing is False

    def test_finished_oneshot_no_longer_mixes_the_dead_channel(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """A stale channel id must stop receiving spatial mix updates once
        the sound has ended -- otherwise it rewrites whatever now owns it."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(50, 0)))
        source = AudioSource(clip_path="s.wav", spatial=True)
        entity.add_component(source)
        source.play()
        system.update(0.016)  # channel 2
        system.update(0.016)  # spatial mix pushed
        assert audio_system.set_channel_mix.called

        audio_system.set_channel_mix.reset_mock()
        audio_system.is_channel_active.return_value = False
        system.update(0.016)
        system.update(0.016)

        audio_system.set_channel_mix.assert_not_called()

    def test_finished_oneshot_can_be_replayed(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """After a one-shot ends, calling play() again actually restarts it
        (the channel id no longer sticks)."""
        _, source = self._play_started_source(entity_manager, system)
        audio_system.is_channel_active.return_value = False
        system.update(0.016)  # reconcile -> cleared

        audio_system.is_channel_active.return_value = True
        audio_system.play_sfx.reset_mock()
        source.play()
        system.update(0.016)

        audio_system.play_sfx.assert_called_once()
        assert source._channel_id is not None

    def test_looping_source_is_not_reconciled_away(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """A looping source stays active as long as the backend says so."""
        _, source = self._play_started_source(entity_manager, system, loop=True)
        for _ in range(5):
            system.update(0.016)
        assert source._channel_id is not None
        assert source.is_playing

    # ---- auto_play latch (exposed by D8's fix) --------------------------

    def test_auto_play_fires_once_not_again_after_the_sound_ends(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """auto_play is 'play on awake', not 'loop': once the one-shot ends
        and is reconciled, it must not restart on its own."""
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="s.wav", spatial=False, auto_play=True)
        entity.add_component(source)

        system.update(0.016)
        assert audio_system.play_sfx.call_count == 1

        audio_system.is_channel_active.return_value = False
        system.update(0.016)  # reconcile
        for _ in range(3):
            system.update(0.016)

        assert audio_system.play_sfx.call_count == 1  # never re-triggered

    def test_failed_load_does_not_retry_every_frame(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """A source whose clip fails to load latches instead of hammering
        the loader once per frame."""
        resource_manager.load.side_effect = Exception("missing")
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="nope.wav", spatial=False, auto_play=True)
        entity.add_component(source)

        for _ in range(5):
            system.update(0.016)

        assert resource_manager.load.call_count == 1

    def test_channel_id_zero_is_honoured(
        self, entity_manager, audio_system, resource_manager, system
    ):
        """Channel id 0 is a real channel: an auto_play source already on
        channel 0 is not treated as 'no channel' and re-triggered."""
        audio_system.play_sfx.return_value = 0
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        source = AudioSource(clip_path="s.wav", spatial=False, auto_play=True)
        entity.add_component(source)

        system.update(0.016)
        system.update(0.016)
        system.update(0.016)

        assert source._channel_id == 0
        assert audio_system.play_sfx.call_count == 1
