# Game Design Document: *Mourisco: Ressonância*

**Version:** 1.0
**Engine:** PyGuara v0.5
**Genre:** 90s Stealth Action-Exploration (Side-scrolling / Metroidvania feel)
**Theme:** Perception as Mechanic — Sound Reveals the World

---

## 1. Executive Summary

### 1.1 Logline

A jaguarundi (*gato-mourisco*) explores pitch-black cavern networks,
using ultrasonic calls to carve a fading window of visibility out of
total darkness — every jump, every threat, every ledge exists only for
as long as the last pulse's echo does.

### 1.2 The "Meta" Pitch

*Mourisco: Ressonância* demonstrates that the renderer, the audio
system, and the physics query layer are one pipeline, not three.

* **The Echolocation Pulse** represents the **Render Graph**:
  `WorldPass → LightPass (custom expansion uniform) → PostProcessPass
  (Bloom)` — a single clean pipeline that lights only what the pulse has
  reached so far.
* **The Radial Raycast** represents **Physics Queries as a Gameplay
  Primitive**: line-of-sight occlusion isn't debug tooling here, it *is*
  the mechanic — what the raycast doesn't hit, the player doesn't see.
* **The Decay Curve** represents **Tweening as Core Loop, not Polish**:
  the easing function driving the pulse's fade *is* the difficulty
  curve — a faster decay is a harder game.

---

## 2. Gameplay Mechanics

### 2.1 Core Loop: "Master the Mix"

The screen is near-total darkness with high-contrast silhouettes. The
player has two vocalisations, a fast/precise one and a slow/wide one,
and must choose per situation:

* **Short chirp:** fast, low-energy ping. Reveals immediate footing and
  nearby platforms only. Safe — does not agitate ceiling bats.
* **Resonant scream:** wide-radius pulse with strong bloom. Reveals
  distant cave layout and spider nests, but agitates bats into a
  disruptive swarm if used near a roost — the wider the reveal, the
  louder the cost.

### 2.2 Platforming & Navigation

* Precise platforming timed to the pulse's decay window — a ledge seen
  on the chirp's crest may be dark again before the jump lands, so
  timing the *next* pulse is as important as the jump itself.
* Giant arachnids ambush from silhouette; a scream reveals their nest
  early enough to route around it, a chirp does not.
* Bats roost on cave ceilings and scatter into disorienting flight paths
  when a scream passes near them, temporarily degrading the player's
  own audio readability (their squeaks mask the ambient cues the player
  relies on between pulses).

### 2.3 Risk/Reward Loop

Screaming is strictly more informative and strictly more dangerous —
the game never forces one choice, it makes the player own the
trade-off pulse by pulse.

---

## 3. Visual & Audio Aesthetic

### 3.1 Art Style: "Neon Echo in the Dark"

Following the cover key art: near-black cavern silhouettes lit only by
cyan/violet wavefront rings expanding from the jaguarundi.

* **Base state:** near-total darkness, high-contrast character and
  terrain silhouettes, no ambient fill light.
* **Revealed state:** normal-mapped cave walls, stalactites, and
  creatures glow neon-cyan to violet along the pulse's leading edge,
  decaying to black behind it.
* **Threat readability:** spiders and bats render in a warmer,
  desaturated tone against the cyan/violet reveal so they read as
  "wrong" the instant the pulse touches them.

### 3.2 Audio Direction

* **Spatial audio:** distant bat squeaks and water drops pan and
  fall off with 3D position, so the player can orient by ear between
  pulses, not just by sight.
* **Occlusion:** low-pass filtering and volume ducking apply when a
  wall sits between the player and a sound source, so the mix itself
  tells the player what's around a corner before a pulse confirms it.
* **SFX:** a distinct short chirp vs. resonant scream vocalisation,
  bat-swarm agitation stinger, and a spider-skitter cue that gets
  louder as a raycast confirms closing distance.

---

## 4. Technical Implementation Specifications

### 4.1 Audio & Spatial Audio Manager (`pyguara.audio`, `pyguara.audio.audio_source_system`)

* Positional falloff and stereo panning for ambient cave sources (bat
  squeaks, water drops) driven by listener/source distance and angle.
* Dynamic low-pass filtering and volume ducking scale with acoustic
  distance *and* wall occlusion, so a source behind a wall reads
  differently than the same source in open air at the same distance.

### 4.2 ModernGL Lighting & Custom Shaders (`pyguara.graphics.backends.moderngl.shaders`, `pyguara.graphics.lighting`)

* The echolocation wavefront is a custom expansion uniform driving
  `light.frag`/`light.vert`, sampling normal maps and a wireframe
  geometry mask so revealed geometry pops before decaying back to
  black.
* Runs through the existing Render Graph pass pipeline:
  `WorldPass → LightPass (expansion uniform) → PostProcessPass`, with
  `bloom_threshold.frag` / `bloom_composite.frag` boosting the wave
  ring's visibility against the dark background.

### 4.3 Raycast Physics Queries (`pyguara.physics.protocols`, `pyguara.physics.character_mover`)

* Each pulse emits a radial fan of line-of-sight raycasts, tested
  against static solids (cave geometry) and moving fauna colliders, to
  determine acoustic occlusion.
* The raycast results directly drive which geometry and creatures the
  LightPass is permitted to reveal — the physics query *is* the fog of
  war, not a separate visibility system layered on top of it.

### 4.4 Tweening & VFX Stack (`pyguara.animation.tween`, `pyguara.graphics.vfx.effects.bloom`)

* Easing functions modulate the resonance decay curve, screen flash on
  scream, and camera shake during intense roars — the decay curve is
  authored as a tween, not a hardcoded fade, so difficulty tuning is a
  curve edit.
* Bloom threshold is pushed up specifically for the wave-ring pass so
  it reads clearly against near-black backgrounds without blowing out
  the rest of the frame.

---

## 5. Level Design: "The Deep Throat"

**Level Name:** `mourisco_caverns.py`

1. **Cave Throat (Tutorial):** short-chirp only, tight linear space,
   teaches reading footing from a narrow reveal.
2. **The Web Nest:** introduces spiders; a resonant scream is needed to
   see the full nest layout, but wakes a nearby bat roost — first real
   risk/reward decision point.
3. **The Deep Resonance:** combines both pulses in a platforming gauntlet
   with moving hazards timed to audio cues, requiring the player to
   alternate chirp/scream deliberately rather than defaulting to one.

---

## 6. Asset Requirements Checklist

**Sprites / Models:**

* [ ] `spr_mourisco_idle`, `spr_mourisco_run`, `spr_mourisco_call`
      (chirp vs. scream call-out poses).
* [ ] `spr_spider_idle`, `spr_spider_lunge`.
* [ ] `spr_bat_roost`, `spr_bat_scatter`.
* [ ] `tex_cave_normalmap`: normal maps for the wall/stalactite geometry
      the echolocation shader samples.

**Audio:**

* [ ] `sfx_chirp_short.wav`, `sfx_scream_resonant.wav`.
* [ ] `sfx_bat_agitated_swarm.wav`.
* [ ] `sfx_spider_skitter.wav` (distance-scaled).
* [ ] `ambient_cave_drips_loop.ogg`.
