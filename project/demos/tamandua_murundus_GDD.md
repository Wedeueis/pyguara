# Game Design Document: *Tamanduá: O Guardião dos Murundus*

**Version:** 0.1 — scope contract, written before the build
**Engine:** PyGuara (pre-alpha)
**Genre:** Horde Survivor / Density Showcase
**Theme:** A cerrado clearing between dusk and dawn

> **Status: future tense.** This document is a *contract for what will be
> built*, written at D0 so that scope is argued once rather than drifting
> through six PRs. It is rewritten as-built at D6, at which point every
> number below is either confirmed or corrected against a measurement.
>
> Two rules were applied to every feature in the original design fiction:
> **which engine capability does this prove?** — and if the answer is "none,
> it is content", it was cut. §8 lists every cut with its reason.

---

## 1. Executive Summary

### 1.1 Logline

A giant anteater holds one clearing from dusk to dawn while the cerrado's
insect life rises against it. The termite mounds — *murundus* — are what feed
the swarm. Break one and the tide thins. Survive to first light.

### 1.2 The "Meta" Pitch

This demo exists to prove four pieces of engine work, each of which shipped
before it. **This section is load-bearing**: if a feature below cannot be
traced to one of these four, it does not belong in the demo.

| Engine capability | Where it lives | What the demo does with it |
| --- | --- | --- |
| **Per-instance sprite tint on the GL backend** | `pyguara/graphics/backends/moderngl/instancing.py`, `shaders/sprite.*` | One neutral insect texture, N colours, **one draw call**. Dull brown at dusk; bioluminescent at midnight. Same texture, same batch, tint driven by the time-of-day curve. |
| **Ambient day/night cycle** | `pyguara/graphics/lighting/cycle.py` | `AmbientCycle` + keyframes drives the run's three phases and resolves at dawn. The clearing is lit by the cycle, not by hand-mutated ambient. |
| **Light type, cone and flicker** | `pyguara/graphics/lighting/` | The anteater carries a `SPOT` light — the cone it can actually see by. Murundus glow with `flicker_enabled`. |
| **The progression kit** | `pyguara/kits/progression/` | Killed insects drop XP motes; `Magnet` pulls them in; enough motes freezes the run and offers 1-of-3 cards. |

Two engine results are *also* on display, though they predate this plan:
the flocking optimisation (`pyguara/ai/flocking_system.py`) and the
`SpatialHash` the magnet and the tongue both query.

**The climax is a density climax, not a boss.** See §8.

---

## 2. Gameplay Mechanics

### 2.1 Core loop

Roughly **four minutes**, one clearing, three lighting phases resolving at
dawn. There is no level select, no meta-progression and no run variety: the
demo is a single scripted arc, because its job is to show a curve, not to be
replayed.

1. **Dusk (0:00–1:20)** — a handful of insects. The player learns the tongue
   and finds the murundus.
2. **Night (1:20–3:00)** — the swarm builds. Bioluminescence comes up with the
   ambient curve. Motes accumulate; the first cards are offered.
3. **Deep night (3:00–3:40)** — peak density. This is the measurement made
   visible.
4. **Dawn (3:40–4:00)** — the ambient curve resolves, the swarm thins, the run
   ends. Not a victory screen: a sunrise.

### 2.2 The anteater

| Input | Action |
| --- | --- |
| `WASD` / arrows | Move |
| *(automatic)* | **The tongue** auto-lashes the nearest insect in an arc in front of the anteater, on a cooldown |
| `Tab` / arrows, `Enter` | Navigate and pick an upgrade card, while the run is frozen |

**The tongue is automatic.** The player steers; the tongue picks its own
target. This is a genre convention and it is also the honest choice here —
aiming would make the demo about input handling, which is not on the list in
§1.2.

Mechanically the tongue is `Hitbox` + `ActiveFrameWindow` from
`kits/action_combat`, with target selection through the shared `SpatialHash`.
No new engine surface.

### 2.3 The swarm

**The hybrid split is stated here deliberately, so nobody mistakes the picture
for the measurement.** `swarm.py` carries two layers:

| Layer | Count | Flocks | Hittable | Costs |
| --- | ---: | --- | --- | --- |
| **Interactive** | up to `SWARM_CAP` | yes, via `FlockingSystem` | yes | flocking + batching |
| **Decorative** | a multiple of it | no — cheap drift | no | batching only |

Both layers draw in **the same batch, through the same tint channel**. The
decorative layer exists so the screen looks like the cerrado at midnight; the
interactive layer is what the engine is actually being measured on.

`SWARM_CAP` is set from `docs/guides/performance.md`, not from ambition. As
measured on **WSL2 · Mesa 23.2.1 over D3D12 · RTX 3050 · CPython 3.12 ·
2026-09-12**, against a 16.7 ms frame:

