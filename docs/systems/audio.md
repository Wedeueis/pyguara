# Audio System

`pyguara.audio` plays music and sound effects, with optional **spatial**
(position-aware) playback and a **bus** hierarchy for grouped volume control.
Game code never touches pygame's mixer directly.

## Layers

1. **`IAudioSystem`** (`pyguara.audio.audio_system`) — the backend contract:
   music streaming, one-shot and looping SFX, spatial placement, buses,
   per-channel mix updates. `PygameAudioSystem` is the shipped
   implementation; it is registered as a singleton by the application
   bootstrap.
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
channel = audio.play_sfx("sfx/jump.wav", volume=0.8)
```

## Music

`play_music(path, loop=True, fade_ms=1000)` streams one track at a time from
disk (pygame's `mixer.music`). `stop_music`, `pause_music`, `resume_music`
and `is_music_playing` control it; `get_current_music()` returns the path
`AudioManager` last started, or `None`.

Music volume follows the `music` bus and the `master` bus: changing either
re-applies immediately to the playing stream.

## Sound effects and channels

`play_sfx(clip, volume, loops, priority, bus)` plays a clip on a mixer
**channel** and returns that channel's id, or `None` if the clip is invalid
or every channel is busy with an equal-or-higher priority sound.

- **`loops`**: `0` plays once, `-1` loops forever, `n` repeats `n` extra
  times.
- **The returned id can be `0`.** Channel 0 is a real channel — test the
  result against `None`, never for truthiness.
- **`priority`** (`AudioPriority.LOW`…`CRITICAL`): when no channel is free, a
  new sound steals the channel of the lowest-priority sound *below* its own
  priority. Same-or-higher priority sounds are never interrupted.

Loudness and stereo pan are applied to the **channel**, never to the `Sound`
object — the `ResourceManager` hands every concurrent play of one clip the
*same* `Sound`, so setting its volume would bleed across all of them.

### One-shot lifecycle

A one-shot sound finishes on its own with no callback. `IAudioSystem`
exposes `is_channel_active(channel)`, which is `True` only while the exact
sound this system started on that channel is still playing — it returns
`False` once the sound has ended *or* the channel has been recycled by an
unrelated sound. `AudioSourceSystem` calls it every frame to reconcile
`AudioSource` state; you rarely call it directly.

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

For headless use (tests, CI) set `SDL_AUDIODRIVER=dummy` before the mixer
initialises — playback then advances in real time but produces no sound.
