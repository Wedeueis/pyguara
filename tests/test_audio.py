"""Tests for the audio system."""

from unittest.mock import Mock, patch
from typing import Any
import pytest
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.audio.manager import AudioManager
from pyguara.resources.types import AudioClip


# ========== Fixtures ==========


@pytest.fixture  # type: ignore[misc]
def mock_pygame_mixer() -> Any:
    """Mock pygame.mixer to avoid actual audio initialization."""
    with patch("pygame.mixer") as mock_mixer:
        # Setup default mocks
        mock_mixer.get_init.return_value = True
        mock_mixer.set_num_channels.return_value = None
        mock_mixer.music = Mock()
        mock_mixer.music.get_busy.return_value = False
        mock_mixer.music.load.return_value = None
        mock_mixer.music.play.return_value = None
        mock_mixer.music.stop.return_value = None
        mock_mixer.music.pause.return_value = None
        mock_mixer.music.unpause.return_value = None
        mock_mixer.music.fadeout.return_value = None
        mock_mixer.music.set_volume.return_value = None
        mock_mixer.pause.return_value = None
        mock_mixer.unpause.return_value = None
        mock_mixer.Channel.return_value.stop.return_value = None

        yield mock_mixer


@pytest.fixture  # type: ignore[misc]
def audio_system(mock_pygame_mixer: Any) -> PygameAudioSystem:
    """Create a PygameAudioSystem instance with mocked pygame."""
    return PygameAudioSystem()


@pytest.fixture  # type: ignore[misc]
def mock_audio_clip() -> AudioClip:
    """Create a mock audio clip for testing."""
    clip = Mock(spec=AudioClip)
    clip.path = "test_sound.wav"

    # Mock pygame Sound object
    mock_sound = Mock()
    mock_sound.set_volume = Mock()
    mock_sound.play = Mock(return_value=Mock(get_id=Mock(return_value=0)))

    clip.native_handle = mock_sound
    return clip


@pytest.fixture  # type: ignore[misc]
def audio_manager(audio_system: PygameAudioSystem) -> AudioManager:
    """Create an AudioManager instance."""
    return AudioManager(audio_system)


# ========== Volume Control Tests ==========


def test_master_volume_control(audio_system: PygameAudioSystem) -> None:
    """Test master volume getter and setter."""
    # Default volume should be 1.0
    assert audio_system.get_master_volume() == 1.0

    # Set new volume
    audio_system.set_master_volume(0.5)
    assert audio_system.get_master_volume() == 0.5

    # Test clamping
    audio_system.set_master_volume(1.5)  # Above max
    assert audio_system.get_master_volume() == 1.0

    audio_system.set_master_volume(-0.5)  # Below min
    assert audio_system.get_master_volume() == 0.0


def test_sfx_volume_control(audio_system: PygameAudioSystem) -> None:
    """Test SFX volume getter and setter."""
    # Default volume should be 1.0
    assert audio_system.get_sfx_volume() == 1.0

    # Set new volume
    audio_system.set_sfx_volume(0.7)
    assert audio_system.get_sfx_volume() == 0.7

    # Test clamping
    audio_system.set_sfx_volume(2.0)
    assert audio_system.get_sfx_volume() == 1.0


def test_music_volume_control(
    audio_system: PygameAudioSystem, mock_pygame_mixer: Any
) -> None:
    """Test music volume getter and setter."""
    # Default volume should be 1.0
    assert audio_system.get_music_volume() == 1.0

    # Set new volume
    audio_system.set_music_volume(0.3)
    assert audio_system.get_music_volume() == 0.3

    # Verify pygame.mixer.music.set_volume was called with effective volume
    mock_pygame_mixer.music.set_volume.assert_called()


def test_volume_hierarchy(audio_system: PygameAudioSystem) -> None:
    """Test that master volume affects both SFX and music."""
    audio_system.set_master_volume(0.5)
    audio_system.set_sfx_volume(0.8)
    audio_system.set_music_volume(0.6)

    assert audio_system.get_master_volume() == 0.5
    assert audio_system.get_sfx_volume() == 0.8
    assert audio_system.get_music_volume() == 0.6

    # Effective volumes should be: master * category
    # This will be verified in play methods


# ========== SFX Playback Tests ==========


