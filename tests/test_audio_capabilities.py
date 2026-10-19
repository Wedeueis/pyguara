"""What a backend can do, and what it refuses to pretend it can.

`IAudioSystem` advertises three things no `pygame.mixer` can express --
per-play pitch, loop points inside a clip, and DSP on a bus. Each one is
declared through `AudioCapability` and declined by raising, so a request
the mixer cannot honour fails where it was made rather than playing
something subtly wrong. These tests pin the declining, the one case that
warns instead, and the signatures the protocol and its backend have to
keep in step.
"""

import inspect
import logging
import os
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from pyguara.audio.audio_source_system import AudioSourceSystem  # noqa: E402
from pyguara.audio.audio_system import (  # noqa: E402
    IAudioSystem,
    require_capability,
    resolve_loop_points,
)
from pyguara.audio.backends.pygame.pygame_audio import (  # noqa: E402
    PygameAudioSystem,
)
from pyguara.audio.components import AudioSource  # noqa: E402
from pyguara.audio.exceptions import UnsupportedAudioCapability  # noqa: E402
from pyguara.audio.manager import AudioManager  # noqa: E402
from pyguara.audio.types import (  # noqa: E402
    AudioBusType,
    AudioCapability,
    AudioEffect,
    HighPassFilter,
    LowPassFilter,
    Reverb,
    SoundHandle,
    SpatialAudioConfig,
    new_sound_handle,
)
from pyguara.common.components import Transform  # noqa: E402
from pyguara.common.types import Vector2  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.resources.meta import AudioMeta  # noqa: E402
from pyguara.resources.types import AudioClip  # noqa: E402

_SAMPLE_RATE = 44100


@pytest.fixture(autouse=True, scope="module")
def _mixer() -> Iterator[None]:
    """Bring the real (dummy-driver) mixer up for the module."""
    pygame.mixer.init(_SAMPLE_RATE, -16, 2, 512)
    yield
    pygame.mixer.quit()


def _make_clip(path: str = "test.wav", seconds: float = 1.0) -> AudioClip:
    """A real AudioClip wrapping a real Sound of `seconds` of silence."""
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
def audio_system() -> Iterator[PygameAudioSystem]:
    system = PygameAudioSystem(num_channels=8)
    yield system
    pygame.mixer.stop()


class _CapableSystem:
    """A stand-in backend that advertises everything.

    Not a mock: the point of these tests is that the *same* request
    succeeds where the capability exists and raises where it does not, so
    one side of that comparison has to be a system that says yes. It
    records what it was asked for and plays nothing.
    """

    def __init__(self) -> None:
        self.played: list[dict[str, Any]] = []
        self.effects: dict[AudioBusType, tuple[AudioEffect, ...]] = {}

    @property
    def capabilities(self) -> AudioCapability:
        return (
            AudioCapability.PITCH
            | AudioCapability.LOOP_POINTS
            | AudioCapability.BUS_EFFECTS
        )

    def play_sfx(self, clip: AudioClip, **kwargs: Any) -> SoundHandle:
        start, end, _explicit = resolve_loop_points(
            clip, kwargs.get("loop_start"), kwargs.get("loop_end")
        )
        self.played.append(
            {"clip": clip.path, "pitch": kwargs.get("pitch", 1.0), "loop": (start, end)}
        )
        return new_sound_handle()

    def set_bus_effects(
        self, bus: AudioBusType, effects: Sequence[AudioEffect]
    ) -> None:
        require_capability(self, AudioCapability.BUS_EFFECTS)  # type: ignore[arg-type]
        self.effects[bus] = tuple(effects)

    def get_bus_effects(self, bus: AudioBusType) -> tuple[AudioEffect, ...]:
        return self.effects.get(bus, ())


# ========== Declaration ==========


class TestCapabilityDeclaration:
    """A backend states what it can do, and the engine reads it."""

    def test_the_pygame_backend_declares_none(
        self, audio_system: PygameAudioSystem
    ) -> None:
        assert audio_system.capabilities is AudioCapability.NONE

    def test_the_manager_reports_its_backend_capabilities(
        self, audio_system: PygameAudioSystem
    ) -> None:
        """A game holding only an `AudioManager` can still find out."""
        assert AudioManager(audio_system).capabilities is AudioCapability.NONE

        capable = _CapableSystem()
        assert AudioManager(capable).capabilities == capable.capabilities  # type: ignore[arg-type]

    def test_require_capability_passes_when_present(self) -> None:
        require_capability(_CapableSystem(), AudioCapability.PITCH)  # type: ignore[arg-type]

    def test_require_capability_raises_when_absent(
        self, audio_system: PygameAudioSystem
    ) -> None:
        with pytest.raises(UnsupportedAudioCapability) as excinfo:
            require_capability(audio_system, AudioCapability.PITCH)

        error = excinfo.value
        assert error.capability is AudioCapability.PITCH
        assert error.backend == "PygameAudioSystem"
        # The message has to name both, since it is all a caller sees.
        assert "PITCH" in str(error)
        assert "PygameAudioSystem" in str(error)