| Agents | `groups=1` | `groups=3` |
| ---: | ---: | ---: |
| 1000 | 16.0 ms | 7.4 ms |
| 2000 | 34.3 ms | 15.6 ms |

**So: ~1000 fully-simulated boids at 60 Hz, or ~2000 with steering staggered
to 20 Hz.** The demo will run the interactive layer with `groups=3` and set
`SWARM_CAP` below the arithmetic ceiling, because flocking is not the only
system in the frame — the batcher, the tongue, the motes and the post-process
stack all bill against the same 16.7 ms. **D2 re-measures in the real scene
and D6 records what was actually affordable.** The number in this row is a
prediction until then.

Clumped density costs materially more than uniform — 161.9 ms against 53.5 at
3000 agents — and a horde converging on a player is exactly the clumped case.
The murundus are the mitigation as well as the mechanic: they keep the swarm
distributed around anchors instead of collapsing onto the player.

### 2.4 Murundus

Termite mounds. Each is a spawn anchor that feeds the swarm from its own
position, and each can be broken.

- Breaking one **stops it feeding** and thins the tide from that quarter.
- Each carries a flickering `LightSource` — a genuine use of E6's
  `flicker_enabled`, not decoration bolted on.
- They are the reason the swarm is spatially distributed rather than a single
  ball converging on the player, which is a performance decision as much as a
  design one (§2.3).

### 2.5 Motes and cards

Killed insects drop XP motes (`Attracted`). The anteater carries a `Magnet`.
Collected motes feed `grant_experience()`; a level freezes the run and offers
**1-of-3** cards from a flat table of **6–8 upgrades**.

Cards are picked with the keyboard, which is the first real consumer of the UI
focus ring (`UIManager.focus_next()`).

The upgrade table is flat — no synergy graph, no evolution paths. §8.

---

## 3. Visual & Audio Aesthetic

### 3.1 Art style

**No sprite art ships with this demo.** Every texture is generated at runtime
through `TextureFactory.create_from_bytes`, as every other demo in this
repository does. That keeps the repo asset-free, and it makes the tint work
maximally visible: **one neutral blob, N colours, one draw call.** A reader
who wants to know whether per-instance tint works can look at one screenshot.

The palette is cerrado at night: burnt ochre earth, dark scrub, and the
insects shifting from dull brown to cyan-green bioluminescence as the ambient
curve falls.

### 3.2 Lighting and glow

The render graph is
`WorldPass → LightPass(f2) → CompositePass → PostProcessPass(Bloom, Vignette) → FinalPass`.

**Bloom is this demo's showcase**, because bioluminescence is precisely a
threshold-crossing colour. **There is no heat haze** — that is *Protocolo
Bandeira*'s showcase, and two demos claiming the same effect teaches nothing.

**Insects are not lights.** If each insect were a `LightSource`, both
`LightingSystem`'s per-entity Python collection and the light instance buffer
would scale with N, and the crowd benchmark would quietly become a lighting
benchmark. Bioluminescence is an **additive tinted sprite that crosses the
bloom threshold**, plus roughly six aggregate lights at flock centroids — the
pooled pattern `arena_fx.LIGHT_POOL_SIZE = 56` already uses.

**The demo must not own a custom `BaseRenderPass`.**
`mourisco_ressonancia/pulse_pass.py` is the only precedent, and it has to
reach up into the *engine's* shader directory because nothing resolves
game-local shader paths. If the glow needs a custom additive pass, that is an
engine gap to raise — not a thing to copy.

### 3.3 Audio

**None.** No demo in this repository ships audio assets, and adding the first
one here would prove nothing on the §1.2 list.

---

## 4. Technical Implementation Specifications

### 4.1 Module layout

`games/tamandua_murundus/`, modelled on `protocolo_bandeira`'s split.
**~3,600–4,000 lines is the ceiling to hold.**

| File | Responsibility |
| --- | --- |
| `bootstrap.py` | DI + the render graph above |
| `swarm.py` | The centrepiece: pool, flocking tick, tint curve, `SWARM_CAP`, and a **pure `build_batch()`** |
| `cerrado_fx.py` | The `arena_fx.py` analogue: backdrop, light pool, day/night hookup, `Sparks`/`Shaker`/`FloatingText`/`ScreenFlash`, hit-stop, `run_pipeline()` |
| `render.py` | Every draw call + palette, with the per-shape-type flush discipline |
| `phases.py` | Run clock, phase table, time-keyed spawn budget |
| `upgrades.py` / `upgrade_ui.py` | Upgrade table + apply functions; card layout |
| `scenes.py`, `systems.py`, `components.py`, `events.py`, `pooling.py`, `main.py` | As per Bandeira |

### 4.2 `build_batch()` must be pure

**Decided before `swarm.py` is written, not retrofitted.**

