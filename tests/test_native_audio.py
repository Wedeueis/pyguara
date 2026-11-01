"""The native audio backend, against constructed PCM and measured properties.

There is no parity suite here because there is nothing to be at parity with:
`pygame.mixer` cannot pitch-shift. So the resampler has a bit-exact tier on
input small enough to work out by hand, and real clips get property
assertions, since bit-exact goldens on decoded audio would churn on every
`symphonia` bump. See the decision record on #72.
"""

from __future__ import annotations

import math
import struct
import wave
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pygame
import pytest

from pyguara import native
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.native.loaders import NativeSoundLoader
from pyguara.audio.backends.native.native_audio import (
    MAX_PITCH,
    MIN_PITCH,
    NativeAudioSystem,
)
from pyguara.audio.backends.native.types import NativeAudioClip
from pyguara.audio.backends.pygame.loaders import PygameSoundLoader
from pyguara.audio.exceptions import UnsupportedAudioCapability
from pyguara.audio.types import AudioBusType, AudioCapability, LowPassFilter
from pyguara.config.manager import ConfigManager
from pyguara.config.types import AudioBackend

module = native.native_module()
pytestmark = pytest.mark.skipif(module is None, reason="extension not built")

RATE = 44100


def _pcm(*samples: int) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def _samples(pcm: bytes) -> list[int]:
    return list(struct.unpack(f"<{len(pcm) // 2}h", pcm))


def _write_wav(
    path: Path,
    *,
    seconds: float = 0.5,
    freq: float = 441.0,
    rate: int = RATE,
    channels: int = 1,
) -> Path:
    count = int(seconds * rate)
    tone = [
        round(12000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(count)
    ]
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(struct.pack("<h", s) * channels for s in tone))
    return path


def _dominant_hz(left: np.ndarray, rate: int = RATE) -> float:
    spectrum = np.abs(np.fft.rfft(left * np.hanning(len(left))))
    return float(np.fft.rfftfreq(len(left), 1 / rate)[int(np.argmax(spectrum))])


def _left(sound: pygame.mixer.Sound) -> np.ndarray:
    return np.frombuffer(sound.get_raw(), dtype="<i2")[::2].astype(float)


class TestResampleIsExact:
    """Worked by hand: a slip in the interpolation moves one of these."""

    def test_the_identity_returns_its_input(self) -> None:
        pcm = _pcm(5, -7, 300, -32768, 32767)

        assert module.resample_pcm(pcm, RATE, 1, RATE, 1) == pcm

    def test_an_octave_up_takes_every_other_sample(self) -> None:
        out = module.resample_pcm(_pcm(0, 100, 200, 300, 400), RATE, 1, RATE, 1, 2.0)

        assert _samples(out) == [0, 200, 400]

    def test_an_octave_down_interpolates_between_samples(self) -> None:
        out = module.resample_pcm(_pcm(0, 100, 200), RATE, 1, RATE, 1, 0.5)

        assert _samples(out) == [0, 50, 100, 150, 200]

    def test_interpolation_rounds_rather_than_truncates(self) -> None:
        out = module.resample_pcm(_pcm(0, 3), RATE, 1, RATE, 1, 0.5)

        assert _samples(out) == [0, 2, 3]

    def test_a_rate_conversion_is_the_same_operation(self) -> None:
        out = module.resample_pcm(_pcm(0, 100, 200), 22050, 1, 44100, 1)

        assert _samples(out) == [0, 50, 100, 150, 200]

    def test_mono_spreads_to_both_channels(self) -> None:
        out = module.resample_pcm(_pcm(1, 2), RATE, 1, RATE, 2)

        assert _samples(out) == [1, 1, 2, 2]

    def test_stereo_averages_down_to_mono(self) -> None:
        out = module.resample_pcm(_pcm(10, 20, -10, -30), RATE, 2, RATE, 1)

        assert _samples(out) == [15, -20]

    def test_channels_stay_separate_through_a_pitch(self) -> None:
        out = module.resample_pcm(_pcm(0, 1000, 100, 1100), RATE, 2, RATE, 2, 0.5)

        assert _samples(out) == [0, 1000, 50, 1050, 100, 1100]

    def test_extremes_do_not_wrap(self) -> None:
        out = module.resample_pcm(_pcm(32767, -32768), RATE, 1, RATE, 1, 0.5)

        assert _samples(out)[0] == 32767
        assert _samples(out)[-1] == -32768

    def test_empty_input_is_empty_output(self) -> None:
        assert module.resample_pcm(b"", RATE, 1, RATE, 1, 1.5) == b""

    @pytest.mark.parametrize("pitch", [0.0, -1.0, float("nan"), float("inf")])
    def test_a_meaningless_pitch_is_refused(self, pitch: float) -> None:
        with pytest.raises(ValueError, match="pitch"):
            module.resample_pcm(_pcm(0, 1), RATE, 1, RATE, 1, pitch)

    def test_a_torn_frame_is_refused(self) -> None:
        with pytest.raises(ValueError, match="whole number"):
            module.resample_pcm(_pcm(0, 1, 2), RATE, 2, RATE, 2)