# ========== Pitch ==========


class TestPitch:
    """`pitch` is declined by raising, and only when actually asked for."""

    def test_the_default_pitch_always_plays(
        self, audio_system: PygameAudioSystem
    ) -> None:
        """1.0 means "not asked for", so it must never raise anywhere."""
        assert audio_system.play_sfx(_make_clip(), pitch=1.0) is not None

    def test_a_shifted_pitch_raises(self, audio_system: PygameAudioSystem) -> None:
        with pytest.raises(UnsupportedAudioCapability):
            audio_system.play_sfx(_make_clip(), pitch=1.2)

    def test_a_shifted_pitch_raises_through_the_manager(
        self, audio_system: PygameAudioSystem
    ) -> None:
        with pytest.raises(UnsupportedAudioCapability):
            AudioManager(audio_system).play_sfx_clip(_make_clip(), pitch=0.8)

    def test_a_shifted_pitch_raises_even_out_of_earshot(
        self, audio_system: PygameAudioSystem
    ) -> None:
        """The report must not depend on where the listener is standing.

        `play_sfx_at_position` returns early for a source past
        `max_distance`, so a capability checked inside the play would be
        checked for a near source and skipped for a far one -- the same
        call raising or not depending on gameplay.
        """
        audio_system.set_spatial_config(
            SpatialAudioConfig(max_distance=100.0, reference_distance=10.0)
        )
        with pytest.raises(UnsupportedAudioCapability):
            audio_system.play_sfx_at_position(
                _make_clip(),
                Vector2(10_000, 0),
                Vector2(0, 0),
                pitch=1.5,
            )

    def test_a_capable_backend_accepts_it(self) -> None:
        system = _CapableSystem()
        system.play_sfx(_make_clip(), pitch=1.5)
        assert system.played[0]["pitch"] == 1.5


class TestPitchThroughTheComponent:
    """`AudioSource.pitch` reaches the backend, and is declined there."""

    def _entity_with(self, manager: EntityManager, source: AudioSource) -> None:
        entity = manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        entity.add_component(source)

    def test_a_default_source_plays(self, audio_system: PygameAudioSystem) -> None:
        manager = EntityManager()
        clip = _make_clip("ecs.wav")
        self._entity_with(
            manager, AudioSource(clip_path="ecs.wav", spatial=False, auto_play=True)
        )
        system = AudioSourceSystem(manager, audio_system, _StubResources(clip))

        system.update(0.016)

        entity = next(iter(manager.get_entities_with(AudioSource)))
        assert entity.get_component(AudioSource).handle is not None

    def test_a_pitched_source_raises(self, audio_system: PygameAudioSystem) -> None:
        manager = EntityManager()
        clip = _make_clip("ecs.wav")
        self._entity_with(
            manager,
            AudioSource(clip_path="ecs.wav", spatial=False, auto_play=True, pitch=0.5),
        )
        system = AudioSourceSystem(manager, audio_system, _StubResources(clip))

        with pytest.raises(UnsupportedAudioCapability):
            system.update(0.016)


class _StubResources:
    """The narrowest resource manager `AudioSourceSystem` will accept."""

    def __init__(self, clip: AudioClip) -> None:
        self._clip = clip

    def load(self, path: str, kind: type) -> AudioClip:
        return self._clip


# ========== Loop points ==========


