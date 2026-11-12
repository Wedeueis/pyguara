"""The native audio backend, against constructed PCM and measured properties.

There is no parity suite here because there is nothing to be at parity with:
`pygame.mixer` cannot pitch-shift. So the resampler has a bit-exact tier on
input small enough to work out by hand, and the mixer is driven offline --
nothing advances until `render` -- and its output measured: a frequency, a
length, a gain, where a lap ends. Bit-exact goldens on decoded audio would
churn on every `symphonia` bump. See the decision record on #72.
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
from pyguara.audio.exceptions import UnsupportedAudioCapability
from pyguara.audio.types import (
    AudioBusType,
    AudioCapability,
    AudioPriority,
    LowPassFilter,
)
from pyguara.common.types import Vector2
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
    audio = NativeAudioSystem(frequency=RATE, output="offline")
    yield audio
    audio.shutdown()


def _load(system: NativeAudioSystem, path: Path) -> NativeAudioClip:
    loaded = NativeSoundLoader(system.mixer).load(str(path))
    assert isinstance(loaded, NativeAudioClip)
    return loaded


@pytest.fixture
def clip(system: NativeAudioSystem, tmp_path: Path) -> NativeAudioClip:
    return _load(system, _write_wav(tmp_path / "tone.wav"))


def _render(system: NativeAudioSystem, frames: int) -> np.ndarray:
    """The next `frames` frames of the mix, as an `(n, 2)` float array."""
    raw = system.mixer.render(frames)
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2).astype(float)


def _length(system: NativeAudioSystem, handle: object, limit: int = RATE * 5) -> int:
    """How many frames a sound plays for, rendering until it ends."""
    played = 0
    while system.is_sound_active(handle) and played < limit:  # type: ignore[arg-type]
        _render(system, 64)
        played += 64
    return played


class TestTheLoader:
    def test_a_clip_is_converted_to_the_mixer_rate(
        self, system: NativeAudioSystem, tmp_path: Path
    ) -> None:
        path = _write_wav(tmp_path / "low.wav", seconds=0.5, rate=22050, channels=1)

        clip = _load(system, path)

        # The length holds, so this is a conversion and not a reinterpretation.
        assert clip.duration == pytest.approx(0.5, abs=0.001)
        assert clip.frames == pytest.approx(RATE / 2, abs=2)
        system.play_sfx(clip)
        assert _dominant_hz(_render(system, 8192)[:, 0]) == pytest.approx(441, abs=6)

    def test_it_declares_what_the_pygame_loader_does_and_flac(self) -> None:
        extensions = set(NativeSoundLoader(None).supported_extensions)
        assert {".wav", ".ogg", ".mp3", ".flac"} <= extensions

    def test_a_file_that_is_not_audio_says_which(
        self, system: NativeAudioSystem, tmp_path: Path
    ) -> None:
        path = tmp_path / "noise.wav"
        path.write_bytes(b"not audio")
        with pytest.raises(OSError, match="noise.wav"):
            _load(system, path)


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

    def test_it_says_where_the_mix_goes(self, system: NativeAudioSystem) -> None:
        assert system.output == "offline"
        assert system.rate == RATE


class TestPlaying:
    def test_a_sound_plays_its_samples_and_ends(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip)

        assert handle is not None
        assert system.is_sound_active(handle)
        assert _length(system, handle) == pytest.approx(clip.frames, abs=64)
        assert not system.is_sound_active(handle)

    def test_volume_and_pan_reach_the_two_sides(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        system.play_sfx_at_position(clip, Vector2(200, 0), Vector2(0, 0), volume=0.5)

        mix = _render(system, 4096)
        left, right = np.abs(mix[:, 0]).max(), np.abs(mix[:, 1]).max()
        # The sound is to the right, so the left is turned down.
        assert 0 < left < right <= 0.5 * 12000 / 32768 + 1e-3

    def test_stopping_silences_at_once(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip)
        _render(system, 100)
        assert handle is not None
        system.stop_sfx(handle)

        assert not system.is_sound_active(handle)
        assert np.abs(_render(system, 256)).max() == 0

    def test_pausing_effects_holds_them_where_they_are(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip)
        system.pause_sfx()

        assert np.abs(_render(system, RATE)).max() == 0
        assert system.is_sound_active(handle)  # type: ignore[arg-type]
        system.resume_sfx()
        assert _length(system, handle) == pytest.approx(clip.frames, abs=64)

    def test_a_bus_volume_reaches_a_sound_already_playing(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        """pygame fixed a channel's loudness at its start; this does not."""
        system.play_sfx(clip, loops=-1)
        before = np.abs(_render(system, 4096)).max()

        system.set_sfx_volume(0.25)

        assert np.abs(_render(system, 4096)).max() == pytest.approx(
            before / 4, rel=0.02
        )

    def test_a_full_mixer_steals_from_a_lower_priority(
        self, clip: NativeAudioClip
    ) -> None:
        audio = NativeAudioSystem(frequency=RATE, num_channels=2, output="offline")
        try:
            loaded = _load(audio, Path(clip.path))
            low = audio.play_sfx(loaded, priority=AudioPriority.LOW)
            normal = audio.play_sfx(loaded)
            high = audio.play_sfx(loaded, priority=AudioPriority.HIGH)
            refused = audio.play_sfx(loaded, priority=AudioPriority.LOW)

            assert high is not None and refused is None
            assert not audio.is_sound_active(low)  # type: ignore[arg-type]
            assert audio.is_sound_active(normal)  # type: ignore[arg-type]
        finally:
            audio.shutdown()


