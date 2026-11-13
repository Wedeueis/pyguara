# Audio System

`pyguara.audio` plays music and sound effects, with optional **spatial**
(position-aware) playback and a **bus** hierarchy for grouped volume control.
Game code never touches pygame's mixer directly.

## Layers

1. **`IAudioSystem`** (`pyguara.audio.audio_system`) — the backend contract:
   music streaming, one-shot and looping SFX, spatial placement, buses,
   per-sound mix updates, and the optional capabilities below.
   `PygameAudioSystem` is the shipped implementation; it is registered as a
   singleton by the application bootstrap.
2. **`AudioManager`** (`pyguara.audio.manager`) — a convenience wrapper over
   `IAudioSystem` that loads clips by path through the `ResourceManager`,
   tracks the current music track, and forwards volume calls. Also a
   bootstrap singleton.
3. **`AudioSourceSystem`** (`pyguara.audio.audio_source_system`) — the ECS
   system that drives `AudioSource` / `AudioEmitter` / `AudioListener`
   components. A scene registers it automatically (priority 250).

```python
from pyguara.audio import AudioManager

audio = container.get(AudioManager)
audio.play_music("music/theme.ogg", loop=True)
sound = audio.play_sfx("sfx/jump.wav", volume=0.8)
```

## Choosing a backend

`AudioConfig.backend` is `native`, the default, or `pygame`; the environment
variable is `PYGUARA_AUDIO_BACKEND`. There is deliberately no `auto`, because it
would give the same game different capabilities on different machines, and
`native` fails at startup if the extension cannot be imported -- which is what
a checkout with no Rust toolchain, or nothing built yet, will see, and why
`pygame` is kept.

**It is not governed by `native_acceleration` or `PYGUARA_NO_NATIVE`.** Those
switch between two implementations of the same thing, and nothing in Python can
stand in for this one. So `PYGUARA_NO_NATIVE=1` does not mean "no native code
runs" any more: to rule out the audio, set `PYGUARA_AUDIO_BACKEND=pygame`. See
ADR 0004, Decision 4.

`NativeAudioSystem` decodes with `symphonia` and mixes in Rust
(`rust/src/mixer.rs`), writing to the sound card through `cpal` -- no
`pygame.mixer`, and no pygame at all. The policy is the default backend's, so a
game hears the same mix: buses, spatial attenuation and pan, 32 voices with
lower priorities stolen first. On top of it:

- **Pitch is continuous, and changes duration.** A voice steps through its
  clip by its pitch, so 2.0 is an octave up and half as long, and 1.003 is
  1.003 -- nothing is rendered or cached per pitch. The range is 0.25 to 4.0,
  and outside it raises `ValueError`.
- **Interpolation is linear**, so a large upward pitch aliases. Inaudible at a
  few percent, and not meant for wide pitch sweeps.
- **Loop points wrap in the mixer**, sample-exact, in the same loop that plays
  the voice: an intro, then `loops` laps of the region (-1 forever). No
  `update()` is needed for them and a frame stall cannot reach them.
- **Bus volumes reach sounds already playing.** pygame fixed a channel's
  loudness when it started; here moving the SFX slider moves a loop under way.
- **Music decodes off the frame**, on a worker thread, and starts when ready,
  fading in; `is_music_playing()` is true while it decodes.
- **It also reads `.flac`**, which the default backend's loader does not.
- **A clip must come through `NativeSoundLoader`**, which bootstrap registers
  for this backend, given the system's mixer: clips are converted to the rate
  the mixer runs at, which on a device is the device's own. A clip from
  another loader raises `TypeError`.
- **With no output device it runs silent, on a clock.** Sounds still end when
  they would have, as pygame's `dummy` driver did, and the boot log says so.
  `NativeAudioSystem.output` reads `device: <name>`, `silent: <why>` or
  `offline`.

`output="offline"` is a mixer that advances only when `mixer.render(frames)`
is called. The tests and `tools/audio_capture.py` (`capture_native`) use it to
measure what would have reached the speaker.