class TestLoopPointResolution:
    """`resolve_loop_points` decides what applies, and who asked."""

    def test_nothing_requested(self) -> None:
        assert resolve_loop_points(_make_clip(), None, None) == (None, None, False)

    def test_an_explicit_start_is_explicit(self) -> None:
        assert resolve_loop_points(_make_clip(), 1.5, None) == (1.5, None, True)

    def test_an_end_alone_implies_the_top(self) -> None:
        """ "Loop up to here" is a whole request, not half of one."""
        assert resolve_loop_points(_make_clip(), None, 4.0) == (0.0, 4.0, True)

    def test_metadata_supplies_a_default(self) -> None:
        clip = _make_clip("music.ogg")
        clip.import_meta = AudioMeta(loop_start=2.0, loop_end=30.0)

        assert resolve_loop_points(clip, None, None) == (2.0, 30.0, False)

    def test_an_argument_beats_metadata(self) -> None:
        clip = _make_clip("music.ogg")
        clip.import_meta = AudioMeta(loop_start=2.0, loop_end=30.0)

        assert resolve_loop_points(clip, 9.0, None) == (9.0, None, True)

    def test_a_negative_start_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="loop_start"):
            resolve_loop_points(_make_clip(), -1.0, None)

    def test_an_inverted_range_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="loop_end"):
            resolve_loop_points(_make_clip(), 5.0, 2.0)


