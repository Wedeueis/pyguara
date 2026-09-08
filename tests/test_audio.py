"""Tests for the audio system.

These drive the **real** pygame mixer under the ``dummy`` SDL driver with
real ``Sound`` buffers. Only ``pygame.mixer.music`` -- the file-streaming API,
which needs a real file on disk -- is mocked. The previous version of this
file patched ``pygame.mixer`` wholesale, so channel ids, stereo volume, the
shared-``Sound`` volume trap and ``Channel.id`` (the real attribute, vs the
non-existent ``get_id()`` the backend called) were never exercised.
"""

import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem  # noqa: E402
from pyguara.audio.manager import AudioManager  # noqa: E402
from pyguara.resources.types import AudioClip  # noqa: E402

_SAMPLE_RATE = 44100

# ========== Fixtures ==========


@pytest.fixture(autouse=True, scope="module")
def _mixer() -> Iterator[None]:
    """Bring the real (dummy-driver) mixer up for the module."""
    pygame.mixer.init(_SAMPLE_RATE, -16, 2, 512)
    yield
    pygame.mixer.quit()


@pytest.fixture
def mock_music() -> Iterator[Any]:
    """Mock only the music-streaming API; channels stay real."""
    with patch("pygame.mixer.music") as music:
        music.get_busy.return_value = False
        yield music


def _make_clip(path: str = "test_sound.wav", seconds: float = 1.0) -> AudioClip:
    """Build a real AudioClip wrapping a real Sound of `seconds` of silence."""
    frames = int(_SAMPLE_RATE * seconds)
    sound = pygame.mixer.Sound(buffer=b"\x00\x00\x00\x00" * frames)

    class _Clip(AudioClip):
        @property
        def duration(self) -> float:
            return seconds

        @property
        def native_handle(self) -> pygame.mixer.Sound:
            return sound

    return _Clip(path)


@pytest.fixture
def audio_system(mock_music: Any) -> Iterator[PygameAudioSystem]:
    """A PygameAudioSystem on the real mixer, isolated between tests."""
    system = PygameAudioSystem(num_channels=8)
    yield system
    pygame.mixer.stop()


@pytest.fixture
def audio_clip() -> AudioClip:
    return _make_clip()


@pytest.fixture
def audio_manager(audio_system: PygameAudioSystem) -> AudioManager:
    return AudioManager(audio_system)


# ========== Volume Control Tests ==========


def test_master_volume_control(audio_system: PygameAudioSystem) -> None:
    """Master volume getter/setter, with clamping."""
    assert audio_system.get_master_volume() == 1.0

    audio_system.set_master_volume(0.5)
    assert audio_system.get_master_volume() == 0.5

    audio_system.set_master_volume(1.5)
    assert audio_system.get_master_volume() == 1.0

    audio_system.set_master_volume(-0.5)
    assert audio_system.get_master_volume() == 0.0


def test_sfx_volume_control(audio_system: PygameAudioSystem) -> None:
    """SFX volume getter/setter, with clamping."""
    assert audio_system.get_sfx_volume() == 1.0

    audio_system.set_sfx_volume(0.7)
    assert audio_system.get_sfx_volume() == 0.7

    audio_system.set_sfx_volume(2.0)
    assert audio_system.get_sfx_volume() == 1.0


def test_music_volume_control(audio_system: PygameAudioSystem, mock_music: Any) -> None:
    """Music volume getter/setter pushes the effective volume to the stream."""
    assert audio_system.get_music_volume() == 1.0

    audio_system.set_music_volume(0.3)
    assert audio_system.get_music_volume() == 0.3
    mock_music.set_volume.assert_called()


# ========== SFX Playback Tests ==========


def test_play_sfx_plays_on_the_channel_it_returns(
    audio_system: PygameAudioSystem, audio_clip: AudioClip
) -> None:
    """The returned id names the channel actually carrying our sound.

    Regression: the backend called ``Channel.get_id()`` (does not exist on
    pygame-ce), so every real ``play_sfx`` raised, was swallowed, and returned
    ``None`` while the sound played on untracked.
    """
    channel_id = audio_system.play_sfx(audio_clip, volume=0.8)

    assert channel_id is not None
    assert isinstance(channel_id, int)
    pg = pygame.mixer.Channel(channel_id)
    assert pg.get_busy()
    assert pg.get_sound() is audio_clip.native_handle


def test_play_sfx_channel_id_zero_is_valid(
    audio_system: PygameAudioSystem, audio_clip: AudioClip
) -> None:
    """Channel 0 is a real channel; it must come back as 0, not be treated
    as falsy/absent."""
    channel_id = audio_system.play_sfx(audio_clip)
    assert channel_id == 0
    assert audio_system.is_channel_active(0)


