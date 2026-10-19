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

## Optional capabilities

Three features cannot be expressed by every mixer, and the one backend that
ships expresses **none** of them: per-play **pitch**, **loop points** inside
a clip, and **DSP on a bus**. Each is declared through `AudioCapability` and
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

| Capability | What it adds | `PygameAudioSystem` |
| --- | --- | --- |
| `PITCH` | `pitch=` on either `play_sfx` | no — the mixer resamples at load and plays at its own rate |
| `LOOP_POINTS` | `loop_start=` / `loop_end=` | no — `Channel.play` takes a loop *count* and nothing else |
| `BUS_EFFECTS` | `set_bus_effects(bus, [...])` | no — a channel's only processing is a left/right gain pair |

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

### One-shot lifecycle

A one-shot sound finishes on its own with no callback. `IAudioSystem`
exposes `is_sound_active(handle)`, which is `True` only while that exact
sound is still playing — it returns `False` once the sound has ended *or* its
channel has been recycled by an unrelated sound. `AudioSourceSystem` calls it
every frame to reconcile `AudioSource` state; you rarely call it directly.

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

`PygameAudioSystem` wraps `pygame.mixer` (pygame-ce). It allocates 32
channels by default. `shutdown()` stops all audio and releases the device;
it is idempotent and is called from `Application.shutdown()`.

It reports `AudioCapability.NONE`, and the three things it cannot do are the
reason a second backend is wanted rather than a longer feature list on this
one — see [#72](https://github.com/Wedeueis/pyguara/issues/72), whose P1
"sound variation" needs `PITCH`.

For headless use (tests, CI) set `SDL_AUDIODRIVER=dummy` before the mixer
initialises — playback then advances in real time but produces no sound.