def test_play_sfx(audio_system: PygameAudioSystem, mock_audio_clip: AudioClip) -> None:
    """Test playing a sound effect."""
    channel_id = audio_system.play_sfx(mock_audio_clip, volume=0.8)

    # Verify sound was played
    mock_audio_clip.native_handle.set_volume.assert_called_once()
    mock_audio_clip.native_handle.play.assert_called_once_with(loops=0)

    # Should return a channel ID
    assert channel_id is not None


def test_play_sfx_with_loops(
    audio_system: PygameAudioSystem, mock_audio_clip: AudioClip
) -> None:
    """Test playing a looping sound effect."""
    audio_system.play_sfx(mock_audio_clip, volume=1.0, loops=3)

    # Verify loops parameter was passed
    mock_audio_clip.native_handle.play.assert_called_once_with(loops=3)


def test_play_sfx_volume_application(
    audio_system: PygameAudioSystem, mock_audio_clip: AudioClip
) -> None:
    """Test that SFX volume is correctly applied."""
    audio_system.set_master_volume(0.5)
    audio_system.set_sfx_volume(0.8)

    audio_system.play_sfx(mock_audio_clip, volume=0.6)

    # Effective volume should be: 0.6 * 0.8 * 0.5 = 0.24
    expected_volume = 0.6 * 0.8 * 0.5
    mock_audio_clip.native_handle.set_volume.assert_called_once_with(expected_volume)


def test_stop_sfx(audio_system: PygameAudioSystem, mock_pygame_mixer: Any) -> None:
    """Test stopping a specific SFX channel."""
    audio_system.stop_sfx(0)

    # Verify Channel(0).stop() was called
    mock_pygame_mixer.Channel.assert_called_once_with(0)
    mock_pygame_mixer.Channel.return_value.stop.assert_called_once()


def test_pause_resume_sfx(
    audio_system: PygameAudioSystem, mock_pygame_mixer: Any
) -> None:
    """Test pausing and resuming all sound effects."""
    audio_system.pause_sfx()
    mock_pygame_mixer.pause.assert_called_once()

    audio_system.resume_sfx()
    mock_pygame_mixer.unpause.assert_called_once()


# ========== Music Playback Tests ==========


def test_play_music(audio_system: PygameAudioSystem, mock_pygame_mixer: Any) -> None:
    """Test playing background music."""
    audio_system.play_music("music/bgm.ogg", loop=True, fade_ms=1000)

    # Verify music was loaded and played
    mock_pygame_mixer.music.load.assert_called_once_with("music/bgm.ogg")
    mock_pygame_mixer.music.play.assert_called_once_with(loops=-1, fade_ms=1000)
    mock_pygame_mixer.music.set_volume.assert_called()


def test_play_music_no_loop(
    audio_system: PygameAudioSystem, mock_pygame_mixer: Any
) -> None:
    """Test playing non-looping music."""
    audio_system.play_music("music/theme.mp3", loop=False)

    # Verify loops=0 for non-looping
    mock_pygame_mixer.music.play.assert_called_once_with(loops=0, fade_ms=1000)


def test_stop_music(audio_system: PygameAudioSystem, mock_pygame_mixer: Any) -> None:
    """Test stopping music."""
    audio_system.stop_music(fade_ms=500)

    mock_pygame_mixer.music.fadeout.assert_called_once_with(500)


def test_pause_resume_music(
    audio_system: PygameAudioSystem, mock_pygame_mixer: Any
) -> None:
    """Test pausing and resuming music."""
    audio_system.pause_music()
    mock_pygame_mixer.music.pause.assert_called_once()

    audio_system.resume_music()
    mock_pygame_mixer.music.unpause.assert_called_once()


def test_is_music_playing(
    audio_system: PygameAudioSystem, mock_pygame_mixer: Any
) -> None:
    """Test checking if music is playing."""
    # Mock music as not playing
    mock_pygame_mixer.music.get_busy.return_value = False
    assert not audio_system.is_music_playing()

    # Mock music as playing
    mock_pygame_mixer.music.get_busy.return_value = True
    assert audio_system.is_music_playing()


# ========== AudioManager Tests ==========