| Measured, 44.1 kHz stereo | |
| --- | ---: |
| Start a pitched voice, and stop it | **4 us** |
| Mix one 60 Hz frame (735 samples) of 32 voices | 0.12 ms, on the audio thread |
| Load and convert one second of audio | 1.3 ms |
| A clip in memory | 353 KB per second (stereo float), once |

The device is `cpal` on Windows and macOS. **On Linux it is ALSA, loaded
with `dlopen` when a mixer opens the device** rather than linked: a linked
`libasound.so.2` made the whole extension fail to import on a machine
without it (a slim container, a server), taking every native store with
it. Now a missing ALSA is one more reason the mixer is silent, and says
so. It plays 16-bit stereo at 48 kHz to ALSA's `default` device, which on a
desktop is PipeWire's or PulseAudio's plugin; `PYGUARA_ALSA_DEVICE` names
another (`null` takes samples with no card, which is how
`tests/test_native_alsa.py` runs the path). A build without the
`audio-output` cargo feature has no device and always runs silent.

`symphonia` is **MPL-2.0**: file-level copyleft, fine to link unmodified from an
MIT engine, but the wheel distributes it.

## Optional capabilities

Three features cannot be expressed by every mixer: per-play **pitch**, **loop
points** inside a clip, and **DSP on a bus**. `PygameAudioSystem`, the default,
expresses none of them; `NativeAudioSystem` expresses the first two. Each is
declared through `AudioCapability` and
declined by **raising** `UnsupportedAudioCapability`, so a request a backend
cannot honour fails where it was made.

```python
from pyguara.audio import AudioCapability

if AudioCapability.PITCH in audio.capabilities:
    audio.play_sfx("sfx/hit.wav", pitch=random.uniform(0.9, 1.1))
else:
    audio.play_sfx("sfx/hit.wav")
```

Every capability has a request that means *not asked for* — `pitch=1.0`,
`loop_start=None`, an empty effect list — so code that uses none of them runs
on any backend. A no-op that accepted `pitch=1.2` and played at the original
speed would report success for a sound that is wrong, with nothing for the
caller to check; this is the same reasoning that made `ShapeType.SEGMENT`
raise instead of returning `None`.

| Capability | What it adds | `PygameAudioSystem` | `NativeAudioSystem` |
| --- | --- | --- | --- |
| `PITCH` | `pitch=` on either `play_sfx` | no — the mixer resamples at load and plays at its own rate | yes |
| `LOOP_POINTS` | `loop_start=` / `loop_end=` | no — `Channel.play` takes a loop *count* and nothing else | yes |
| `BUS_EFFECTS` | `set_bus_effects(bus, [...])` | no — a channel's only processing is a left/right gain pair | no — needs the device, see below |

**Loop points from a `.meta` sidecar warn instead of raising.** `AudioMeta`
carries `loop_start` / `loop_end`, and those are the asset describing itself
rather than a call site asking for something. An incapable backend logs once
per clip and loops the whole file: refusing would let one line of metadata
silence a sound that worked before anybody wrote it. An explicit argument
still raises. A malformed range (negative, or inverted) raises `ValueError`
on every backend, before the capability is consulted — the same bad input
should read the same way everywhere.

Bus effects are a settled seam, not a shipped feature: `LowPassFilter`,
`HighPassFilter` and `Reverb` are descriptions a backend interprets, applied
in list order. Nothing implements them yet, which is why asking for one
raises and `get_bus_effects` reports `()` rather than the chain you handed
it — holding a chain that will never be applied would describe an effect
nobody can hear.

## Music

