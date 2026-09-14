# Game Design Document: *Tamanduá: O Guardião dos Murundus*

**Version:** 1.0 — as built
**Engine:** PyGuara (pre-alpha)
**Genre:** Horde Survivor / Density Showcase
**Theme:** A cerrado clearing between dusk and dawn

> **Status: past tense.** Version 0.1 of this document was a scope contract
> written before any of the demo existed, so that scope was argued once
> rather than drifting through six PRs. This is the rewrite: what was
> actually built, what the numbers actually came out at, and where the
> contract was wrong.
>
> **§10 "What the contract got wrong"** is the part worth reading if you
> only read one section. Predictions that held are cheap; the three that
> did not are where the engine taught us something.

---

## 1. Executive Summary

### 1.1 Logline

A giant anteater holds one clearing from dusk to dawn while the cerrado's
insect life rises against it. The termite mounds — *murundus* — are what feed
the swarm. Break one and the tide thins. Survive to first light.

### 1.2 The "Meta" Pitch

The demo exists to prove four pieces of engine work, each of which shipped
before it. Every feature below traces to one of them; §9 lists what was cut for
failing that test.

| Engine capability | Where it lives | What the demo does with it | Shipped in |
| --- | --- | --- | --- |
| **Per-instance sprite tint on the GL backend** | `graphics/backends/moderngl/instancing.py`, `shaders/sprite.*` | One neutral insect texture, N colours, **one draw call**. Dull brown at dusk, bioluminescent at midnight. | #147 |
| **Ambient day/night cycle** | `graphics/lighting/cycle.py` | `AmbientCycle` drives the run's phases and resolves at dawn. One loop of the cycle **is** one run. | #148 |
| **Light type, cone and flicker** | `graphics/lighting/` | The anteater carries a real `SPOT` light — the cone it reads the clearing by. Murundus glow with `flicker_enabled`. | #149 |
| **The progression kit** | `kits/progression/` | Killed insects drop XP motes; `Magnet` pulls them in; a level freezes the run and offers 1-of-3 cards. | #150 |

