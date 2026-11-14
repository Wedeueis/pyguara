# Finishing the engine: the roadmap

Written 2026-11-14, from a whole-codebase evaluation made the same day
against `next` at `6154b5a`. It asked four questions: can a professional
game ship on this, is the design coherent, is it overbuilt, and what does
a professional developer experience still lack.

This file orders what is left. It does not replace
`next_engine_plan.md`, which stays the record of workstreams 1 to 7 and
their measurements; where a row below is one of those workstreams, that
file has the detail.

## Where the engine stands

Checked on the day, with the native extension built:

- `pytest`: 8,451 passed, 4 skipped (all four deliberate), 0 failed.
- `ruff check .` and `mypy pyguara` (strict): clean.
- Workstreams 1 to 4 done: wgpu renderer, winit window, gilrs gamepads,
  native images, text and audio. The wgpu path runs without pygame.
- Workstream 5 (Steam) was done **through 5b** when this was written:
  the sans-IO core and the binding, run against real Steam on Windows.
  5c (lobbies) landed the same day in `0240300`; 5d and 5e are open.
  `next_engine_plan.md` has the live status.

**The verdict the roadmap is built on:** a professional 2D desktop game
can ship on this engine if its author is also the engine programmer. It
is not yet something another team could pick up. The core is sound; what
is missing is the last mile of shipping and the first hour of onboarding.

## The feedback, mapped

Every finding from the evaluation, and the phase that answers it.