`play_music(path, loop=True, fade_ms=1000)` streams one track at a time from
disk (pygame's `mixer.music`). `stop_music`, `pause_music`, `resume_music`
and `is_music_playing` control it; `get_current_music()` returns the path
`AudioManager` last started, or `None`.

Music volume follows the `music` bus and the `master` bus: changing either
re-applies immediately to the playing stream.

## Sound effects and handles

`play_sfx(clip, volume, loops, priority, bus, pitch, loop_start, loop_end)`
plays a clip and returns a **`SoundHandle`**, or `None` if the clip is invalid
or every channel is busy with an equal-or-higher priority sound.

- **A handle is opaque.** Its `token` is minted per play, never reused in a
  process, and means nothing to a caller. `stop_sfx`, `is_sound_active` and
  `set_sound_mix` all take one; a handle whose sound has ended resolves to
  nothing, so they become no-ops rather than acting on a stranger.
- **That is the point.** A mixer channel number is recycled the instant its
  sound ends, so `stop_sfx(7)` on a channel int held for a few frames stopped
  whatever had taken channel 7 over. Channel `0` was also falsy, so
  `if channel_id:` dropped a real sound.
- **`loops`**: `0` plays once, `-1` loops forever, `n` repeats `n` extra
  times.
- **`priority`** (`AudioPriority.LOW`…`CRITICAL`): when no channel is free, a
  new sound steals the channel of the lowest-priority sound *below* its own
  priority. Same-or-higher priority sounds are never interrupted.

Loudness and stereo pan are applied to the **channel**, never to the `Sound`
object — the `ResourceManager` hands every concurrent play of one clip the
*same* `Sound`, so setting its volume would bleed across all of them.

### Limiting one sound

Ten hits landing in one frame start ten copies of the same clip at once,
which sounds like one hit, much louder. `AudioManager.set_sfx_limit` caps it:

```python
audio = container.get(AudioManager)
audio.set_sfx_limit("sfx/hit.wav", max_voices=4, min_interval=0.03)
```

- **`max_voices`** is the most copies playing together. A copy stops counting
  once `is_sound_active` says it has ended.
- **`min_interval`** is the seconds between two starts, in real time.
- **A play over the limit is dropped**, and `play_sfx` returns `None`. It isn't
  queued, which would be heard late, and it doesn't cut off a copy already
  playing.
- The limit is per clip path. `play_sfx_clip` reads it from the clip.
- Calling it with both arguments at their defaults removes the limit.
  `get_sfx_limit` returns what is set.

### One-shot lifecycle

A one-shot sound finishes on its own with no callback. `IAudioSystem`
exposes `is_sound_active(handle)`, which is `True` only while that exact
sound is still playing — it returns `False` once the sound has ended *or* its
channel has been recycled by an unrelated sound. `AudioSourceSystem` calls it
every frame to reconcile `AudioSource` state; you rarely call it directly.

## Placeholder sounds

Before any real sounds exist, `pyguara.audio.placeholder` builds short stand-ins
(a thud, a blip, a hiss) from simple tones and noise, and writes them as `.wav`
files the game loads like any other. When a real recording arrives it replaces
the file, with no code change.

From code, the functions combine like this:

```python
from pyguara.audio.placeholder import envelope, mix, rng_for, sine, transient, write_wav

rng = rng_for("hit")
hit = envelope(mix(transient(0.03, 0.5, rng), sine(140.0, 0.12, 0.6)), decay_rate=20.0)
write_wav(Path("assets/audio/hit.wav"), hit)
```

From data, the same tree as JSON. Each node is an object with one key, naming a
function, holding that function's arguments; `envelope` and `concat` take what
they wrap as `of`, and `mix` takes a list:

```json
{"hit": {"envelope": {"decay_rate": 20.0, "of": {"mix": [
    {"transient": {"duration": 0.03, "amplitude": 0.5}},
    {"sine": {"freq": 140.0, "duration": 0.12, "amplitude": 0.6}}]}}}}
```

```bash
pyguara sounds data/sounds.json assets/audio/
```

| Node | Arguments |
| --- | --- |
| `sine`, `square` | `freq`, `duration`, `amplitude` (1.0) |
| `sweep` | `freq_start`, `freq_end`, `duration`, `amplitude` (1.0) |
| `noise`, `transient` | `duration`, `amplitude` |
| `envelope` | `of`, `attack` (0.005 s), `decay_rate` (8.0) |
| `concat` | `of` (a list), `gap` (0.01 s) |
| `mix` | a list |

- **Every recipe is checked before anything is written.** A mistake names
  its place in the tree and the closest valid name, for example
  `hit > envelope > of > mix[1] > sine: unknown argument 'frq'; did you mean 'freq'?`
- **The output is deterministic.** Noise is seeded by the sound's own name, so
  editing one sound leaves every other file byte-identical, and a rebuild with
  no edits changes nothing. `--seed` rerolls all of them.
- Files are mono, 16-bit, 22,050 Hz. Anything past full scale is clipped.

Quintal do Cerrado's `assets/audio/generate_placeholder_sfx.py` is a worked
example in code.

## Spatial audio

Attach components to entities that also carry a `Transform`:

| Component | Purpose |
| --- | --- |
| `AudioListener` | Marks the "ears" (usually the camera/player). One active listener per scene; its position drives every spatial calculation. |
| `AudioSource` | A persistent or looping sound that follows its entity. `spatial=True` (default) attenuates and pans it by distance to the listener, updated every frame while it plays. |
| `AudioEmitter` | A fire-and-forget one-shot at the entity's position. `remove_after_play=True` (default) drops the component once it has played. |

```python
entity.add_component(Transform(position=Vector2(400, 300)))
entity.add_component(AudioSource(clip_path="sfx/engine_loop.wav", loop=True))
entity.get_component(AudioSource).play()   # or auto_play=True / play_on_awake=True
```

`auto_play` fires **once**, when the source is first processed; a one-shot
that ends is not restarted (use `loop=True` for that, or call `play()`
again). `AudioSource.is_playing` reflects reality — it goes back to `False`
when a non-looping sound ends.

### `SpatialAudioConfig`

Controls the distance model (`AudioSourceSystem.set_spatial_config`, or
`PygameAudioSystem.set_spatial_config`):

| Field | Meaning |
| --- | --- |
| `reference_distance` | Distance (world units) within which volume is 100%. Must be `> 0`. |
| `max_distance` | Distance at which the sound is silent. Must be `> reference_distance`. |
| `rolloff_factor` | How fast volume falls between the two (`1.0` ≈ realistic inverse-distance; `< 1` slower). Must be `>= 0`. |
| `pan_strength` | Stereo spread from horizontal offset (`0.0` mono … `1.0` full). Must be `>= 0`. |

Out-of-range values raise `ValueError` at construction — an inverted or zero
range is a divide-by-zero in the pan maths and a hard volume cliff in the
attenuation maths, not a soft degradation.

## Buses and volume

Four buses in a fixed hierarchy: `master` → `sfx` / `music` / `voice`
(`AudioBusType`). Effective volume walks the chain
(`bus.volume × … × master.volume`); a muted bus contributes `0`.

```python
audio_system.set_bus_volume(AudioBusType.SFX, 0.5)
audio_system.set_bus_muted(AudioBusType.MASTER, True)
```

Buses are volume-only on the shipped backend. `set_bus_effects` is the seam
for DSP; see **Optional capabilities**.

`set_master_volume` / `set_sfx_volume` / `set_music_volume` are shorthands
for the `master` / `sfx` / `music` buses.

!!! note "Known limitation"
    A bus or master volume change re-applies to the music stream and to
    spatial SFX (which are re-mixed every frame), but **not** to
    already-playing *non-spatial* SFX — those keep the volume they were
    started with until they end. Set bus volumes before triggering sounds,
    or drive important sustained sounds through an `AudioSource`.

## Backend notes

**A machine with no audio output still runs.** If the mixer can't open, because the device is
missing or disabled, both backends log a warning and fall back to SDL's dummy driver. Everything
keeps working and nothing is heard, so a game doesn't need to handle this itself.

`PygameAudioSystem` wraps `pygame.mixer` (pygame-ce). It allocates 32
channels by default. `shutdown()` stops all audio and releases the device;
it is idempotent and is called from `Application.shutdown()`.

It reports `AudioCapability.NONE`, and the three things it cannot do are the
reason a second backend is wanted rather than a longer feature list on this
one — see [#72](https://github.com/Wedeueis/pyguara/issues/72), whose P1
"sound variation" needs `PITCH`.

For headless use (tests, CI) set `SDL_AUDIODRIVER=dummy` before the mixer
initialises — playback then advances in real time but produces no sound.