class TestDecode:
    def test_a_wav_decodes_to_exactly_its_samples(self, tmp_path: Path) -> None:
        samples = [0, 1, -1, 12345, -12345, 32767, -32768]
        path = tmp_path / "exact.wav"
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(22050)
            out.writeframes(_pcm(*samples))

        pcm, rate, channels = module.decode_audio(str(path))

        assert _samples(pcm) == samples
        assert (rate, channels) == (22050, 1)

    def test_a_missing_file_says_which(self, tmp_path: Path) -> None:
        with pytest.raises(OSError, match="nope.wav"):
            module.decode_audio(str(tmp_path / "nope.wav"))

    def test_something_that_is_not_audio_says_which(self, tmp_path: Path) -> None:
        path = tmp_path / "text.wav"
        path.write_text("this is not audio")

        with pytest.raises(OSError, match="text.wav"):
            module.decode_audio(str(path))

    @pytest.mark.parametrize("extension", ["wav", "ogg", "mp3", "flac"])
    def test_every_format_the_engine_advertises_decodes(self, extension: str) -> None:
        """A format the loader cannot read fails with no capability to decline.

        `pygame-ce` ships one clip in every format, so no asset is added. MP3
        is off by default in `symphonia` and this is what notices it going.
        """
        data = Path(pygame.__file__).parent / "examples" / "data"
        path = data / f"house_lo.{extension}"
        if not path.exists():
            pytest.skip(f"{path} is not in this pygame-ce")

        pcm, rate, channels = module.decode_audio(str(path))

        assert (rate, channels) == (11025, 1)
        assert len(pcm) / 2 / rate == pytest.approx(7.1, abs=0.2)
        assert max(abs(s) for s in _samples(pcm)) > 1000


@pytest.fixture
def system() -> Iterator[NativeAudioSystem]:
    if pygame.mixer.get_init() is not None:
        pygame.mixer.quit()
    audio = NativeAudioSystem()
    yield audio
    audio.shutdown()


@pytest.fixture
def clip(system: NativeAudioSystem, tmp_path: Path) -> NativeAudioClip:
    loaded = NativeSoundLoader().load(str(_write_wav(tmp_path / "tone.wav")))
    assert isinstance(loaded, NativeAudioClip)
    return loaded


class TestTheLoader:
    def test_a_clip_is_rendered_to_the_mixer_format(
        self, system: NativeAudioSystem, tmp_path: Path
    ) -> None:
        path = _write_wav(tmp_path / "low.wav", seconds=0.5, rate=22050, channels=1)

        clip = NativeSoundLoader().load(str(path))

        # Stereo at 44.1 kHz, whatever the file was: one sample per side, and
        # the length holds, so this is a conversion and not a reinterpretation.
        assert clip.duration == pytest.approx(0.5, abs=0.001)
        assert _dominant_hz(_left(clip.native_handle)) == pytest.approx(441, abs=4)

    def test_it_declares_what_the_pygame_loader_does_and_flac(self) -> None:
        native_types = set(NativeSoundLoader().supported_extensions)

        assert set(PygameSoundLoader().supported_extensions) <= native_types
        assert ".flac" in native_types

    def test_it_refuses_without_a_mixer(self, tmp_path: Path) -> None:
        if pygame.mixer.get_init() is not None:
            pygame.mixer.quit()

        with pytest.raises(RuntimeError, match="mixer"):
            NativeSoundLoader().load(str(_write_wav(tmp_path / "x.wav")))


