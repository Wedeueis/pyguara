"""Integration tests for Pygame audio backend."""

import os
import pytest
import pygame
from typing import Iterator, Any
from unittest.mock import MagicMock
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.resources.types import AudioClip

# Ensure headless execution
os.environ["SDL_AUDIODRIVER"] = "dummy"


@pytest.fixture(scope="module")
def pygame_mixer_init() -> Iterator[None]:
    """Initialize pygame mixer for the module."""
    pygame.mixer.init()
    yield
    pygame.mixer.quit()


@pytest.fixture
def audio_system(pygame_mixer_init: None) -> PygameAudioSystem:
    """Create a PygameAudioSystem instance."""
    # Re-init explicitly for test isolation if needed, but fixture handles module level
    return PygameAudioSystem()


def test_audio_initialization(audio_system: PygameAudioSystem) -> None:
    """Audio system should initialize with default volumes."""
    assert audio_system.get_master_volume() == 1.0
    assert audio_system.get_sfx_volume() == 1.0
    assert audio_system.get_music_volume() == 1.0


def test_volume_control(audio_system: PygameAudioSystem) -> None:
    """Audio system should update volumes."""
    audio_system.set_master_volume(0.5)
    assert audio_system.get_master_volume() == 0.5

    audio_system.set_sfx_volume(0.8)
    assert audio_system.get_sfx_volume() == 0.8

    audio_system.set_music_volume(0.2)
    assert audio_system.get_music_volume() == 0.2


class MockAudioClip(AudioClip):
    def __init__(self, path: str, native_sound: Any = None):
        super().__init__(path)
        self._native_sound = native_sound

    @property
    def duration(self) -> float:
        return 1.0

    @property
    def native_handle(self) -> Any:
        return self._native_sound


def test_play_sfx_mock(audio_system: PygameAudioSystem) -> None:
    """Audio system should play sound effects."""
    # Mock native sound
    mock_sound = MagicMock()
    # Mock play to return a Channel object
    mock_channel = MagicMock()
    mock_channel.get_id.return_value = 1
    mock_sound.play.return_value = mock_channel

    clip = MockAudioClip("dummy.wav", mock_sound)

    channel_id = audio_system.play_sfx(clip)

    assert channel_id == 1
    mock_sound.play.assert_called_once()
    mock_sound.set_volume.assert_called()


def test_play_sfx_invalid(audio_system: PygameAudioSystem) -> None:
    """Audio system should handle invalid clips gracefully."""
    # Clip with no native handle (or handle missing methods)
    clip = MockAudioClip("broken.wav", None)

    channel_id = audio_system.play_sfx(clip)
    assert channel_id is None


def test_music_controls(audio_system: PygameAudioSystem) -> None:
    """Audio system should expose music controls without crashing."""
    # We can't easily play music without a file, but we can call stop/pause
    audio_system.stop_music()
    audio_system.pause_music()
    audio_system.resume_music()
    assert audio_system.is_music_playing() is False
