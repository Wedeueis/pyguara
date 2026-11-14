# Cleaning the repository at true alpha

Written 2026-11-14, from an inventory of `next` at `6154b5a`. Its four
open questions were decided the same day (see "Decided", at the end).
Nothing here has been moved or deleted yet.

**When:** after the fork merges back into `pyguara` and the roadmap's
phase 3 lands (`engine_completion_roadmap.md`). Cleaning the fork first
would be cleaning a repository that is about to be archived.

## The rule

One question sorts every file: **who needs it, and does it have to
change in the same commit as the engine?**

| Answer | Goes to |
| --- | --- |
| The engine cannot build, test or be understood without it | stays in `pyguara` |
| It explains a decision that still constrains the code | stays, as an ADR or a docs page |
| It teaches someone to use the engine | `pyguara-examples`, under `tutorials/` |
| It shows the engine off, or is a game in its own right | `pyguara-examples`, under `showcase/` |
| It records how the work was done, and the work is finished | archived: a tag, then deleted from `main` |
| It is generated, local or stale | deleted, and ignored |

A GitHub wiki is not on the list. Everything worth keeping as prose is
worth versioning with the code it describes, and the mkdocs site already
does that. Two homes for documentation is how `GEMINI.md` came to
advertise make targets that did not exist.

## What the inventory found

Tracked files, by top-level directory:

| Path | Files | Size | What it is |
| --- | ---: | ---: | --- |
| `pyguara/` | 412 | 5.7 MB | the engine |
| `tests/` | 347 | 5.1 MB | its tests, **and the demos' tests** |
| `games/` | 201 | 2.3 MB | 7 tutorials, 7 capstones, 1 network diagnostic |
| `docs/` | 155 | 1.3 MB | 52 pages, plus a 103-file web design-system bundle |
| `.scratch/` | 50 | 0.4 MB | the finished wayfinder effort |
| `project/` | 31 | 0.4 MB | plans, an archive from January, seven game design documents |
| `REFACTOR_STATE.md` | 1 | 0.3 MB | the finished subsystem audit, 4,080 lines |
| `tools/` | 13 | 0.2 MB | four live tools, nine one-off probes |
| `assets/` | 4 | 0.8 MB | a mascot, an icon, one texture |

**The finding that shapes the plan: the demos are load-bearing.** 44 test
files import from `games/`. They are three different things:

1. **Tests of a game's own rules** -- about 30 files such as
   `test_quintal_cerrado_*.py` (16 of them) and `test_tamandua_*.py`.
   They test the demo, not the engine, and belong wherever the demo goes.
2. **Engine tests that use a demo as the scene to run** -- eight
   integration tests import `BootScene` from `games/boot_process` simply
   because they need *a* scene.
3. **Engine tests that use the demos as a pixel corpus** --
   `test_demos_render.py`, `test_wgpu_demos.py`, `test_wgpu_gl_demos.py`
   and the golden images under `tests/integration/golden/`. This is the
   evidence that wgpu draws what pygame drew. It cannot simply leave.

Kits point the same way: `pack`, `trail`, `echolocation` and `spawn`
each name a capstone as their first consumer.

## Disposition

### Stays in `pyguara`