A fifth arrived *because* of the demo rather than before it: **entity dormancy**
(#157), which came out of a defect this build hit twice. See §10.

Also on display, predating this plan: the flocking optimisation
(`ai/flocking_system.py`), the shared `SpatialHash`, and E8's UI focus ring
(#151), whose first real consumer is the upgrade pick.

**The climax is a density climax, not a boss.** §9.

---

## 2. Gameplay Mechanics

### 2.1 Core loop

**240 seconds**, one clearing, four named phases resolving at dawn. One loop of
the `AmbientCycle` is the whole run, so a single number drives the light, the
swarm's tint and the spawn rate and they cannot drift apart.

| Phase | Cycle | Ambient | Releases per feed |
| --- | ---: | ---: | ---: |
| ANOITECER | 0.00 | 0.66 → 0.40 | 1 |
| NOITE | 0.30 | 0.40 → 0.20 | 2 |
| NOITE FECHADA | 0.55 | 0.20 → 0.14 | 3 |
| REVOADA | 0.75 | 0.14 → 0.11 | 4 |
| AMANHECER | 0.88 | first light | 0 |

The phases are aligned to the *light*, not spaced evenly: the peak-density phase
has to sit in the darkest stretch. An earlier table put REVOADA at 0.86 and the
HUD announced the climax over a frame that still looked like dusk.

The run stops at cycle phase **0.98**, not 1.0. A cycle is a ring — let it reach
1.0 and it is back at phase 0, which is dusk, so the clearing flashed from first
light to nightfall and held there.

### 2.2 The anteater

| Input | Action |
| --- | --- |
| `WASD` / arrows | Move |
| *(automatic)* | **The tongue** auto-lashes the nearest insect in an arc in front of the anteater, on a cooldown |
| `A`/`D`, `Tab`, `Enter` | Pick an upgrade while the run is frozen |

The tongue is `Hitbox`-shaped in spirit but simpler in fact: a cooldown, an arc
test, and a `SpatialHash` radius query for candidates. No new engine surface.
Target search went through the spatial index from D1, before the swarm was large
enough to need it — the tongue should not be the thing that stops scaling.

### 2.3 The swarm

**The hybrid split, as shipped:**

| Layer | Count | Flocks | Hittable | Costs |
| --- | ---: | --- | --- | --- |
| **Interactive** | `SWARM_CAP` = **700** | yes, `groups=3` | yes | flocking + batching |
| **Decorative** | 1,400 | no — cheap drift | no | batching only |

Both draw in **the same batch, through the same tint channel**. The decorative
layer is dimmed rather than recoloured: it is the same insects further away, and
a second hue would read as a second species.

**`SWARM_CAP` is measured.** Re-measured in the real scene with every CPU-side
system a frame runs, decorative layer at shipping size:

| interactive | ms/frame (CPU) |
| ---: | ---: |
| 300 | 3.75 |
| 500 | 6.26 |
| **700** | **9.08** ← shipped |
| 900 | 12.73 |
| 1100 | 16.88 — over budget on CPU alone |

Measured on WSL2 · Mesa 23.2.1 over D3D12 · RTX 3050 · CPython 3.12 · 2026-09-14.

**But the CPU is not what binds on this machine.** See §10.

### 2.4 Murundus

Five mounds, fixed positions, each a spawn anchor with a flickering
`LightSource`. Breaking one stops it feeding. They keep the swarm distributed
around anchors rather than collapsing onto the player — which is a performance
decision as much as a design one, since clumped flocking costs roughly three
times uniform at the same count.

### 2.5 Motes and cards

Killed insects drop XP motes (`Attracted`, pooled, cap 220). The anteater
carries a `Magnet` of radius **108** — deliberately **shorter than the tongue's
150**. Matching them made the magnet invisible: every kill landed inside the pull
radius, so every mote was collected on the frame it dropped and the genre's
signature mechanic never visibly happened.

**The level curve is measured.** A simulated run with the player orbiting the
clearing kills ~242 insects and collects ~236 of them. Against that yield:

| base | growth | levels reached |
| ---: | ---: | ---: |
| **14.0** | **1.28** | **8** ← shipped |
| 10.0 | 1.24 | 9 |
| 8.0 | 1.20 | 11 |
| 6.0 | 1.18 | 13 |

Eight, because the card table is seven: a run should offer about as many picks as
there are distinct things to pick. An idle player reaches level 2.

The same simulation: **242 kills still leaves 638 of 700 alive.** The player
cannot clear the clearing, which is the point of a density climax.

A level freezes the run and offers **1-of-3** from **seven flat upgrades**, two
thematic. Picked with the keyboard through `UIManager`'s focus ring.

---

## 3. Visual & Audio Aesthetic

### 3.1 Art style

**No sprite art ships.** Every texture is generated at runtime through
`TextureFactory.create_from_bytes` — the insect is one soft white blob, 8×8, and
the *tint* is what makes a thousand of them different colours. That keeps the
repo asset-free and makes the result legible: if the tint path broke, every
insect on screen would be that exact white.

### 3.2 Lighting and glow

`WorldPass → LightPass(f2) → CompositePass → PostProcessPass(Bloom, Vignette) → FinalPass`.
No heat haze — that is *Protocolo Bandeira*'s showcase. Bloom threshold **0.62**,
lower than Bandeira's 0.86, because the clearing spends the run dark and what has
to cross is a bioluminescent insect, not a muzzle flash.

**Insects are not lights** — but a tinted sprite cannot bloom unaided either. The
composite multiplies the world by the light map, so under a sub-1.0 ambient a
sprite comes out *darker* than it was drawn, however bright its tint. The flock
is bucketed into a fixed 3×2 grid instead: at most **six aggregate lights at cell
centroids**, weighted by density. Lighting cost stays independent of `SWARM_CAP`.

**No custom `BaseRenderPass`**, as contracted.

### 3.3 Audio

None, as contracted.

---

## 4. Technical Implementation

### 4.1 Module layout, as built

**3,233 lines**, against a contracted ceiling of 3,600–4,000.

| File | Lines | Responsibility |
| --- | ---: | --- |
| `scenes.py` | 950 | The run: setup, input, the frame, the pick |
| `swarm.py` | 434 | Pool, flocking, tint curve, `SWARM_CAP`, pure `build_batch()` |
| `cerrado_fx.py` | 361 | Backdrop, light pool, the cycle, feedback, hit-stop, `run_pipeline()` |
| `render.py` | 250 | Draw calls + palette |
| `systems.py` | 205 | Mounds and the tongue |
| `motes.py` | 198 | Pooled XP motes |
| `upgrades.py` | 196 | The seven cards and their closures |
| `bootstrap.py` | 193 | DI + the render graph |
| `phases.py` | 133 | Run clock, phase table, glow curve |
| `upgrade_ui.py` | 128 | Card elements and layout |
| `components.py`, `events.py`, `main.py` | 184 | — |

### 4.2 `build_batch()` is pure — and it paid

The contract's load-bearing constraint, and it earned its place. GL demos cannot
boot headlessly (SDL's dummy driver has no OpenGL), so the tint showcase would
have shipped covered by a manual smoke and nothing else. `tests/visual/`
rasterises nothing — it snapshots the batch's own tint values at three points on
the curve, on any machine, with no GPU.

### 4.3 Run clock and spawn budget

`phases.py` owns both. `SpawnDirector` is deliberately unused: its model is a
release-rate *budget*, and both existing consumers bypass that gate entirely.
Reported upward as **#163** rather than worked around silently.

### 4.4 Testing

**111 tests**, none of which need a GPU:

| Suite | Tests |
| --- | ---: |
| `test_tamandua_upgrades.py` | 23 |
| `test_tamandua_phases.py` | 22 |
| `test_tamandua_motes.py` | 22 |
| `test_tamandua_swarm.py` | 21 |
| `test_tamandua_clearing.py` | 20 |
| `tests/visual/test_tamandua_swarm_snapshots.py` | 3 |

---

## 5. Level Design: "The Clearing"

A single bounded clearing, five mounds at fixed positions, soft bounds. No
scrolling world, no procgen. A bounded arena is what keeps the swarm on screen,
which is what makes a density showcase visible at all.

---

## 6. Cultural note

The *murundu* is real: the earth mounds that dot the Brazilian cerrado, many of
them built by termites over decades, standing above the seasonal flood line. The
tamanduá-bandeira that eats from them is the same animal *Protocolo Bandeira*
casts as a garbage collector. This demo puts it back in its own landscape.

---

## 7. Asset Requirements Checklist

- [x] **Textures:** none on disk. One 8×8 blob generated at runtime.
- [x] **Audio:** none.
- [x] **Fonts:** engine default.
- [x] **Shaders:** none game-local.

---

## 8. How to run it

```bash
uv run python games/tamandua_murundus/main.py                      # a real window
uv run python tools/agent_view.py tamandua_murundus --gl --frames 2000 --shot 1900
```

**The windowed run has been done** — 180 frames presented to a real X11 window,
which also exercised the vsync-fallback path (`OpenGL vsync unavailable on this
driver; opening without it`). That is the divergence
`docs/guides/agent-visual-inspection.md` exists to warn about, so it is worth
recording that this demo survives it.

**A capture cannot reach a level-up.** `agent_view`'s `--press` has no key-up, so
a held direction pins the anteater against a wall *facing the wall* — one kill in
116 seconds with 589 insects behind it. The demo is fine; the tool cannot play
it. Verifying the upgrade cards required temporarily raising `MOTE_VALUE`.

---

## 9. Cut and deferred

Unchanged from the contract. Every item below was in the original design fiction
and is **not** built.

| Cut | Why | Gated on |
| --- | --- | --- |
| **The 3-phase Matriarca boss** | No multi-phase boss exists anywhere, and `ai/fsm.py` has zero importers across `games/`. Behaviour-tree composites have memory, so a health-threshold front guard stops being re-checked once a sequence advances — #46's exact gap, and precisely the pattern a phase-abort boss needs. Largest content cost in the document, none of it reusable. | **#46** |
| **Weapon evolution paths** | The mechanism already exists (`Upgrade.requires` + `UpgradeRecord.taken`), so this is content, not capability. | A second consumer of `kits/progression` |
| **Claw cleave, tail-sweep ultimate** | Both are the tongue with a different shape. If they return, they return as cards, which is free. | — |
| **12-minute run, six phases** | Run length is a balance problem with no engine payoff, and a 12-minute run cannot be iterated on through frame captures. | — |
| **The synergy table** | Replaced by seven flat upgrades. | — |
| **Audio, meta-progression, sprite art** | None prove anything on the §1.2 list. | — |
| **Sun-angle shadows, normal-mapped terrain** | There is no sampler in `light.frag` at all. | Its own proposal |

---

## 10. What the contract got wrong

Three predictions in version 0.1 did not survive contact. Recorded because they
are the parts that taught us something.

### 10.1 "`SWARM_CAP` will be bound by the CPU"

It is not, on this machine. The CPU table in §2.3 is real and 700 leaves ~7 ms of
headroom — but the demo runs at roughly **47 fps** building to ~320 insects, and
D1 with *no swarm at all* already ran at ~60. **The post-process stack binds
first**: three bloom blur passes at 960×720 through Mesa on D3D12.

So the honest statement of this demo's ceiling is "700 interactive insects are
affordable on the CPU; what the frame actually costs depends on the driver under
the post stack". A machine with a real GL driver would likely tell a different
story, which is exactly why `docs/guides/performance.md` says to quote CPU-side
numbers when quoting an engine limit.

### 10.2 "A pooled entity is cheap while idle"

Assumed, never stated, and wrong. `EntityPool` never destroys anything, so every
component a factory attaches keeps its entity in **every matching query for the
life of the scene**. A pool of 700 insects each carrying a `FlockingAgent` cost
`FlockingSystem` all 700 every tick whether ten were in play or seven hundred —
and worst when the pool was mostly *idle*, because idle entities sat at one
position and an O(n·k) neighbour search over a single point is its own
degenerate case.

Measured, in one process: **103 ms/frame against 1.4 ms** at 20 active out of 700.

This demo worked around it twice by hand before it was fixed properly in the
engine as **entity dormancy (#157)**, which also fixed
`protocolo_bandeira`'s `EnemyPool` — a pool that had never had the workaround and
had been carrying its idle enemies in the spatial index since it merged.

### 10.3 "The HUD belongs on the `UIRenderer`"

It does, in principle. It could not go there in practice: `UIRenderer` composites
*after* the final blit, and `tools/agent_view.py` captures the buffer the final
blit reads — so **nothing on the UI layer is visible to any capture this
repository can take** (**#162**). No `UIManager` widget in any demo has ever been
seen in a frame.

The HUD and the upgrade cards are therefore drawn onto the finished frame, past
the composite and the post stack. The cards remain real `UIElement`s so E8's
focus ring drives them; they simply draw nothing of their own. When #162 is
fixed, `CardElement.render()` is where that drawing belongs and the scene's
hand-drawing is what comes out.

**This is tooling dictating design**, and it should not survive.

---

## 11. What the demo sent back upstream

Nine findings were filed rather than fixed in place, plus one fixed in the engine:

| | |
| --- | --- |
| **#157** | Entity dormancy — **fixed**, not filed. §10.2 |
| #158 | `get_or_create` silently ignores a conflicting dtype; the HDR chain never reaches its tonemap |
| #159 | The material system is plumbed through the pipeline but never read by the backend |
| #160 | `Atlas`/`SpriteSheet` cannot feed the instanced sprite path — no per-instance UV |
| #161 | No visibility culling (with the 25.2 ms number, and the argument against bothering) |
| #162 | `agent_view` cannot capture the UI layer. §10.3 |
| #163 | `SpawnDirector`'s release-rate budget is bypassed by every consumer |
| #164 | `vinagre_matilha` has an O(n²) neighbour loop bypassing the spatial hash |
| #165 | `mourisco_ressonancia` builds a second `FramebufferManager` |
| #166 | GL blend state is set by the window, not the renderer |

That list is the real argument for building a demo against an engine rather than
alongside one.