class TestTheProtocol:
    def test_it_is_an_audio_system(self, system: NativeAudioSystem) -> None:
        assert isinstance(system, IAudioSystem)

    def test_it_reports_exactly_what_it_does(self, system: NativeAudioSystem) -> None:
        assert system.capabilities == (
            AudioCapability.PITCH | AudioCapability.LOOP_POINTS
        )

    def test_bus_effects_are_still_declined(self, system: NativeAudioSystem) -> None:
        with pytest.raises(UnsupportedAudioCapability):
            system.set_bus_effects(AudioBusType.SFX, [LowPassFilter(cutoff_hz=1000.0)])


class TestPitch:
    def test_an_octave_up_doubles_the_frequency_and_halves_the_length(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        pitched = system._pitched(clip, 2.0)

        assert _dominant_hz(_left(pitched)) == pytest.approx(882, abs=6)
        assert pitched.get_length() == pytest.approx(clip.duration / 2, abs=0.001)

    def test_it_does_not_clip_or_change_loudness(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        before = _left(clip.native_handle)
        after = _left(system._pitched(clip, 1.5))

        assert np.max(np.abs(after)) <= 12001
        assert np.sqrt(np.mean(after**2)) == pytest.approx(
            np.sqrt(np.mean(before**2)), rel=0.02
        )

    def test_it_plays_and_is_tracked(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, pitch=1.2)

        assert handle is not None
        assert system.is_sound_active(handle)
        system.stop_sfx(handle)
        assert not system.is_sound_active(handle)

    def test_pitch_also_reaches_a_spatial_sound(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        from pyguara.common.types import Vector2

        handle = system.play_sfx_at_position(
            clip, Vector2(10, 0), Vector2(0, 0), pitch=2.0
        )

        assert handle is not None
        channel = pygame.mixer.Channel(system._playing_sounds[handle].channel_id)
        assert channel.get_sound() is system._pitched(clip, 2.0)

    def test_unity_plays_the_clip_itself_with_no_render(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, pitch=1.001)

        assert handle is not None
        channel = pygame.mixer.Channel(system._playing_sounds[handle].channel_id)
        assert channel.get_sound() is clip.native_handle

    def test_nearby_pitches_share_a_buffer(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        assert system._pitched(clip, 1.201) is system._pitched(clip, 1.199)
        assert system._pitched(clip, 1.21) is not system._pitched(clip, 1.2)

    @pytest.mark.parametrize("pitch", [MIN_PITCH - 0.01, MAX_PITCH + 0.01, 0.0, -1.0])
    def test_outside_the_range_is_refused(
        self, system: NativeAudioSystem, clip: NativeAudioClip, pitch: float
    ) -> None:
        with pytest.raises(ValueError, match="pitch"):
            system.play_sfx(clip, pitch=pitch)

    def test_the_cache_stays_inside_its_budget(self, tmp_path: Path) -> None:
        if pygame.mixer.get_init() is not None:
            pygame.mixer.quit()
        budget = 200_000
        audio = NativeAudioSystem(cache_bytes=budget)
        try:
            clip = NativeSoundLoader().load(str(_write_wav(tmp_path / "t.wav")))
            for step in range(40):
                audio.play_sfx(clip, pitch=1.0 + (step + 1) * 0.01)

            assert audio._cached_bytes <= budget
            assert len(audio._cache) >= 1
        finally:
            audio.shutdown()

    def test_a_clip_from_another_backend_is_refused_by_name(
        self, system: NativeAudioSystem, tmp_path: Path
    ) -> None:
        foreign = PygameSoundLoader().load(str(_write_wav(tmp_path / "p.wav")))

        with pytest.raises(TypeError, match="NativeAudioClip"):
            system.play_sfx(foreign, pitch=1.5)


class TestLoopPoints:
    def test_the_intro_stops_at_the_loop_end_and_the_lap_is_the_region(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        buffers = system._loop_buffers(clip, 1.0, 0.1, 0.3)

        assert buffers.intro.get_length() == pytest.approx(0.3, abs=0.001)
        assert buffers.lap.get_length() == pytest.approx(0.2, abs=0.001)

    def test_a_segment_is_whole_laps_of_at_least_a_second(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        buffers = system._loop_buffers(clip, 1.0, 0.1, 0.3)

        lap = len(buffers.lap.get_raw())
        assert len(buffers.segment.get_raw()) == lap * buffers.laps_per_segment
        assert buffers.segment.get_length() >= 1.0

    def test_seconds_name_positions_in_the_clip_at_any_pitch(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        buffers = system._loop_buffers(clip, 2.0, 0.1, 0.3)

        assert buffers.lap.get_length() == pytest.approx(0.1, abs=0.001)

    def test_a_queued_segment_follows_the_intro(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loops=-1, loop_start=0.1, loop_end=0.3)

        assert handle is not None
        channel = pygame.mixer.Channel(system._playing_sounds[handle].channel_id)
        assert channel.get_queue() is not None
        assert system.is_sound_active(handle)

    def test_a_one_shot_ignores_loop_points(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loop_start=0.1, loop_end=0.3)

        assert handle is not None
        assert handle not in system._loops

    def test_a_sidecars_points_are_honoured_where_pygame_warned(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        from pyguara.resources.meta import AudioMeta

        clip.import_meta = AudioMeta(loop_start=0.1, loop_end=0.3)

        handle = system.play_sfx(clip, loops=-1)

        assert handle in system._loops

    def test_a_region_past_the_end_of_the_clip_is_refused(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        with pytest.raises(ValueError, match="empty"):
            system.play_sfx(clip, loops=-1, loop_start=5.0, loop_end=6.0)

    def test_an_inverted_region_is_refused_even_for_a_one_shot(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        with pytest.raises(ValueError, match="greater"):
            system.play_sfx(clip, loop_start=0.3, loop_end=0.1)

    def test_a_stopped_loop_queues_nothing_more(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loops=-1, loop_start=0.1, loop_end=0.3)
        assert handle is not None
        channel = pygame.mixer.Channel(system._playing_sounds[handle].channel_id)

        system.stop_sfx(handle)
        system.update()

        assert handle not in system._loops
        assert channel.get_queue() is None

    def test_update_does_not_touch_a_recycled_channel(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loops=-1, loop_start=0.1, loop_end=0.3)
        assert handle is not None
        channel = pygame.mixer.Channel(system._playing_sounds[handle].channel_id)
        channel.stop()
        other = pygame.mixer.Sound(buffer=b"\0" * 44100)
        channel.play(other)

        system.update()

        assert channel.get_queue() is None
        assert not system.is_sound_active(handle)

    def test_finite_loops_count_down_to_nothing(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loops=1, loop_start=0.1, loop_end=0.3)
        assert handle is not None

        assert system._loops[handle].remaining == 0
        queued = pygame.mixer.Channel(
            system._playing_sounds[handle].channel_id
        ).get_queue()
        assert queued is system._loops[handle].buffers.lap


class TestLapsAreCountedOnce:
    """`Channel.queue` replaces what is pending, so re-queueing eats laps."""

    def test_update_leaves_a_full_queue_and_its_count_alone(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loops=50, loop_start=0.1, loop_end=0.3)
        assert handle is not None
        remaining = system._loops[handle].remaining
        assert remaining == 50 - system._loops[handle].buffers.laps_per_segment

        for _ in range(5):
            system.update()

        assert system._loops[handle].remaining == remaining


class TestTheSwitch:
    def test_no_auto_exists(self) -> None:
        """An `auto` would vary a game's capabilities by machine."""
        assert {b.value for b in AudioBackend} == {"pygame", "native"}

    def test_the_default_is_pygame(self) -> None:
        assert ConfigManager().config.audio.backend is AudioBackend.PYGAME

    def test_the_debug_switch_does_not_govern_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`PYGUARA_NO_NATIVE=1` must not change what a game can ask for."""
        monkeypatch.setenv("PYGUARA_NO_NATIVE", "1")
        native.reset_for_tests()
        try:
            assert native.native_module() is None
            assert native.require_extension("a test") is not None
        finally:
            monkeypatch.delenv("PYGUARA_NO_NATIVE")
            native.reset_for_tests()

    def test_a_missing_extension_fails_at_startup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(__import__("sys").modules, native._MODULE_NAME, None)
        monkeypatch.setattr(native, "_candidate_paths", list)

        with pytest.raises(RuntimeError, match="native extension"):
            NativeAudioSystem()

    def test_only_signed_16_bit_is_accepted(self) -> None:
        with pytest.raises(ValueError, match="-16"):
            NativeAudioSystem(size=16)