| Path | Note |
| --- | --- |
| `pyguara/`, `rust/`, `Cargo.*`, `pyproject.toml`, `uv.lock` | the engine |
| `tests/` | engine tests only, after the split below |
| `docs/adr/`, `docs/core/`, `docs/systems/`, `docs/graphics/`, `docs/physics/`, `docs/ai/`, `docs/kits/`, `docs/agents/` | reference |
| `docs/guides/` | except `zero_to_hero.md`, which follows the tutorials |
| `tools/agent_view.py`, `audio_capture.py`, `net_probe.py`, `studio_demo.py`, `demo_list.py` | named in `AGENTS.md` and the guides |
| `tools/bench_native_pool.py`, `price_native_boundary.py` | ADR 0004's pricing rule is run with them; move to `tools/bench/` |
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/`, `.claude/settings.json`, `.claude/hooks/` | agent instructions, generated from one source |
| `.github/`, `Makefile`, `mkdocs.yml`, `CHANGELOG.md`, `LICENSE`, `README.md` | |
| `config/game_config.json` | the default configuration |
| `assets/textures/icon.jpg`, `pyguara_mascot.png` | used by the README and the build's default icon; drop the `.jpg` duplicate of the mascot |

### Becomes documentation

Content that outlived the file it is in.

| From | To |
| --- | --- |
| `REFACTOR_STATE.md`, "Two patterns worth carrying forward" and the Phase A-D method | a `docs/guides/contributing.md`: probe before fixing, uniform-setup as the test smell, guards that return a wrong answer. Perhaps 150 lines of the 4,080 |
| `project/backlog/active/rust_core.md` (RFC-0003) | already decided in ADRs 0003, 0004 and 0006. Check nothing is only in the RFC, then archive it |
| `project/backlog/active/network_multiplayer.md` | when phase 5 of it closes: the design into `docs/systems/networking.md`, the decisions into ADR 0007. Until then it stays active |
| `project/backlog/active/next_engine_plan.md` | its measurements into `docs/guides/performance.md`; the plan itself is archived when workstream 6 closes |
| `project/DEPENDENCY_MAP.md` | dated January and predates the Rust core. Regenerate into `docs/core/architecture.md` or delete; do not carry it as is |
| `.claude/decision-log.md` | any entry that still constrains code becomes an ADR; the rest is archived |

### Moves to `pyguara-examples`

**One repository, decided 2026-11-14**, with `tutorials/` and
`showcase/` inside it: two readers, but one CI for one maintainer to
keep green. It depends on `pyguara` from PyPI like any game would.

#### `tutorials/` -- once `pyguara` is on PyPI

- The seven tutorial modules: `boot_process`, `ecs_mental_model`,
  `asset_pipeline`, `input_events`, `physics_integration`,
  `tilemap_authoring`, `ui_scene_graph`.
- `docs/guides/zero_to_hero.md`, which walks through them.
- `project/backlog/future/tutorial_series_raodmap.md`.
- The tests that are theirs (`test_demo_tilemap_authoring.py`).

It needs the roadmap's phase 4 first: with `pyguara` on PyPI the
`sys.path.append` at the top of each `main.py` goes, and that is the
difference between an examples repository and a folder of scripts.

**Before they leave**, the eight integration tests that borrow
`BootScene` get a scene of their own in `tests/`. A test should not
import a tutorial to have something to run.

#### `design_system/` -- with the tutorials

`docs/design_system/`: 103 files of HTML, JSX and CSS. The engine's own
design system is `pyguara/ui/design_system/` and its page is
`docs/systems/ui-design-system.md`; this bundle is the web reference it
was drawn from, and is not an example. It goes to the same repository
because one was chosen, under its own directory.

#### `showcase/` -- at beta, not before

**Decided 2026-11-14: the capstones do leave**, at beta. The seven
capstones and `net_horde`, each with its own tests and its design
document beside it.

The capstones wait because they are the pixel corpus. While the API is
still moving, a demo in another repository turns every breaking change
into two pull requests that must land together, and the first time they
do not, the corpus goes red and gets ignored. So, in order:

1. **Now, in place:** rename `games/` to `examples/`, move each
   capstone's game-rule tests to `examples/<name>/tests/`, and its
   design document from `project/demos/` to `examples/<name>/DESIGN.md`. `tests/` is
   then the engine's and nothing else's, and what a later move has to
   carry is one directory per game.
2. **Still in place:** make the pixel tests discover demos through
   `demo_list` rather than importing `games.*`, so they can run against
   a checkout of another repository.
3. **At beta:** move them. The engine's CI runs `pyguara-examples` as a
   downstream job, the way Reclaimer is checked by hand today. Two or
   three compact scenes stay behind as `tests/fixtures/`, chosen to keep
   the golden coverage: one render-graph scene with lighting and
   post-processing, one sprite-and-tilemap scene, one UI scene.

### Archived, then deleted from `main`

**A tag, decided 2026-11-14**, not a branch. Tag the last commit that
holds them (`archive/pre-alpha-history`), say so in the changelog, and
delete. `git show <tag>:<path>` reads any of it
back; nothing is lost and a newcomer does not wade through it.

| Path | Why it is finished |
| --- | --- |
| `REFACTOR_STATE.md` | the audit closed 2026-09-09; `AGENTS.md` still calls it ACTIVE and must stop |
| `.scratch/engine-remediation/` | all 49 tickets resolved 2026-10-05 |
| `project/backlog/archive_202601/` | 15 files from before the audit, already named an archive |
| `project/backlog/active/Consolide uma versao completa de feedabcks, bugs....md` | the external audit; reconciled and closed in issue #305 |
| `project/backlog/future/systems_improvement.md`, `technical_debt_cleanup.md` | check each line against open issues, open one for anything live, then archive |
| `tools/columnar_probe.py`, `count_vector_ops.py`, `net_phase0.py`, `preflight_pymunk_vector.py`, `wgpu_probe.py` | each answered a question an ADR now records |

`tools/slice_spritesheet.py` is referenced by nothing. If it is useful
it becomes a `pyguara` CLI command beside `atlas`; if not it goes.

### Deleted outright

- `main.py`: it runs a tutorial scene through `app._container`. The
  roadmap's `pyguara new` and one-call entry point replace it.
- `logs/`, `saves/`, `target/`, `games/__pycache__/` (17 GB on disk):
  untracked already. Confirm `saves/` is ignored.
- `project/backlog/archive_202601/`, `future/` and `project/demos/`,
  once empty. **`project/` itself stays until beta** (decided
  2026-11-14), holding `backlog/active/`. At beta the plans in it are
  finished or have become issues, and it goes with the capstones.

## What `AGENTS.md` has to change with it

`AGENTS.md` is read at the start of every agent session and will
otherwise send one to files that are gone.

- "Ongoing Efforts": remove the subsystem audit and the wayfinder
  sections; point at the roadmap.
- `docs/agents/issue-tracker.md` names `.scratch/engine-remediation/` as
  the wayfinder effort's home.
- "Running the Engine" and "Where things are" name `main.py` and
  `games/`.
- `tests/test_docs_api.py` and `test_demo_bootstrap_conventions.py` walk
  `docs/` and `games/` by path.

## Order

1. Archive tag, then the history deletions. No code depends on any of it.
2. The documentation extractions, in the same pull request as the
   deletion each one replaces.
3. `games/` to `examples/`, game-rule tests and design documents beside
   their games, a test scene in place of `BootScene`.
4. After PyPI: create `pyguara-examples`; tutorials to `tutorials/`,
   `docs/design_system/` to `design_system/`.
5. At beta: capstones to `showcase/`, fixtures left behind, `project/`
   removed.

Steps 1 to 3 are one afternoon each and independent. Each is its own
branch from `main`.

**Done when** a fresh clone's top level is the engine, its tests, its
docs, its examples and its build files, and every path `AGENTS.md` names
exists.

## Decided

By the user, 2026-11-14.

1. **The capstones leave, at beta.** Until then they are `examples/`,
   the engine's pixel corpus.
2. **One extra repository**, `pyguara-examples`, with `tutorials/` and
   `showcase/`. Not `pyguara-learning` and `pyguara-extras`.
3. **A tag for the archive**, `archive/pre-alpha-history`.
4. **`project/` survives until beta**, then goes.