class TestLoopPointsOnAnIncapableBackend:
    """Arguments raise; a sidecar warns once. The asymmetry is deliberate."""

    def test_explicit_loop_points_raise(self, audio_system: PygameAudioSystem) -> None:
        with pytest.raises(UnsupportedAudioCapability):
            audio_system.play_sfx(_make_clip(), loops=-1, loop_start=1.0)

    def test_a_one_shot_ignores_loop_points(
        self, audio_system: PygameAudioSystem
    ) -> None:
        """`loops=0` ignores loop points on every backend, so declining
        them here would report a difference that does not exist."""
        assert audio_system.play_sfx(_make_clip(), loops=0, loop_start=1.0) is not None

    def test_a_malformed_range_is_rejected_before_the_capability(
        self, audio_system: PygameAudioSystem
    ) -> None:
        """Validation comes first, so a bad range reads the same on every
        backend rather than being masked by whichever one is in use."""
        with pytest.raises(ValueError):
            audio_system.play_sfx(_make_clip(), loops=-1, loop_start=8.0, loop_end=2.0)

    def test_metadata_loop_points_warn_and_play(
        self, audio_system: PygameAudioSystem, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A sidecar is the asset describing itself, not a call site asking.

        Refusing to play would let one line of metadata silence a sound
        that worked before anybody wrote it.
        """
        clip = _make_clip("bed.ogg")
        clip.import_meta = AudioMeta(loop_start=2.0, loop_end=30.0)

        with caplog.at_level(logging.WARNING):
            assert audio_system.play_sfx(clip, loops=-1) is not None

        assert "bed.ogg" in caplog.text
        assert "LOOP_POINTS" in caplog.text

    def test_the_metadata_warning_fires_once_per_clip(
        self, audio_system: PygameAudioSystem, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A looping cue restarted every few seconds must not fill the log."""
        clip = _make_clip("bed.ogg")
        clip.import_meta = AudioMeta(loop_start=2.0)

        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                audio_system.play_sfx(clip, loops=-1)

        assert caplog.text.count("bed.ogg") == 1

    def test_a_one_shot_with_metadata_does_not_warn(
        self, audio_system: PygameAudioSystem, caplog: pytest.LogCaptureFixture
    ) -> None:
        clip = _make_clip("hit.wav")
        clip.import_meta = AudioMeta(loop_start=2.0)

        with caplog.at_level(logging.WARNING):
            audio_system.play_sfx(clip, loops=0)

        assert "hit.wav" not in caplog.text

    def test_a_capable_backend_honours_metadata(self) -> None:
        clip = _make_clip("music.ogg")
        clip.import_meta = AudioMeta(loop_start=2.0, loop_end=30.0)
        system = _CapableSystem()

        system.play_sfx(clip, loops=-1)

        assert system.played[0]["loop"] == (2.0, 30.0)


# ========== Bus DSP ==========


class TestBusEffects:
    """A chain is declined, except the one call that clears nothing."""

    def test_clearing_is_accepted(self, audio_system: PygameAudioSystem) -> None:
        audio_system.set_bus_effects(AudioBusType.MUSIC, [])
        assert audio_system.get_bus_effects(AudioBusType.MUSIC) == ()

    def test_installing_a_chain_raises(self, audio_system: PygameAudioSystem) -> None:
        with pytest.raises(UnsupportedAudioCapability):
            audio_system.set_bus_effects(AudioBusType.MUSIC, [Reverb()])

    def test_a_declined_chain_is_not_reported_as_installed(
        self, audio_system: PygameAudioSystem
    ) -> None:
        """Holding a chain it will never apply would make `get_bus_effects`
        describe an effect nobody can hear."""
        with pytest.raises(UnsupportedAudioCapability):
            audio_system.set_bus_effects(AudioBusType.SFX, [LowPassFilter(800.0)])

        assert audio_system.get_bus_effects(AudioBusType.SFX) == ()

    def test_a_capable_backend_keeps_the_chain_in_order(self) -> None:
        system = _CapableSystem()
        chain: list[AudioEffect] = [LowPassFilter(800.0), Reverb(room_size=0.9)]

        system.set_bus_effects(AudioBusType.SFX, chain)

        assert system.get_bus_effects(AudioBusType.SFX) == tuple(chain)


class TestEffectValidation:
    """An effect rejects parameters no DSP could realise, at construction."""

    @pytest.mark.parametrize("cutoff", [0.0, -1.0])
    def test_a_filter_needs_a_positive_cutoff(self, cutoff: float) -> None:
        with pytest.raises(ValueError, match="cutoff_hz"):
            LowPassFilter(cutoff)
        with pytest.raises(ValueError, match="cutoff_hz"):
            HighPassFilter(cutoff)

    @pytest.mark.parametrize(
        ("field", "value"),
        [("room_size", 1.5), ("damping", -0.1), ("wet", 2.0), ("dry", -1.0)],
    )
    def test_reverb_parameters_are_unit_range(self, field: str, value: float) -> None:
        with pytest.raises(ValueError, match=field):
            Reverb(**{field: value})

    def test_the_defaults_are_valid(self) -> None:
        """Every effect has to be constructible with no arguments, or the
        protocol advertises a type nobody can make."""
        assert LowPassFilter().cutoff_hz > 0
        assert HighPassFilter().cutoff_hz > 0
        assert Reverb().room_size == 0.5


# ========== Handles ==========


class TestSoundHandle:
    """What makes a handle safer than a channel number."""

    def test_tokens_are_unique_across_systems(self) -> None:
        """The counter is process-wide, so two backends cannot mint the
        same handle and resolve each other's sounds."""
        handles = {new_sound_handle() for _ in range(1000)}
        assert len(handles) == 1000

    def test_a_handle_is_hashable_and_frozen(self) -> None:
        handle = new_sound_handle()
        assert {handle: "ok"}[handle] == "ok"
        with pytest.raises(AttributeError):
            handle.token = 5  # type: ignore[misc]

    def test_two_plays_of_one_clip_get_different_handles(
        self, audio_system: PygameAudioSystem
    ) -> None:
        clip = _make_clip(seconds=2.0)
        first = audio_system.play_sfx(clip)
        second = audio_system.play_sfx(clip)

        assert first is not None and second is not None
        assert first != second


# ========== Protocol conformance ==========


def _parameters(function: object) -> list[tuple[str, object]]:
    """The `(name, default)` pairs of a method, `self` dropped."""
    signature = inspect.signature(function)  # type: ignore[arg-type]
    return [
        (name, parameter.default)
        for name, parameter in signature.parameters.items()
        if name != "self"
    ]


def _signature_drift(protocol: type, implementation: type) -> list[str]:
    """Every public method whose signature differs from the protocol's."""
    drift = []
    for name, declared in inspect.getmembers(protocol, inspect.isfunction):
        if name.startswith("_"):
            continue
        provided = getattr(implementation, name, None)
        if not callable(provided):
            drift.append(f"{name}: missing entirely")
            continue
        want, have = _parameters(declared), _parameters(provided)
        if want != have:
            drift.append(f"{name}: protocol takes {want}, implementation takes {have}")
    return drift


class TestTheBackendKeepsTheProtocolSignature:
    """`isinstance` against a runtime-checkable Protocol compares method
    *names*, so a parameter the protocol advertises can be missing from a
    backend and nothing notices until the first call that passes it.

    This protocol just grew three parameters on two methods and renamed
    three more, which is exactly the situation that drifted `IRenderer.
    draw_texture` -- see `tests/test_graphics_protocol_conformance.py`,
    where the same check found it.
    """

    def test_the_pygame_backend_matches(self) -> None:
        assert _signature_drift(IAudioSystem, PygameAudioSystem) == []

    def test_the_backend_satisfies_the_protocol_structurally(
        self, audio_system: PygameAudioSystem
    ) -> None:
        assert isinstance(audio_system, IAudioSystem)

    def test_the_drift_check_can_actually_fail(self) -> None:
        """The control: a reflection-driven comparison is easy to write so
        loosely that it never reports anything."""

        class Behind:
            def play_sfx(self, clip: object) -> None: ...

        drift = _signature_drift(IAudioSystem, Behind)
        assert any("play_sfx" in line for line in drift)