def test_play_sfx_loops_forever_when_requested(
    audio_system: PygameAudioSystem,
) -> None:
    """loops=-1 keeps a short clip busy well past its own length."""
    import time

    clip = _make_clip(seconds=0.05)
    channel_id = audio_system.play_sfx(clip, loops=-1)
    assert channel_id is not None
    time.sleep(0.2)
    assert pygame.mixer.Channel(channel_id).get_busy()


def test_play_sfx_centred_volume_is_set_on_the_channel_not_the_sound(
    audio_system: PygameAudioSystem, audio_clip: AudioClip
) -> None:
    """Effective volume = clip * sfx * master, applied to the channel; the
    shared Sound object is left untouched.

    ``Channel.get_volume()`` only reflects a single-argument ``set_volume``
    (the centred path), so a non-spatial clip is used here.
    """
    audio_system.set_master_volume(0.5)
    audio_system.set_sfx_volume(0.8)

    channel_id = audio_system.play_sfx(audio_clip, volume=0.6)
    assert channel_id is not None

    expected = 0.6 * 0.8 * 0.5
    assert pygame.mixer.Channel(channel_id).get_volume() == pytest.approx(
        expected, abs=0.02
    )
    # D2: the ResourceManager-cached Sound must never have its volume touched.
    assert audio_clip.native_handle.get_volume() == pytest.approx(1.0)


def test_play_sfx_applies_audiometa_volume_db_as_per_asset_gain(
    audio_system: PygameAudioSystem,
) -> None:
    """A clip whose import_meta is an AudioMeta(volume_db=...) is played at
    the corresponding linear gain, multiplied into the channel volume."""
    from pyguara.resources.meta import AudioMeta

    clip = _make_clip("quiet.wav")
    clip.import_meta = AudioMeta(volume_db=-6.0)  # ~0.501x

    channel_id = audio_system.play_sfx(clip, volume=1.0)
    assert channel_id is not None

    assert pygame.mixer.Channel(channel_id).get_volume() == pytest.approx(
        0.501, abs=0.02
    )
    # The shared Sound is still untouched (D2 from the audio audit).
    assert clip.native_handle.get_volume() == pytest.approx(1.0)


def test_channel_stereo_split_is_pure_and_symmetric() -> None:
    """The pan -> (left, right) maths, tested directly (the applied split is
    not observable through ``Channel.get_volume()``)."""
    assert PygameAudioSystem._channel_stereo(1.0, 0.0) == (1.0, 1.0)
    assert PygameAudioSystem._channel_stereo(1.0, 1.0) == (0.0, 1.0)
    assert PygameAudioSystem._channel_stereo(1.0, -1.0) == (1.0, 0.0)
    l_r, r_r = PygameAudioSystem._channel_stereo(0.8, 0.5)
    l_l, r_l = PygameAudioSystem._channel_stereo(0.8, -0.5)
    assert (l_r, r_r) == (r_l, l_l)  # mirror image
    # clamped
    assert PygameAudioSystem._channel_stereo(1.0, 5.0) == (0.0, 1.0)


def test_concurrent_plays_of_one_clip_do_not_share_volume(
    audio_system: PygameAudioSystem,
) -> None:
    """Two spatial plays of the SAME cached clip must not fight over one
    shared ``Sound.set_volume`` (D2)."""
    from pyguara.audio.types import SpatialAudioConfig
    from pyguara.common.types import Vector2

    audio_system.set_spatial_config(
        SpatialAudioConfig(max_distance=1000, reference_distance=100)
    )
    clip = _make_clip(seconds=1.0)

    near = audio_system.play_sfx_at_position(
        clip, Vector2(0, 0), Vector2(0, 0), volume=1.0
    )
    far = audio_system.play_sfx_at_position(
        clip, Vector2(600, 0), Vector2(0, 0), volume=1.0
    )
    assert near is not None and far is not None and near != far

    # The near play is centred, so its channel volume is observable and must
    # still be full despite the quieter far play that followed.
    assert pygame.mixer.Channel(near).get_volume() == pytest.approx(1.0, abs=0.02)
    # And the clip's Sound was never used as the volume knob.
    assert clip.native_handle.get_volume() == pytest.approx(1.0)