class TestPitch:
    def test_an_octave_up_doubles_the_frequency_and_halves_the_length(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, pitch=2.0)
        assert _dominant_hz(_render(system, 8192)[:, 0]) == pytest.approx(882, abs=8)

        played = 8192 + _length(system, handle)
        assert played == pytest.approx(clip.frames / 2, abs=64)

    def test_pitch_is_continuous(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        """No longer quantised to 1%: 1.003 is heard as 1.003."""
        handle = system.play_sfx(clip, pitch=1.03)
        assert _length(system, handle) == pytest.approx(clip.frames / 1.03, abs=64)

    def test_it_does_not_clip_or_change_loudness(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        plain_handle = system.play_sfx(clip)
        plain = _render(system, 8192)[:, 0]
        system.stop_sfx(plain_handle)  # type: ignore[arg-type]
        system.play_sfx(clip, pitch=1.5)
        pitched = _render(system, 8192)[:, 0]

        assert np.abs(pitched).max() <= 12001 / 32768
        assert np.sqrt(np.mean(pitched**2)) == pytest.approx(
            np.sqrt(np.mean(plain**2)), rel=0.02
        )

    def test_pitch_also_reaches_a_spatial_sound(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        system.play_sfx_at_position(clip, Vector2(10, 0), Vector2(0, 0), pitch=2.0)
        assert _dominant_hz(_render(system, 8192)[:, 1]) == pytest.approx(882, abs=8)

    @pytest.mark.parametrize("pitch", [MIN_PITCH / 2, MAX_PITCH * 2])
    def test_outside_the_range_is_refused(
        self, system: NativeAudioSystem, clip: NativeAudioClip, pitch: float
    ) -> None:
        with pytest.raises(ValueError, match="pitch"):
            system.play_sfx(clip, pitch=pitch)

    def test_a_clip_from_another_backend_is_refused_by_name(
        self, system: NativeAudioSystem
    ) -> None:
        class Foreign(NativeAudioClip.__mro__[1]):  # type: ignore[misc,valid-type]
            duration = 1.0
            native_handle = None

        with pytest.raises(TypeError, match="NativeAudioClip"):
            system.play_sfx(Foreign("elsewhere.wav"))


class TestLoopPoints:
    def test_the_intro_then_laps_of_the_region(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loops=3, loop_start=0.1, loop_end=0.3)

        lap = round(0.2 * RATE)
        assert _length(system, handle) == pytest.approx(
            round(0.3 * RATE) + 3 * lap, abs=64
        )

    def test_the_region_is_in_the_clips_seconds_at_any_pitch(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, pitch=2.0, loops=1, loop_start=0.1, loop_end=0.3)

        # Intro to 0.3 s and one lap of 0.2 s, each half as long at pitch 2.
        assert _length(system, handle) == pytest.approx(0.25 * RATE, abs=64)

    def test_the_seam_is_sample_exact(self, system: NativeAudioSystem) -> None:
        """A lap ends on the frame before the start, with no gap or repeat."""
        ramp = struct.pack("<8h", *(1000 * i for i in range(8)))
        samples = system.mixer.clip(ramp, RATE, 1)
        system.mixer.play(samples, 1.0, 1.0, loops=2, loop_start=2.0, loop_end=6.0)

        out = np.frombuffer(system.mixer.render(16), dtype="<f4")[::2]
        heard = [round(float(v) * 32768) for v in out]
        assert heard == [0, 1000, 2000, 3000, 4000, 5000, 2000, 3000, 4000, 5000,
                         2000, 3000, 4000, 5000, 0, 0]  # fmt: skip

    def test_forever_keeps_going(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loops=-1, loop_start=0.1, loop_end=0.3)
        _render(system, RATE * 3)
        assert system.is_sound_active(handle)  # type: ignore[arg-type]

    def test_a_one_shot_ignores_loop_points(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        handle = system.play_sfx(clip, loop_start=0.1, loop_end=0.3)
        assert _length(system, handle) == pytest.approx(clip.frames, abs=64)

    def test_a_sidecars_points_are_honoured(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        from pyguara.resources.meta import AudioMeta

        clip.import_meta = AudioMeta(loop_start=0.1, loop_end=0.3)
        handle = system.play_sfx(clip, loops=1)

        assert _length(system, handle) == pytest.approx(0.5 * RATE, abs=64)

    def test_a_region_past_the_end_of_the_clip_is_refused(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        with pytest.raises(ValueError, match="empty"):
            system.play_sfx(clip, loops=1, loop_start=0.6, loop_end=0.9)

    def test_an_inverted_region_is_refused_even_for_a_one_shot(
        self, system: NativeAudioSystem, clip: NativeAudioClip
    ) -> None:
        with pytest.raises(ValueError):
            system.play_sfx(clip, loop_start=0.3, loop_end=0.1)


class TestMusic:
    def test_a_track_decodes_off_the_frame_then_plays_and_fades_in(
        self, system: NativeAudioSystem, tmp_path: Path
    ) -> None:
        import time

        path = _write_wav(tmp_path / "music.wav", seconds=1.0)
        system.play_music(str(path), loop=False, fade_ms=100)
        assert system.is_music_playing()  # decoding counts as playing

        heard = np.zeros(0)
        for _ in range(200):
            heard = _render(system, 8820)[:, 0]
            if np.abs(heard).max() > 0:
                break
            time.sleep(0.01)
        # A 100 ms fade: the first 10 ms is far quieter than the last.
        assert np.abs(heard[:441]).max() < 0.25 * np.abs(heard[-441:]).max()

    def test_stopping_fades_out_then_ends(
        self, system: NativeAudioSystem, tmp_path: Path
    ) -> None:
        import time

        system.play_music(str(_write_wav(tmp_path / "m.wav", seconds=2.0)), fade_ms=0)
        for _ in range(200):
            if np.abs(_render(system, 441)).max() > 0:
                break
            time.sleep(0.01)
        system.stop_music(fade_ms=50)

        assert system.is_music_playing()
        _render(system, round(0.06 * RATE))
        assert not system.is_music_playing()

    def test_a_file_that_will_not_decode_plays_nothing(
        self, system: NativeAudioSystem, tmp_path: Path
    ) -> None:
        import time

        bad = tmp_path / "bad.ogg"
        bad.write_bytes(b"nope")
        system.play_music(str(bad))
        for _ in range(200):
            if not system.is_music_playing():
                break
            time.sleep(0.01)
        assert not system.is_music_playing()


class TestTheSwitch:
    def test_no_auto_exists(self) -> None:
        """An `auto` would vary a game's capabilities by machine."""
        assert {b.value for b in AudioBackend} == {"pygame", "native"}

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

    def test_an_unknown_output_is_refused(self) -> None:
        with pytest.raises(ValueError, match="offline"):
            NativeAudioSystem(output="speakers")