| Finding | Kind | Phase |
| --- | --- | --- |
| Steam lobbies, Python transport and the two-machine playtest are open | shipping | 1 |
| No packed assets; a shipped game exposes loose files (W30) | shipping | 2 |
| No source protection (W29, Nuitka) | shipping | 2 |
| No Windows version resource (#354) | shipping | 2 |
| `ci.yml` tests Ubuntu and one Windows network job; no macOS job | shipping | 2 |
| Native audio unheard on a real Linux desktop; macOS unrun | shipping | 2 |
| No localisation anywhere in `pyguara/` | shipping | 2 |
| No crash capture for a shipped build | shipping | 2 |
| `display.backend` defaults to `pygame` while wgpu is the stated future | coherence | 3 |
| Studio attaches only on wgpu, so it is absent on the default path | coherence | 3 |
| Game code uses the container as a service locator (173 `container.get` calls in `games/`); `main.py` reads `app._container` | coherence | 3 |
| README is stale: "production-grade", "currently pygame-ce", the retired F12 editor, a broken docs link, `pip install pyguara` | coherence | 3 |
| Status disagrees: `AGENTS.md` says Pre-Alpha, README and classifier say Alpha | coherence | 3 |
| No `pyguara new`; every demo opens with a `sys.path.append` | DevEx | 4 |
| No one-call entry point; a scene is handed the dispatcher by hand, and module 1 hand-wires 94 lines of bootstrap | DevEx | 4 |
| Not on PyPI; no hosted docs site or API reference | DevEx | 4 |
| No Aseprite or skeletal import; the animation editor is #53 | DevEx | 5 |
| Studio lost its config editor and resource browser (#330) | DevEx | 5 |
| No in-game profiler suitable for a shipped build | DevEx | 5 |
| Each native subsystem keeps a Python twin, paid for by five parity suites, though the wheel always ships the extension | overbuilt | 6 |
| pygame and pymunk are required dependencies; `Vector2` is a `pymunk.Vec2d`, so every position depends on a physics library | coherence | 6 |
| DI offers three lifetimes and scopes for what is mostly singleton lookup | overbuilt | 6 |
| About half the non-blank lines in `pyguara/` are docstrings and comments; `REFACTOR_STATE.md` is 4,080 lines | overbuilt | 6 |
| Desktop only: no web, mobile or console | ceiling | not planned |
| One maintainer | risk | not planned |

## Order of work

Shipping first, because Reclaimer is waiting on it and it is what
"commercially viable" means. Coherence second, because it is cheap and
the merge back into `pyguara` is the moment to do it. Onboarding after,
because it only matters once someone else can install the thing.

### Phase 1. Steam, to the end (workstream 5)

| Increment | What | Needs |
| --- | --- | --- |
| **5c** | Friends-only lobby on hosting, rich presence, overlay invite and `+connect_lobby`, admit only lobby members | **Done** (`0240300`) |
| **5d** | `SteamTransport` under `Transport`; `pyguara dist` copies `steam_api` beside the game | 5a, 5b |
| **5e** | Reclaimer hosts and joins through Steam across two home connections | two machines, two accounts |

**Done when** two people on different home connections finish a
Reclaimer session through a Steam invite.

**Then the fork merges back**, as `next_engine_plan.md` already
decides: a merge-commit PR from `next` into `pyguara`'s `main`, Reclaimer
repointed, `pyguara-next` archived. Phases 2 onward happen in `pyguara`.

### Phase 2. What a store release needs

| Item | What | Size |
| --- | --- | --- |
| **Packed assets** (W30, workstream 6) | Loader protocol from path to opener, across every loader; a bake step in `pyguara build` | XL |
| **Platform verification** | A macOS test job and a full Windows test job in `ci.yml`; native audio heard on a real Linux desktop; a wgpu frame seen on macOS | M |
| **Crash capture** | An `excepthook` that writes a report (traceback, engine version, backend, `native.status()`) into the user data directory, and says where | S |
| **Localisation** | A string table keyed by id, a locale setting in config, font fallback for scripts outside Liberation Sans | L |
| **Windows version resource** (#354) | Blocked on validating it off Windows; decide whether to build it on the Windows runner instead | S |
| **Source protection** (W29) | Nuitka, only if the game asks for it | M |

**Done when** a Reclaimer build made by `pyguara build` and `pyguara
dist steam` installs from a Steam depot on a clean Windows machine with
no loose assets, and a crash leaves a report behind.

Localisation is the one item here a game can ship without, in one
language. It is listed because adding it after the UI is written costs
far more than before.

### Phase 3. One story

Small, and best done in the merge-back PR's wake so `pyguara` lands
telling the truth about itself.

1. **wgpu becomes the default `display.backend`.** pygame stays as the
   reference renderer the pixel tests hold wgpu to, selected by name.
   Then decide whether `pygame-ce` can become an extra.
2. **A public way to reach services.** `app.container` exists; fix
   `main.py`, then decide the one sanctioned pattern for a scene
   (constructor injection or `self.container.get`) and make the demos
   agree. An ADR, since it touches the DI container.
3. **Rewrite the README** from the code: backends, Studio in place of the
   F12 editor, working links, an install line that is true.
4. **One status word** across `AGENTS.md`, README and the classifier.

**Done when** a new reader's first ten minutes with the README contain
no statement the code contradicts.

### Phase 4. The first hour

| Item | What | Size |
| --- | --- | --- |
| **`pyguara new <name>`** | A project that runs: `pyproject.toml`, a scene, config, an assets folder, `AGENTS.md` from `pyguara studio instructions`. No `sys.path` edits | M |
| **A one-call entry point** | `pyguara.run(MyScene)`, with the scene's dispatcher supplied by the engine. The explicit bootstrap stays for those who want it | S |
| **Demos as installed code** | Drop the `sys.path.append` from every `games/*/main.py`; run them as modules | S |
| **PyPI release** | The wheels already build; publish them through `release.yml` | S |
| **Hosted docs with an API reference** | Deploy the mkdocs site; generate the reference from docstrings, which are already there | M |

**Done when** `pip install pyguara && pyguara new demo && cd demo &&
python -m demo` opens a window on a machine that has never seen the
repository.

### Phase 5. Authoring

Each is its own issue and none blocks a release.

- Aseprite import into the animation system (#37, #53).
- Studio's config editor and resource browser (#330).
- A frame profiler overlay that works in a shipped build.
- The input production layer (#73) and audio production layer (#72),
  when Reclaimer's plan asks for them.

### Phase 6. One Rust engine, with Python as its interface

**Direction, decided by the user 2026-11-14:** the engine's backend is a
unified, optimised Rust core, and Python is the interface a game is
written in. Whatever in the backend is better in Rust is replaced,
whether it is Python today or someone else's C.

This goes further than ADR 0003, which made Rust "an accelerator, not a
rewrite" and kept a Python twin of every native subsystem.
`docs/adr/0011-one-rust-engine-python-interface.md` supersedes that
position and is the record of this one; read it before building any
item below.

#### Where the line already is

| Rust today | Python or third-party C today |
| --- | --- |
| Renderer (wgpu), window, input, gamepads | ECS storage (`EntityManager`) |
| Image decoding, text, audio mixer | Physics (pymunk, C) |
| Network transport, Steam binding | `Vector2` (a `pymunk.Vec2d`, a tuple subclass) |
| Flow field, particles, sparks, flocking, spatial hash | Render system, batcher and render graph orchestration |
| Static-solid sweep (ADR 0009) | Replication and interpolation, AI, animation, tilemap, UI layout |

#### The rule for "what makes sense"

ADR 0004's pricing rule, unchanged: measure the cost, price the port,
and port what pays. Two findings already on record bound it:

- **Bulk state belongs in Rust; one object at a time does not.** The
  columnar spike (ADR 0008) measured bulk work 290x to 1000x faster and
  per-entity reads 4.7x to 9.5x *slower*. A call across the boundary
  costs more than the Python attribute it replaces.
- **So the unit to move is a system and its data together**, never a
  type that Python then touches per entity, per frame.

What stays Python by design: scenes, the service registry, events, the
UI builder, the gameplay kits, Studio and the CLI. That is the interface.

#### The work, in dependency order

| Item | What | Why it makes sense | Size |
| --- | --- | --- | --- |
| **6a. Retire the Python stores** | The five two-store subsystems keep only their Rust implementation, one at a time. Each parity suite is converted to golden vectors first, not deleted (ADR 0011, Decision 3) | The wheel always ships the extension; the twins cost five parity suites and a second implementation of every change | M |
| **6b. pygame becomes an extra** | wgpu is the default (phase 3); `pip install pyguara` no longer pulls pygame; the software renderer is `pyguara[pygame]` and stays in `dev` as the pixel reference | The wgpu path already runs with pygame unimportable | S |
| **6c. Replication in Rust** | Snapshot interpolation of replicated fields moves beside the transport | The plan names it the largest engine cost on a guest's machine | L |
| **6d. Batched drawing** (workstream 2) | A scene hands over arrays of shapes in one call | 0.4 us of Python per primitive is the frame's largest drawing cost on wgpu | M |
| **6e. Physics on Rapier** | A second `IPhysicsEngine` in the crate, then the default; pymunk retired | Removes the last third-party C engine, gives cross-machine determinism (rollback netcode), and is what unblocks 6f | XL |
| **6f. `Vector2` in Rust** | A PyO3 value type in place of the `pymunk.Vec2d` subclass, if the tuple-compatibility audit comes back cheap; otherwise a tuple subclass of the engine's own | Only possible after 6e: pymunk's C layer accepts tuples and nothing else (ADR 0003, finding 1) | L |
| **6g. Columnar components** (workstream 7) | Component data that systems consume in bulk lives in Rust columns | The foundation the remaining ports stand on; first consumer is 6d | XL |
| **6h. Pure pixel goldens, pygame dropped** | The wgpu pixel tests compare against golden images, as the render-graph tests already do | Removes pygame from `dev` too. Only once nothing but tests needs it | M |

**6e and 6f are one decision.** A Rust `Vector2` cannot be passed to
pymunk, so it either waits for Rapier or pays a conversion on every
physics call. And 6f is worth less alone than it looks: today's add
costs about 290 ns and a PyO3 call still costs 50 to 100 ns, so expect
perhaps 3x on a single operation. It touches about 1,080 uses in
`pyguara/` and 3,660 in tests and demos, all of which may rely on it
being a tuple. Its value is that it stops every position in the engine
depending on a physics library.

**6e must reproduce what pymunk does before it replaces it:** joints,
queries, triggers, collision events and the swept character mover, held
by the existing physics tests run against both backends. Rapier will not
settle a stack identically, so any replay or golden frame containing
rigid bodies changes once.

**Done when** `pip install pyguara` installs no pygame and no pymunk,
one implementation exists of each backend subsystem, and a game written
against the Python interface before phase 6 still runs.

#### Decisions that go with it

1. **The DI container** becomes a typed service registry: see
   `docs/adr/0010-the-container-is-a-service-registry.md`, **status
   proposed**. It subsumes phase 3's item 2 and shares the scene
   constructor change with phase 4's one-call entry point, so the three
   land together. It is Python by design and independent of the items
   above.
2. **Process history** (`REFACTOR_STATE.md` and the rest): see
   `repo_cleanup_plan.md`.

## What is not in this roadmap

- Web, mobile and console targets. wgpu leaves the browser door open,
  but Python does not walk through it cheaply.
- A second maintainer. The roadmap can make the engine easier to join
  (phases 3 and 4); it cannot staff it.
- What `next_engine_plan.md` excludes and this still does: 3D, visual
  scripting, a custom physics solver, Rust ports of gameplay kits.
  **A Rapier backend is no longer excluded**; it is 6e.
- A rewrite of the Python interface. Phase 6 changes what is underneath
  it.