def test_recycled_channel_does_not_inherit_previous_pan(
    audio_system: PygameAudioSystem,
) -> None:
    """A centred sound landing on a reused channel resets the stereo split
    instead of keeping the last sound's hard pan (D3).

    A stale two-argument split leaves ``Channel.get_volume()`` reading 1.0
    (it ignores stereo separation); the centred play must drive it to its
    own volume.
    """
    from pyguara.audio.types import SpatialAudioConfig
    from pyguara.common.types import Vector2

    one_channel = PygameAudioSystem(num_channels=1)
    one_channel.set_spatial_config(SpatialAudioConfig(max_distance=10000))
    try:
        one_channel.play_sfx_at_position(
            _make_clip("left.wav", 0.05),
            Vector2(-9000, 0),
            Vector2(0, 0),
            volume=1.0,
        )
        pygame.mixer.Channel(0).stop()

        centred = one_channel.play_sfx(_make_clip("mid.wav", 0.5), volume=0.5)
        assert centred == 0
        assert pygame.mixer.Channel(0).get_volume() == pytest.approx(0.5, abs=0.02)
    finally:
        pygame.mixer.stop()


def test_stop_sfx_stops_and_forgets_the_channel(
    audio_system: PygameAudioSystem, audio_clip: AudioClip
) -> None:
    channel_id = audio_system.play_sfx(audio_clip)
    assert channel_id is not None
    assert audio_system.is_channel_active(channel_id)

    audio_system.stop_sfx(channel_id)
    assert not pygame.mixer.Channel(channel_id).get_busy()
    assert not audio_system.is_channel_active(channel_id)


def test_invalid_clip_returns_none(audio_system: PygameAudioSystem) -> None:
    class _Broken(AudioClip):
        @property
        def duration(self) -> float:
            return 0.0

        @property
        def native_handle(self) -> Any:
            return None

    assert audio_system.play_sfx(_Broken("broken.wav")) is None


def test_pause_resume_sfx(audio_system: PygameAudioSystem) -> None:
    # The dummy SDL driver does not reflect pause() in get_busy(), so assert
    # the calls route through to the mixer.
    with (
        patch("pygame.mixer.pause") as pause,
        patch("pygame.mixer.unpause") as unpause,
    ):
        audio_system.pause_sfx()
        audio_system.resume_sfx()
    pause.assert_called_once()
    unpause.assert_called_once()


# ========== is_channel_active ==========


def test_is_channel_active_false_for_unknown_channel(
    audio_system: PygameAudioSystem,
) -> None:
    assert audio_system.is_channel_active(5) is False


def test_is_channel_active_false_once_sound_finishes(
    audio_system: PygameAudioSystem,
) -> None:
    import time

    channel_id = audio_system.play_sfx(_make_clip(seconds=0.05))
    assert channel_id is not None
    assert audio_system.is_channel_active(channel_id)

    time.sleep(0.25)
    assert audio_system.is_channel_active(channel_id) is False


def test_is_channel_active_false_when_channel_reused_by_other_sound(
    audio_system: PygameAudioSystem,
) -> None:
    one = PygameAudioSystem(num_channels=1)
    try:
        first = one.play_sfx(_make_clip("first.wav", 2.0))
        assert first == 0
        pygame.mixer.Channel(0).stop()
        # Something unrelated grabs channel 0 directly.
        pygame.mixer.Channel(0).play(_make_clip("other.wav", 2.0).native_handle)
        assert one.is_channel_active(0) is False
    finally:
        pygame.mixer.stop()


# ========== set_channel_mix ==========


def test_set_channel_mix_updates_channel_volume(
    audio_system: PygameAudioSystem, audio_clip: AudioClip
) -> None:
    channel_id = audio_system.play_sfx(audio_clip, volume=1.0)
    assert channel_id is not None

    audio_system.set_channel_mix(channel_id, attenuation=0.4, pan=0.0)
    assert pygame.mixer.Channel(channel_id).get_volume() == pytest.approx(0.4, abs=0.02)


def test_set_channel_mix_ignores_finished_channel(
    audio_system: PygameAudioSystem,
) -> None:
    import time

    channel_id = audio_system.play_sfx(_make_clip(seconds=0.05), volume=1.0)
    assert channel_id is not None
    time.sleep(0.25)
    # Must not raise, must not resurrect volume on a dead channel.
    audio_system.set_channel_mix(channel_id, attenuation=0.4, pan=0.0)
    assert audio_system.is_channel_active(channel_id) is False


def test_set_channel_mix_ignores_unknown_channel(
    audio_system: PygameAudioSystem,
) -> None:
    audio_system.set_channel_mix(99, attenuation=0.5, pan=0.5)  # no raise


# ========== shutdown ==========


def test_shutdown_is_idempotent_and_stops_audio() -> None:
    system = PygameAudioSystem(num_channels=4)
    system.play_sfx(_make_clip(seconds=1.0), loops=-1)

    system.shutdown()
    system.shutdown()  # second call is a no-op, must not raise

    # Bring the module mixer back for the remaining tests.
    pygame.mixer.init(_SAMPLE_RATE, -16, 2, 512)