GL demos are excluded from `DEMOS_THAT_DRAW` — SDL's dummy video driver has no
OpenGL — so the tint showcase would otherwise ship covered only by a manual
smoke test. But `tests/visual/` rasterises nothing: it snapshots the ordered
stream of backend calls against a recording `IRenderer`.

A **pure** `build_batch(...) -> RenderBatch` makes the swarm's batch —
including `colors_enabled=True` and the actual tint values — deterministically
snapshot-testable without a GPU. This is a design constraint on the module,
decided up front or not at all.

### 4.3 Run clock and spawn budget

`phases.py` owns a run clock and a **time-keyed** spawn schedule. Note that
`SpawnDirector`'s release-rate budget is bypassed by both existing consumers
(`budget=0.0, cost=0.0`), which is a signal that a release-rate budget is the
wrong abstraction for a horde. This demo will hand-roll a time-keyed schedule
and an alive-count cap locally, and **that is a finding to report upward**,
not a pattern to spread.

### 4.4 Registration chores

- `tools/agent_view.py`'s `DEMOS` dict
- `GL_ONLY_DEMOS` in `tests/integration/test_demos_render.py`
- the exclusion note in `games/validate_demos.py`
- a `games/README.md` capstone entry

---

## 5. Level Design: "The Clearing"

**Scene:** `games/tamandua_murundus/scenes.py`

- **Map structure:** a single bounded clearing. No scrolling world, no rooms,
  no procgen. A bounded arena is what keeps the swarm on screen, which is what
  makes a density showcase visible at all.
- **Murundus:** a handful of mounds at fixed positions, spread so the swarm
  arrives from several directions.
- **Bounds:** soft — the anteater is kept in, and the swarm is steered back by
  the flock's own cohesion rather than by walls.

---

## 6. Cultural note

The *murundu* is real: the earth mounds that dot the Brazilian cerrado, many
of them built by termites over decades, standing above the seasonal flood
line. The tamanduá-bandeira that eats from them is the same animal *Protocolo
Bandeira* casts as a garbage collector. This demo puts it back in its own
landscape.

---

## 7. Asset Requirements Checklist

- [ ] **Textures:** none on disk. All generated at runtime
      (`TextureFactory.create_from_bytes`).
- [ ] **Audio:** none. See §3.3.
- [ ] **Fonts:** engine default.
- [ ] **Shaders:** none game-local. See §3.2.

---

## 8. Cut and deferred

Every item below was in the original design fiction and is **not** being
built. This section exists so that this document is not read as a backlog in
six months.

| Cut | Why | Gated on |
| --- | --- | --- |
| **The 3-phase Matriarca boss** | Three reasons stack. No multi-phase boss exists anywhere in the repo, and `ai/fsm.py` has *zero importers across `games/`* — so building it means either wiring FSM for the first time (unplanned engine work) or hand-rolling a phase machine that teaches the framework nothing. Behaviour-tree composites have **memory**, so a health-threshold front guard stops being re-checked once a sequence advances — which is issue #46's exact gap and precisely the pattern a phase-abort boss needs. And it is by far the largest content cost in the document, none of it reusable. | **#46** (reactive BT composites / FSM transition table) |
| **Weapon evolution paths** | A second data table proving nothing the first does not, and doubling the balance surface. The mechanism already exists — `Upgrade.requires` + `UpgradeRecord.taken` — so this is content, not capability. | Revisit once `kits/progression` has one real consumer |
| **Claw cleave, tail-sweep ultimate** | Both are `Hitbox` + `ActiveFrameWindow` with a different shape. The tongue proves that path. If they return, they return as *upgrades* in the card table, which is free. | — |
| **12-minute run, six phases** | Run length is a balance problem with zero engine payoff, and a 12-minute run cannot be iterated on through `agent_view` frame captures. Cut to ~4 minutes, three phases + dawn. | — |
| **The synergy table** | Replaced by 6–8 flat upgrades, two of them thematic enough that the flavour survives. | — |
| **Audio** | No demo here ships audio assets. §3.3. | — |
| **Meta-progression** | Between-run persistence proves `persistence`, which is not on the §1.2 list, and needs a second run to be visible at all. | — |
| **Sprite art** | Runtime-generated textures make the tint result *more* legible, not less. §3.1. | — |
| **Sun-angle shadows, normal-mapped terrain** | There is no sampler in `light.frag` at all. A much larger change and its own proposal. | — |

---

## 9. Build order

| PR | Delivers |
| --- | --- |
| **D0** | This document |
| **D1** | The clearing, the tongue, the murundus |
| **D2** | The Revoada — swarm scale and per-instance tint |
| **D3** | Day, dusk, and the night the swarm lights up |
| **D4** | XP motes and the level curve |
| **D5** | The 1-of-3 pick and the Cerrado upgrade table |
| **D6** | This document, rewritten as-built |

D1 is independent. **D2 → D6 is a genuine chain** — each link either consumes
an API the previous introduces or edits the same file — so they merge in
order.
