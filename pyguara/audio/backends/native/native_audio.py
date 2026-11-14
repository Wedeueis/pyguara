"""The audio backend that owns its device: pitch, loop points, no pygame."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pyguara import native
from pyguara.audio.audio_system import require_capability, resolve_loop_points
from pyguara.audio.types import (
    AudioBusManager,
    AudioBusType,
    AudioCapability,
    AudioEffect,
    AudioPriority,
    PlayingSoundInfo,
    SoundHandle,
    SpatialAudioConfig,
    new_sound_handle,
)
from pyguara.common.types import Vector2
from pyguara.log import get_logger
from pyguara.resources.meta import AudioMeta
from pyguara.resources.types import AudioClip

from .types import NativeAudioClip

logger = get_logger(__name__)

MIN_PITCH = 0.25
"""Two octaves down. Below this a clip is too stretched to be a variation."""

MAX_PITCH = 4.0
"""Two octaves up. Linear interpolation aliases audibly well before this."""


@dataclass(slots=True)
class _Playing:
    """What a voice was asked for, so its gains can be worked out again."""

    info: PlayingSoundInfo
    voice: int
    gain: float
    """Base volume times the clip's and its sidecar's gain: all but the bus."""
    attenuation: float
    pan: float


def _stereo(volume: float, pan: float) -> tuple[float, float]:
    """Split a volume into left and right gains for a pan.

    The same law `PygameAudioSystem` uses on a channel: the far side is
    turned down, the near side left alone, so a centred sound and a panned
    one are equally loud on the side they favour.

    Args:
        volume: Loudness, 0.0 to 1.0.
        pan: -1.0 full left, 0.0 centred, 1.0 full right.

    Returns:
        `(left, right)`.
    """
    pan = max(-1.0, min(1.0, pan))
    if pan >= 0.0:
        return volume * (1.0 - pan), volume
    return volume, volume * (1.0 + pan)


class NativeAudioSystem:
    """An audio system on the native mixer (`rust/src/mixer.rs`).

    The mixer owns the device, through cpal, and plays voices; this decides
    what they are. The policy is `PygameAudioSystem`'s -- buses, spatial
    attenuation and pan, a fixed number of voices with lower priorities
    stolen first -- so a game switching backend hears the same mix, plus:

    - **Pitch, continuously.** 2.0 is an octave up and half as long.
    - **Loop points.** An intro, then laps of a region, wrapped sample-exact
      in the mixer.
    - **Bus volumes reach sounds already playing.** pygame fixed a channel's
      loudness when it started; here moving a slider moves a loop that is
      going on.

    **Selected by `AudioConfig.backend`, not by `native_acceleration`.**
    Nothing in Python can stand in for it, so `PYGUARA_NO_NATIVE=1` must not
    change what a game is allowed to ask for: `PYGUARA_AUDIO_BACKEND=pygame`
    is what isolates a bug here. See ADR 0004, Decision 4.

    With no output device -- or an extension built without the
    `audio-output` feature -- the mixer runs against a silent clock and
    sounds still end on time; `output` says which.
    """

    def __init__(
        self,
        frequency: int = 44100,
        num_channels: int = 32,
        output: str = "device",
    ) -> None:
        """Open the mixer.

        Args:
            frequency: The rate to mix at when there is no device. A device
                runs at its own rate, which `rate` reports.
            num_channels: How many effects may sound at once; more steal
                from lower priorities, as on pygame.
            output: `"device"` (falling back to silent), `"silent"`, or
                `"offline"`, where nothing advances until `mixer.render`.

        Raises:
            RuntimeError: If the extension cannot be imported.
        """
        extension = native.require_extension("the native audio backend")
        self.mixer: Any = extension.NativeMixer(frequency, output)
        self._num_channels = num_channels
        self._bus_manager = AudioBusManager()
        self._master_volume = 1.0
        self._sfx_volume = 1.0
        self._music_volume = 1.0
        self._spatial_config = SpatialAudioConfig()
        self._listener_position = Vector2(0, 0)
        self._playing: dict[SoundHandle, _Playing] = {}
        self._shut_down = False
        description = str(self.mixer.output)
        if description.startswith("silent"):
            logger.warning("Native audio is %s; the game will be silent.", description)
        else:
            logger.info("Native audio: %s at %d Hz", description, self.mixer.rate)

    @property
    def rate(self) -> int:
        """The rate the mixer runs at."""
        return int(self.mixer.rate)

    @property
    def output(self) -> str:
        """Where the mix goes: `device: <name>`, `silent: <why>` or `offline`."""
        return str(self.mixer.output)

    @property
    def capabilities(self) -> AudioCapability:
        """Report pitch and loop points."""
        return AudioCapability.PITCH | AudioCapability.LOOP_POINTS

    # ========== Playing ==========

    def play_sfx(
        self,
        clip: AudioClip,
        volume: float = 1.0,
        loops: int = 0,
        priority: AudioPriority = AudioPriority.NORMAL,
        bus: AudioBusType = AudioBusType.SFX,
        pitch: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> SoundHandle | None:
        """Play a sound effect with priority and bus routing."""
        self._check(clip, pitch, loop_start, loop_end)
        return self._play(
            clip, volume, 1.0, 0.0, loops, priority, bus, None, pitch,
            loop_start, loop_end,
        )  # fmt: skip

    def play_sfx_at_position(
        self,
        clip: AudioClip,
        source_pos: Vector2,
        listener_pos: Vector2,
        volume: float = 1.0,
        loops: int = 0,
        priority: AudioPriority = AudioPriority.NORMAL,
        bus: AudioBusType = AudioBusType.SFX,
        pitch: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> SoundHandle | None:
        """Play a sound effect attenuated and panned by its position."""
        self._check(clip, pitch, loop_start, loop_end)
        distance = math.hypot(
            source_pos.x - listener_pos.x, source_pos.y - listener_pos.y
        )
        attenuation = self._spatial_config.calculate_attenuation(distance)
        if attenuation <= 0.001:
            return None
        pan = self._spatial_config.calculate_pan(source_pos, listener_pos)
        return self._play(
            clip, volume, attenuation, pan, loops, priority, bus, source_pos,
            pitch, loop_start, loop_end,
        )  # fmt: skip

    def _check(
        self,
        clip: AudioClip,
        pitch: float,
        loop_start: float | None,
        loop_end: float | None,
    ) -> None:
        """Refuse what no backend could honour, before anything else.

        Raises:
            ValueError: If `pitch` is outside `MIN_PITCH`-`MAX_PITCH`, or the
                loop range is negative or inverted -- for a one-shot too, so
                a bad range is reported rather than dropped.
            TypeError: If the clip came from another backend's loader.
        """
        if not MIN_PITCH <= pitch <= MAX_PITCH:
            raise ValueError(
                f"pitch must be between {MIN_PITCH} and {MAX_PITCH}, got {pitch}"
            )
        resolve_loop_points(clip, loop_start, loop_end)
        if not isinstance(clip, NativeAudioClip):
            raise TypeError(
                f"'{clip.path}' is a {type(clip).__name__}; the native backend "
                "plays a NativeAudioClip. Load it through a ResourceManager "
                "bootstrapped with AudioConfig.backend = NATIVE."
            )

    def _play(
        self,
        clip: AudioClip,
        volume: float,
        attenuation: float,
        pan: float,
        loops: int,
        priority: AudioPriority,
        bus: AudioBusType,
        position: Vector2 | None,
        pitch: float,
        loop_start: float | None,
        loop_end: float | None,
    ) -> SoundHandle | None:
        assert isinstance(clip, NativeAudioClip)
        start, end, _explicit = resolve_loop_points(clip, loop_start, loop_end)
        region: dict[str, float] = {}
        if start is not None and loops != 0:
            # Seconds name positions in the clip, and the voice steps through
            # the clip's own frames, so pitch does not enter into it.
            first = round(start * self.rate)
            last = (
                clip.frames if end is None else min(round(end * self.rate), clip.frames)
            )
            if last <= first:
                raise ValueError(
                    f"Loop region {start}-{end} s is empty in '{clip.path}', "
                    f"which is {clip.duration:.3f} s long."
                )
            region = {"loop_start": float(first), "loop_end": float(last)}

        if not self._make_room(priority):
            logger.debug("No voice free for '%s'", clip.path)
            return None
        base_volume = max(0.0, min(1.0, volume))
        meta = clip.import_meta
        import_gain = (
            meta.get_volume_multiplier() if isinstance(meta, AudioMeta) else 1.0
        )
        gain = base_volume * import_gain * clip.gain

        left, right = _stereo(self._bus_gain(bus) * gain * attenuation, pan)
        voice = int(
            self.mixer.play(
                clip.native_handle, left, right, pitch=pitch, loops=loops, **region
            )
        )
        handle = new_sound_handle()
        info = PlayingSoundInfo(
            handle=handle,
            channel_id=voice,
            clip_path=clip.path,
            priority=priority,
            bus=bus,
            base_volume=base_volume,
            position=position,
            is_spatial=position is not None,
        )
        self._playing[handle] = _Playing(info, voice, gain, attenuation, pan)
        return handle

    def _make_room(self, priority: AudioPriority) -> bool:
        """Free a voice if all are in use, stealing a lower priority's.

        Returns:
            Whether there is room to start one.
        """
        self._reap()
        if len(self._playing) < self._num_channels:
            return True
        lowest: _Playing | None = None
        for playing in self._playing.values():
            if playing.info.priority.value < priority.value and (
                lowest is None
                or playing.info.priority.value < lowest.info.priority.value
            ):
                lowest = playing
        if lowest is None:
            return False
        self.stop_sfx(lowest.info.handle)
        logger.debug("Stole a voice from a lower priority sound")
        return True

    def _reap(self) -> None:
        ended = [
            handle
            for handle, playing in self._playing.items()
            if not self.mixer.is_playing(playing.voice)
        ]
        for handle in ended:
            del self._playing[handle]

    def _bus_gain(self, bus: AudioBusType) -> float:
        name = self._bus_manager.get_bus_for_type(bus)
        return self._bus_manager.get_effective_volume(name)

    def _remix(self) -> None:
        """Apply the buses' current volumes to everything playing."""
        for playing in self._playing.values():
            self._apply(playing)
        self.mixer.set_music_gain(self._music_gain())

    def _apply(self, playing: _Playing) -> None:
        loudness = self._bus_gain(playing.info.bus) * playing.gain * playing.attenuation
        self.mixer.set_gains(playing.voice, *_stereo(loudness, playing.pan))

    # ========== Playing sounds ==========

    def is_sound_active(self, sound: SoundHandle) -> bool:
        """Return True only while the sound this handle refers to is playing."""
        playing = self._playing.get(sound)
        if playing is None:
            return False
        if self.mixer.is_playing(playing.voice):
            return True
        del self._playing[sound]
        return False

    def set_sound_mix(self, sound: SoundHandle, attenuation: float, pan: float) -> None:
        """Update a playing sound's attenuation and pan."""
        playing = self._playing.get(sound)
        if playing is None:
            return
        playing.attenuation = max(0.0, min(1.0, attenuation))
        playing.pan = pan
        self._apply(playing)

    def stop_sfx(self, sound: SoundHandle) -> None:
        """Stop one sound. A handle that has ended, or was never issued, is a no-op."""
        playing = self._playing.pop(sound, None)
        if playing is not None:
            self.mixer.stop(playing.voice)

    def pause_sfx(self) -> None:
        """Pause all sound effects."""
        self.mixer.pause()

    def resume_sfx(self) -> None:
        """Resume all paused sound effects."""
        self.mixer.resume()

    def update(self) -> None:
        """Forget sounds that have ended. Looping needs no help here."""
        self._reap()

    def cleanup_finished_channels(self) -> None:
        """Forget sounds that have ended."""
        self._reap()

    def get_active_sound_count(self) -> int:
        """How many sounds are playing."""
        self._reap()
        return len(self._playing)

    # ========== Music ==========

    def _music_gain(self) -> float:
        return self._bus_manager.get_effective_volume("music")

    def play_music(self, path: str, loop: bool = True, fade_ms: int = 1000) -> None:
        """Decode a track off the frame, then play it, fading in.

        A file that cannot be decoded plays nothing and is reported; the
        game carries on, as it did when `pygame.mixer.music` failed.
        """
        self.mixer.play_music(path, loop, max(0, fade_ms), self._music_gain())

    def stop_music(self, fade_ms: int = 1000) -> None:
        """Fade the music out, then stop it."""
        self.mixer.stop_music(max(0, fade_ms))

    def pause_music(self) -> None:
        """Pause the music."""
        self.mixer.pause(music=True)

    def resume_music(self) -> None:
        """Resume the music."""
        self.mixer.resume(music=True)

    def is_music_playing(self) -> bool:
        """Whether a track is playing, or being decoded to play."""
        return bool(self.mixer.music_playing)

    # ========== Volumes ==========

    def set_master_volume(self, volume: float) -> None:
        """Set the global master volume."""
        self._master_volume = max(0.0, min(1.0, volume))
        self._bus_manager.set_bus_volume("master", self._master_volume)
        self._remix()

    def set_sfx_volume(self, volume: float) -> None:
        """Set the sound effects volume."""
        self._sfx_volume = max(0.0, min(1.0, volume))
        self._bus_manager.set_bus_volume("sfx", self._sfx_volume)
        self._remix()

    def set_music_volume(self, volume: float) -> None:
        """Set the music volume."""
        self._music_volume = max(0.0, min(1.0, volume))
        self._bus_manager.set_bus_volume("music", self._music_volume)
        self._remix()

    def get_master_volume(self) -> float:
        """Get the master volume."""
        return self._master_volume

    def get_sfx_volume(self) -> float:
        """Get the sound effects volume."""
        return self._sfx_volume

    def get_music_volume(self) -> float:
        """Get the music volume."""
        return self._music_volume

    def set_bus_volume(self, bus: AudioBusType, volume: float) -> None:
        """Set a bus's volume; sounds already playing on it follow."""
        name = self._bus_manager.get_bus_for_type(bus)
        self._bus_manager.set_bus_volume(name, volume)
        self._remix()

    def get_bus_volume(self, bus: AudioBusType) -> float:
        """Get a bus's own volume."""
        found = self._bus_manager.get_bus(self._bus_manager.get_bus_for_type(bus))
        return found.volume if found else 1.0

    def set_bus_muted(self, bus: AudioBusType, muted: bool) -> None:
        """Mute or unmute a bus; sounds already playing on it follow."""
        name = self._bus_manager.get_bus_for_type(bus)
        self._bus_manager.set_bus_muted(name, muted)
        self._remix()

    def is_bus_muted(self, bus: AudioBusType) -> bool:
        """Whether a bus is muted."""
        found = self._bus_manager.get_bus(self._bus_manager.get_bus_for_type(bus))
        return found.muted if found else False

    def set_bus_effects(
        self, bus: AudioBusType, effects: Sequence[AudioEffect]
    ) -> None:
        """Decline a DSP chain; accept clearing one.

        The mixer owns the device now, so a bus effect has somewhere to go;
        none is written yet, and a chain this cannot apply is not stored,
        or `get_bus_effects` would report an effect nobody hears.
        """
        if effects:
            require_capability(self, AudioCapability.BUS_EFFECTS)

    def get_bus_effects(self, bus: AudioBusType) -> tuple[AudioEffect, ...]:
        """Return an empty chain."""
        return ()

    # ========== Listener ==========

    def set_listener_position(self, position: Vector2) -> None:
        """Set the listener position for spatial audio."""
        self._listener_position = position

    def get_listener_position(self) -> Vector2:
        """Get the listener position."""
        return self._listener_position

    def set_spatial_config(self, config: SpatialAudioConfig) -> None:
        """Set the spatial audio configuration."""
        self._spatial_config = config

    def get_spatial_config(self) -> SpatialAudioConfig:
        """Get the spatial audio configuration."""
        return self._spatial_config

    def shutdown(self) -> None:
        """Stop everything and release the device. Idempotent."""
        if self._shut_down:
            return
        self._shut_down = True
        self.mixer.close()
        self._playing.clear()