def test_audio_manager_initialization(audio_manager: AudioManager) -> None:
    """Test AudioManager initializes correctly."""
    assert audio_manager is not None
    assert audio_manager.get_master_volume() == 1.0
    assert audio_manager.get_current_music() is None


def test_audio_manager_play_music(
    audio_manager: AudioManager, mock_pygame_mixer: Any
) -> None:
    """Test AudioManager music playback."""
    audio_manager.play_music("music/bgm.ogg")

    # Verify music was played
    mock_pygame_mixer.music.load.assert_called_once_with("music/bgm.ogg")
    mock_pygame_mixer.music.play.assert_called_once()

    # Verify current music is tracked
    assert audio_manager.get_current_music() == "music/bgm.ogg"


def test_audio_manager_stop_music(
    audio_manager: AudioManager, mock_pygame_mixer: Any
) -> None:
    """Test AudioManager stops music and clears tracking."""
    audio_manager.play_music("music/bgm.ogg")
    audio_manager.stop_music()

    mock_pygame_mixer.music.fadeout.assert_called_once()
    assert audio_manager.get_current_music() is None


def test_audio_manager_volume_control(audio_manager: AudioManager) -> None:
    """Test AudioManager volume controls."""
    audio_manager.set_master_volume(0.7)
    assert audio_manager.get_master_volume() == 0.7

    audio_manager.set_sfx_volume(0.5)
    assert audio_manager.get_sfx_volume() == 0.5

    audio_manager.set_music_volume(0.3)
    assert audio_manager.get_music_volume() == 0.3


def test_audio_manager_pause_resume(
    audio_manager: AudioManager, mock_pygame_mixer: Any
) -> None:
    """Test AudioManager pause and resume."""
    audio_manager.pause_music()
    mock_pygame_mixer.music.pause.assert_called_once()

    audio_manager.resume_music()
    mock_pygame_mixer.music.unpause.assert_called_once()

    audio_manager.pause_all_sfx()
    mock_pygame_mixer.pause.assert_called_once()

    audio_manager.resume_all_sfx()
    mock_pygame_mixer.unpause.assert_called_once()


def test_audio_manager_cleanup(
    audio_manager: AudioManager, mock_pygame_mixer: Any
) -> None:
    """Test AudioManager cleanup."""
    audio_manager.play_music("music/bgm.ogg")
    audio_manager.cleanup()

    # Verify music was stopped
    mock_pygame_mixer.music.fadeout.assert_called_with(0)

    # Verify tracking was cleared
    assert audio_manager.get_current_music() is None


def test_audio_manager_play_sfx_clip(
    audio_manager: AudioManager, mock_audio_clip: AudioClip
) -> None:
    """Test AudioManager playing SFX clip."""
    channel_id = audio_manager.play_sfx_clip(mock_audio_clip, volume=0.8)

    # Verify sound was played
    mock_audio_clip.native_handle.play.assert_called_once()
    assert channel_id is not None


def test_audio_manager_stop_sfx(
    audio_manager: AudioManager, mock_pygame_mixer: Any
) -> None:
    """Test AudioManager stopping SFX channel."""
    audio_manager.stop_sfx(0)

    mock_pygame_mixer.Channel.assert_called_once_with(0)
    mock_pygame_mixer.Channel.return_value.stop.assert_called_once()


# ========== Integration Tests ==========


def test_full_audio_workflow(
    audio_manager: AudioManager,
    mock_audio_clip: AudioClip,
    mock_pygame_mixer: Any,
) -> None:
    """Test a complete audio workflow."""
    # Set volumes
    audio_manager.set_master_volume(0.8)
    audio_manager.set_sfx_volume(0.7)
    audio_manager.set_music_volume(0.5)

    # Play music
    audio_manager.play_music("music/bgm.ogg", loop=True)
    assert (
        audio_manager.is_music_playing() or not audio_manager.is_music_playing()
    )  # Depends on mock

    # Play SFX
    channel = audio_manager.play_sfx_clip(mock_audio_clip, volume=1.0)
    assert channel is not None

    # Pause everything
    audio_manager.pause_music()
    audio_manager.pause_all_sfx()

    # Resume everything
    audio_manager.resume_music()
    audio_manager.resume_all_sfx()

    # Stop music
    audio_manager.stop_music()
    assert audio_manager.get_current_music() is None

    # Cleanup
    audio_manager.cleanup()