# ========== Music Playback Tests ==========


def test_play_music(audio_system: PygameAudioSystem, mock_music: Any) -> None:
    audio_system.play_music("music/bgm.ogg", loop=True, fade_ms=1000)

    mock_music.load.assert_called_once_with("music/bgm.ogg")
    mock_music.play.assert_called_once_with(loops=-1, fade_ms=1000)
    mock_music.set_volume.assert_called()


def test_play_music_no_loop(audio_system: PygameAudioSystem, mock_music: Any) -> None:
    audio_system.play_music("music/theme.ogg", loop=False)
    mock_music.play.assert_called_once_with(loops=0, fade_ms=1000)


def test_stop_music(audio_system: PygameAudioSystem, mock_music: Any) -> None:
    audio_system.stop_music(fade_ms=500)
    mock_music.fadeout.assert_called_once_with(500)


def test_pause_resume_music(audio_system: PygameAudioSystem, mock_music: Any) -> None:
    audio_system.pause_music()
    mock_music.pause.assert_called_once()

    audio_system.resume_music()
    mock_music.unpause.assert_called_once()


def test_is_music_playing(audio_system: PygameAudioSystem, mock_music: Any) -> None:
    mock_music.get_busy.return_value = False
    assert not audio_system.is_music_playing()

    mock_music.get_busy.return_value = True
    assert audio_system.is_music_playing()


# ========== AudioManager Tests ==========


def test_audio_manager_initialization(audio_manager: AudioManager) -> None:
    assert audio_manager.get_master_volume() == 1.0
    assert audio_manager.get_current_music() is None


def test_audio_manager_play_music(audio_manager: AudioManager, mock_music: Any) -> None:
    audio_manager.play_music("music/bgm.ogg")

    mock_music.load.assert_called_once_with("music/bgm.ogg")
    mock_music.play.assert_called_once()
    assert audio_manager.get_current_music() == "music/bgm.ogg"


def test_audio_manager_stop_music(audio_manager: AudioManager, mock_music: Any) -> None:
    audio_manager.play_music("music/bgm.ogg")
    audio_manager.stop_music()

    mock_music.fadeout.assert_called_once()
    assert audio_manager.get_current_music() is None


def test_audio_manager_volume_control(audio_manager: AudioManager) -> None:
    audio_manager.set_master_volume(0.7)
    assert audio_manager.get_master_volume() == 0.7

    audio_manager.set_sfx_volume(0.5)
    assert audio_manager.get_sfx_volume() == 0.5

    audio_manager.set_music_volume(0.3)
    assert audio_manager.get_music_volume() == 0.3


def test_audio_manager_pause_resume(
    audio_manager: AudioManager, mock_music: Any
) -> None:
    audio_manager.pause_music()
    mock_music.pause.assert_called_once()

    audio_manager.resume_music()
    mock_music.unpause.assert_called_once()


def test_audio_manager_cleanup_stops_music_and_clears_tracking(
    audio_manager: AudioManager, mock_music: Any
) -> None:
    audio_manager.play_music("music/bgm.ogg")
    audio_manager.cleanup()

    mock_music.fadeout.assert_called_with(0)
    assert audio_manager.get_current_music() is None


def test_audio_manager_play_sfx_clip(
    audio_manager: AudioManager, audio_clip: AudioClip
) -> None:
    channel_id = audio_manager.play_sfx_clip(audio_clip, volume=0.8)
    assert channel_id is not None
    assert pygame.mixer.Channel(channel_id).get_sound() is audio_clip.native_handle


def test_audio_manager_stop_sfx(
    audio_manager: AudioManager, audio_clip: AudioClip
) -> None:
    channel_id = audio_manager.play_sfx_clip(audio_clip, loops=-1)
    assert channel_id is not None
    audio_manager.stop_sfx(channel_id)
    assert not pygame.mixer.Channel(channel_id).get_busy()


# ========== Integration ==========


def test_full_audio_workflow(
    audio_manager: AudioManager, audio_clip: AudioClip, mock_music: Any
) -> None:
    audio_manager.set_master_volume(0.8)
    audio_manager.set_sfx_volume(0.7)
    audio_manager.set_music_volume(0.5)

    audio_manager.play_music("music/bgm.ogg", loop=True)
    channel = audio_manager.play_sfx_clip(audio_clip, volume=1.0)
    assert channel is not None
    assert pygame.mixer.Channel(channel).get_busy()

    audio_manager.pause_music()
    audio_manager.pause_all_sfx()
    audio_manager.resume_music()
    audio_manager.resume_all_sfx()

    audio_manager.stop_music()
    assert audio_manager.get_current_music() is None

    audio_manager.cleanup()
