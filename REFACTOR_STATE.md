# PyGuara Refactor State

Shared memory for the incremental subsystem audit. One subsystem per iteration:
audit (Phase A) -> tests (Phase B) -> docs (Phase C) -> capability gaps
(Phase D) -> approval -> next.

**Started:** 2026-09-06
**Method:** Never analyse more than one subsystem at a time. Every finding that
touches a *different* subsystem gets parked under "Cross-Cutting Concerns"
rather than fixed in place.

---

## How to resume

1. Read **Completed Subsystems** for what is done and **Pending Subsystems**
   for what is next. The queue is ordered by dependency depth: foundations
   first, leaves last.
2. Read **Cross-Cutting Concerns**. Anything found that spans subsystems is
   parked there rather than fixed in place, and several are now GitHub issues.
3. Take the next unticked subsystem. For each one, in order:
   - **Phase A** — audit the code. Reproduce every suspected defect with a
     throwaway probe *before* fixing it. Reading is not enough: every
     significant defect this audit has found looked correct on a read-through
     and was obvious under a probe.
   - **Phase B** — audit the tests, and write the verdict into the iteration
     log. Not "added N tests" — a judgement on what the existing suite is
     *worth*: which tests are load-bearing, which are theatre. The recurring
     smells here: **uniform setup** (every test builds the subject the same
     way — see the note below; this has hidden most bugs), **assertions on
     private state** (`obj._internal[...]` instead of the public getter, so a
     refactor breaks the test not the code), **tautological asserts**
     (`assert x is not None` on something that cannot be None; `assert not
     raises` as the only check), and **fixtures that mock away the unit under
     test** (`test_config.py` mocked the filesystem, so no round-trip bug
     could surface). Then add or rewrite tests to close the gap the verdict
     names.
   - **Phase C** — audit the docs, and verify the documented API actually
     exists. Three pages have described functions that never existed.
   - **Phase D** — capability gaps. A subsystem can be defect-free and still
     be missing something the engine's target genre (roguelikes — issue #28)
     will need. Ask: what would a shipped game reach for here and not find?
     Name each gap in the iteration log with a rough size and a
     **disposition**:
       - *in-slice* — small enough and squarely in this subsystem; build it
         now (e.g. the resources `reload()` primitive).
       - *new issue* — coherent, sizeable, or needs a product decision; open
         a GitHub issue and add it to "Tracked as GitHub issues" (e.g. #37
         for the animation authoring layer).
       - *parked* — note it under "Left open" / a CC; revisit when a
         downstream subsystem forces the question.
     This is not a licence to widen the slice — the default for anything
     non-trivial is *new issue* or *parked*. It replaces the ad-hoc
     "Left open" notes with a deliberate forward-looking pass.
4. Branch from `main` — see "Branching and Pull Requests" in `CLAUDE.md`.
5. Verify each commit **in a clean checkout**, not the working tree:
   `git worktree add --detach <tmp> <sha>` then run the suite there. A working
   tree can pass with unstaged changes the commit does not contain; that has
   happened once.
6. Log the iteration at the bottom of this file and open a PR.

### Two patterns worth carrying forward

**Guards that return a wrong answer.** Four graphics slices and one DI
iteration turned up the same shape: a check that avoids a crash by
substituting a plausible-looking wrong value. `safe_zoom = 0.001` gave
coordinates six orders of magnitude out; `window_ratio ... else 0` gave a
450px viewport for a 0px window. In each case the crash would have been easier
to diagnose. Grep for `if x != 0 else`, `or 1`, and bare `except: pass`.

**Uniform test setup, not missing tests.** The blind spot has repeatedly been
that every existing test built its subject the same way. `test_query_cache.py`
always used `create_entity()`, so an `add_entity()` bug survived;
`test_config.py` always mocked the filesystem, so no round-trip bug could
surface; every DI test was single-threaded, so a missing lock survived. Ask
how the subject is *constructed*, not just what is asserted.

---

## Active Subsystem

**None — `pyguara/ai` closed 2026-09-08 (branch `refactor/ai-audit`).**
Next in the queue is Tier 4: `pyguara/ui` (layout engine, widgets, theming).
Open `REFACTOR_STATE.md` "How to resume" and take it.

`pyguara/ai` in one slice, ~2,100 lines (`fsm`, `blackboard`, `components`,
`ai_system`, `steering`, `steering_system`, `behavior_tree`, `navmesh`,
`pathfinding/{core,astar,grid}`). No single dead-end like audio's SFX, but
the recurring shapes held. **`world_to_grid_coords()` used `int()`** (rounds
toward zero) not `floor`, so any grid with a non-zero `offset` — or any
negative local coordinate — resolved to the wrong cell, and the whole
quadrant left of / above the origin collapsed onto row/column 0 (probe:
world `(-10,-10)` → grid `(0,0)`, whose centre is `(16,16)` — a sign flip).
"Guard/formula that returns a wrong answer." Now `math.floor`. **`AISystem`
passed the raw `Entity` as the behavior-tree context**, so `WaitNode` (and
any node reading `context.dt`) fell back to a hardcoded `1/60` and drifted
with the real frame rate — `WaitNode(1.0)` took ~2.1 s at 30 fps, ~3.5 s at
144 fps; the engine's own game (`protocolo_bandeira`) had to hand-roll its
own AI system with a `dt`-carrying context to work around it. Fixed by a
small `AIContext` (entity + dt + blackboard), user's choice, passed to
`tree.tick()`. **`SteeringSystem` only dispatched `seek/arrive/flee/wander`**
— `SteeringBehavior.pursuit()` / `.evade()`, the only two that lead a
*moving* target (the roguelike "chase the player" case), were fully
implemented but unreachable through the ECS system, and an unknown
`behavior` string produced zero force with no warning. "Declared and wired
to nothing" + silent guard. Per the user's choice, `behavior` is now a
`SteeringBehaviorType` enum (`SEEK/ARRIVE/FLEE/WANDER/PURSUIT/EVADE`),
coerced-and-validated in `__post_init__` (unknown → `ValueError` at
construction), all six wired, `SteeringAgent` gained `target_velocity` for
pursuit/evade. **`behavior="arrive"` overshot the target and orbited it
forever** — the dt-scaled steering force is only a weak proportional brake;
the system now enforces the arrive speed ramp directly and snaps to rest.
**Generic `AStarPathfinder` crashed on a priority tie** (`TypeError: '<' not
supported`) whenever graph nodes were not order-comparable — `Node` is bound
only to `Hashable`, ties are the common case; latent for the shipped
`GridGraph` (tuple nodes). Added the standard monotonic tie-break counter
(also to `NavMeshPathfinder`'s copy). **`NavMesh.remove_polygon()` left the
dangling id in every other polygon's `neighbors` list** — now pruned. FSM
`set_initial_state()` / an unknown transition target were silent no-ops —
now logged, and a second `set_initial_state()` calls the previous state's
`on_exit()`. `NavMeshPathfinder`'s docstring claimed funnel smoothing it
does not do — corrected. Recurring shapes: "guard/formula that returns a
wrong answer" (`int` vs `floor`, silent steering/FSM no-ops), "declared and
wired to nothing" (`pursuit`/`evade`, `AISystem` never threading `dt`),
"one advance per frame / hardcoded dt" (`WaitNode`), and uniform test setup
— `TestCoordinateConversion` used only positive coords + positive offsets
(hid the floor bug), `test_wait_completes` baked the `0.016` fallback into
its comment, and there was **no test at all** for `AISystem` or
`SteeringSystem` despite both being auto-registered on every scene. Tests
+29 (1770 → 1799). See the iteration log entry below.

**Capability gaps (Phase D)** — the subsystem is defect-free but thin: BT
composites have memory with no *reactive* variant (a guard `ConditionNode`
at the front of a `SequenceNode` stops being re-checked once the sequence
advances past it) and `ParallelNode` re-ticks already-completed children;
FSM has no transition table / event-driven transitions (only
`update()`-returns-a-name); no declarative blackboard BT nodes (every leaf
is a hand-written closure); `NavMesh` needs a full shared edge (no
partial-edge portals / T-junctions), returns polygon-*centre* waypoints (no
funnel string-pulling), and generates nothing (you hand it convex
polygons). `SteeringSystem` integrates `transform.position` directly,
bypassing physics/`CharacterMover` — agents don't collide or separate.
`_wander_targets` is only evicted on scene exit, not per destroyed entity.
Disposition: the BT/FSM authoring gaps → propose one **new issue** (sibling
of #37/#40/#43); navmesh funnel/portals/generation → **parked** pending a
real consumer (flow-field pathfinding is already #28's); steering-vs-physics
→ **parked** for the top-down `CharacterMover` slice; `_wander_targets`
eviction → left-open note. See the iteration log.

**Left open.** `WaitNode` still has a `getattr(context, "dt", 1/60)`
fallback for trees ticked with a bare object (now a named constant, not a
magic literal). The arrive fix is a system-side velocity clamp, not a
redesign of the force/integration model shared by all behaviors —
`_ARRIVE_STOP_DISTANCE = 1.0` world units. `NavMeshPolygon.contains_point`
references `xinters` before assignment on a code path the outer guards make
unreachable (fragile, not fixed).

---

`pyguara/persistence` in one slice, ~970 lines (`manager`, `storage`,
`serializer`, `migration`, `types`). The migration half was actually sound
— the chain-integrity guards (`to_version > from_version`, `to_version <=

`pyguara/persistence` in one slice, ~970 lines (`manager`, `storage`,
`serializer`, `migration`, `types`). The migration half was actually sound
— the chain-integrity guards (`to_version > from_version`, `to_version <=
current_version` on register, "no gap" in `get_migration_path`, no
downgrade) compose correctly and the `while version < current_version` loop
provably terminates; probes for an overshoot / infinite loop all came back
negative. The save/load half carried the recurring shapes. **`save_data()`
discarded `storage.save()`'s return value** — `FileStorageBackend.save`
returns `False` on `OSError` rather than raising, so a full disk still
logged "Successfully saved" and returned `True` ("guard that returns a
wrong answer"). **`FileStorageBackend` sanitised keys by deleting bad
characters**, so `"slot 1"` / `"slot/1"` / `"slot.1"` all collapsed onto
`slot1` and silently overwrote each other; an all-punctuation key wrote
literal `.dat`/`.meta` — the resources F2 stem-collision shape exactly.
Now non-round-tripping keys raise `ValueError`. **Data and meta were two
independent `os.replace` calls** while the load path's comment claimed
"atomic save ensures both or neither" — a crash between them left new data +
stale-checksum meta, and `load_data` then returned `None` for a save whose
bytes were intact. User asked which fix was more systemic; chose the
envelope: metadata is framed into **one blob** (`{"…"}\n<payload>`),
`StorageBackend` drops its `metadata` param and becomes a plain key→blob
store, `FileStorageBackend` writes one `{key}.save` file (+ dir fsync +
temp-file sweep). **`compress=` was a documented no-op** — implemented
(gzip, recorded in the header). **`SerializationFormat.MSGPACK` was a
public enum member with no implementation** though `msgpack` is a declared
dep — implemented via the existing `prepare_for_json` / `game_object_hook`
path and exposed through a new `fmt=` arg on `save_data`. `SaveMetadata`
was built then hand-copied field by field and never reconstructed on load;
now carries `format`/`compressed`, used via `asdict`, engine version from
`importlib.metadata` (was hard-coded `"1.0.0"`), UTC timestamp. Migration
gained `from_version >= 1` / `current_version >= 1` construction guards and
`MigrationRegistry` is `eq=False`. Recurring shapes: "declared and wired to
nothing" (`compress`, `MSGPACK`, the `metadata` half of `SaveMetadata`),
"guard that returns a wrong answer" (the swallowed `save()` failure, the
key mangling), "identity vs value" (`MigrationRegistry`), and uniform test
setup — every storage test used an already-safe key (`save1`, `slot_a`,
`autosave`) so the collapse was unreachable; every migration test used
positive versions from 1 so the guards had no test. Tests +35 (1735 →
1770). See the iteration log entry below.

**Capability gaps (Phase D)** — the subsystem is defect-free but thin for a
shipped game: no backup / prior-version retention (one `.save` file, no
fallback on a bad-but-valid save or bit-rot), no `list_saves()` / cheap
metadata-header read / `delete`/`exists` facade for a save-menu UI,
`FileStorageBackend` roots at CWD-relative `saves/` not the OS user-data
dir. First three grouped into **#43** ("persistence production layer",
sibling of #37). Envelope `format_version` header field is a small parked
add. Run/meta save split is #28's. Async save and tamper-resistance
(HMAC vs. accept user-editable) need a decision. See the iteration log.

**Left open.** `save_data` always writes JSON metadata + records the
payload `fmt`; no per-call *metadata* format choice (fine — the header is
meant to stay greppable). `BINARY` (pickle) load is unauthenticated —
documented trusted-input-only, not fixed (a signature scheme is its own
slice). Mypy's `python_version` is `3.10` while `requires-python` is `3.12`,
so `datetime.UTC` (ruff UP017's fix) fails typecheck — one `# noqa: UP017`
and a possible CC (mypy target vs `requires-python`).

`pyguara/resources` in one slice, ~1,100 lines (`manager`, `meta`,
`loader`, `types`, `data`, `data_loader`, `exceptions`; hot reload itself
lives downstream in `pyguara/dev`). No headline crash like audio's dead
SFX — the subsystem was in better shape — but the same recurring shapes.
**Reference counting was internally inconsistent and wired to nothing**:
`load()` auto-incremented on every call including cache hits, `release()`
auto-unloaded at 0, so `unload_unused()` ("cleanup between scenes") could
never evict a resource anything used and a released one was already gone —
dead code. No engine caller of acquire/release/unload/unload_unused;
`AudioManager` `load()`s per play, so the count climbed forever.
`Resource._ref_count` was a *third*, entirely dead counter. Reworked (user
chose "fix the model + add reload()"): `load()` is a pure cache-get, the
resource enters unpinned (0); `acquire()`/`release()` pin; `unload_unused()`
now meaningfully sweeps. `index_directory()` **silently resolved a stem
collision to whichever file the walk hit last** — now the ambiguous bare
stem is dropped with a warning, full-name keys always win. `MetaLoader`
**cached parsed meta by path with no invalidation** (stale after a disk
change — wrong under hot reload) and the path-only key **swallowed the
`expected_type` mismatch warning** after the first call — now mtime-pinned
+ re-read on change + `invalidate()`, and the type check runs every call.
`DataResource`'s docstring claimed "hot-reloaded by the ResourceManager"
with **no reload API** — added `ResourceManager.reload()` (re-run loader,
re-read `.meta`, swap in place, keep count). The **`.meta` import pipeline
was ~70% scaffolding** (`AudioMeta`/`SpritesheetMeta` had no consumer, GL
loader hardcoded `LINEAR`) — wired end to end per the user's choice:
`Resource.import_meta` carries the resolved sidecar, `GLTextureLoader`
honours `filter` (and its default flips to `NEAREST`, matching the pygame
path — the two backends disagreed), the audio backend applies
`AudioMeta.volume_db` as a per-asset channel gain, `SpriteSheet` gained
`margin`/`spacing` (previously meaningless everywhere) + `slice_from_meta`.
Recurring shapes: "declared and wired to nothing" (the whole ref-count
half; `AudioMeta`; `_ref_count`), "identity vs value" absent here, and
uniform test setup — `test_resources.py` asserted on `_reference_counts` /
`_cache` / `_path_index` privates and hand-poked an impossible state into
`test_unload_unused`; every `test_meta.py` test used a fresh `MetaLoader()`
so the stale-cache bug had no test that could see it. See the iteration
log entry below.

**Capability gaps → #40** (async / batch / `preload` loading, hot-reload
wiring + stale-holder handling, error context on a missing file, asset
dependency graph — the resources equivalent of what Phase D now does
explicitly). **Left open.** `AudioMeta.loop_start/loop_end/normalize/
load_mode`, `TextureMeta.mipmaps/wrap_s/wrap_t` still have no consumer —
they need streaming / DSP / GL-state work past a single slice
(authoring-layer gap, sibling of #37). Under the new lifecycle the audio
system should `acquire()` clips it wants to survive a between-scene
`unload_unused()` — a small `pyguara/audio` follow-up (no behaviour change
today: nothing calls `unload_unused()` yet). `ResourceManager` has no lock
on `_cache`/`_reference_counts` (check-then-act) — no concurrent caller
exists, parked as CC. `load_atlas()` still re-parses its JSON on every call
(no `Atlas` cache) — perf nicety, not a defect.

`pyguara/animation` in one slice, both halves (tween/easing in
`pyguara/animation`, and the sprite-animation FSM in
`pyguara/graphics/{animation_system.py,components/animation.py}`, only
"surveyed" during the graphics audit): **`Tween` accepted only `float`
scalars and `tuple`s** — `Tween(0, 100, 1.0)` (int), a `list`, mixed
int/float, or a `Color` all constructed fine then crashed on the first
`update()` with a bare `AssertionError` (`_interpolate` used
`assert isinstance(x, float)` as runtime validation). `Tween` was a
value-equality `@dataclass`, so `TweenManager.remove(b)` removed an equal-
but-different tween `a`. `Animator.update()` advanced at most one frame per
call (`if`, not `while`), so a lag spike dropped frames and drifted
permanently behind. `AnimationStateMachine` re-fired `on_complete` and the
transition check every frame a non-looping clip sat finished (a callback
storm for any terminal state). `AnimationClip` had no validation
(`frame_rate=0` → `ZeroDivisionError`, `frames=[]` → `IndexError`).
`TransitionCondition.IMMEDIATE` was declared but `_check_transitions()` had
no branch for it. `Scene.update_animations()` — documented as the way to
tick animations — double-updated everything now that `AnimationSystem` is
auto-registered; removed. See the iteration log entry below.

`pyguara/audio` in one slice: **SFX playback was dead end to end** —
`PygameAudioSystem._play_sound` called `Channel.get_id()`, which pygame-ce
has no such attribute (`Channel.id`), so every real `play_sfx` /
`play_sfx_at_position` raised, was swallowed by a blind
`except (AttributeError, Exception)`, and returned `None` while the sound
played on untracked. Every one of the 107 audio tests missed it: they
`patch("pygame.mixer")` wholesale (the "mock away the unit under test"
smell). Volume + pan were set on the ResourceManager-shared `Sound`, not the
channel, so concurrent plays of one clip corrupted each other's loudness;
recycled channels kept the previous sound's hard pan; `AudioSourceSystem`
never detected a finished one-shot (so `is_playing` lied forever, a source
could not be replayed, and stale channel ids leaked spatial mix updates onto
whatever reused the channel); `SpatialAudioConfig` had no validation (0 →
`ZeroDivisionError` in `calculate_pan`); `IAudioSystem` had no `shutdown`.
See the iteration log entry below.

`pyguara/input` in one slice: `InputContext` was inert end to end (no way to
leave `GAMEPLAY`), gamepad identity was by device index not SDL instance id
(unplugging a non-last pad flagged the wrong one), `rebind(SWAP)` reported
`SWAPPED` when it had actually just unbound, `RebindResult.CONFLICT` was
unreachable, and `OnAction`/`OnRawKey`/`OnMouse` events were frozen at
`timestamp=0.0`. See the iteration log entry below.

`pyguara/physics` ran over four slices: PR #24 (substepping), PR #25
(character movement onto `CharacterMover`), PR #27 (triggers + joints, both
inert end to end), and the closing slice on branch
`refactor/physics-queries-sleep-close` (spatial queries, body sleeping, the
`substeps` decision, Phase C). See the iteration log entries below.

**`substeps` resolved: stays 4.** The benchmark put the cost of 4 at
~0.65 ms/update for 200 dynamic bodies (2.5 ms at 500) — an order of
magnitude below the "half a frame" this file previously feared — while 4
stops a body against a 10px wall up to ~900 px/s vs ~400 at 2. Body sleeping
(new in the closing slice) further cuts the settled-props cost. `substeps=2`
is documented as the knob for someone running many hundreds of fast bodies.

**Next physics slice, its own build/PR (`CharacterMover`-sized), not a
blocker for anything:** a **top-down kinematic character controller** —
8-directional collide-and-slide
with actor-vs-actor soft separation and push-out-of-overlap. The physics
layer currently serves only platformers; every game the engine targets is
top-down, and dynamic bodies there hit the same sink/creep/jitter family the
platformer did, plus crowd stacking. Platformer polish (slope handling,
variable jump height, corner correction) and `surface_velocity` (conveyors)
are **parked as low priority** given the genre.

Framework-level work above physics — combat spine, seeded RNG service,
stat/modifier system, projectile layer, procgen, tilemap, run/meta save
split, flow-field pathfinding, hit-stop, combat juice, local co-op input —
is **issue #28 (roguelike core)**, out of scope for the physics audit.
#28 carries the layering decision: three layers (core / `pyguara/kits/*` /
game), mechanism in core and world-model vocabulary in an opt-in kit, core
may not import a kit. Prior art: `github.com/Wedeueis/reclaimer_legacy`, an
earlier iteration of this engine (fused with one game, hence the restart)
that already built and tested combat, stats, equipment/modules, procgen,
GOAP/utility AI and projectiles — mine it **per kit**, reading its
`reclaimer/game/<subsystem>` for interface shape and tests before starting
the matching `pyguara/kits/<kit>` piece.

**The big decision — move characters off dynamic rigid bodies onto
`CharacterMover` — is resolved, built, and merged.** Full physical parity
(knockback, platform riding, crate pushing), on Celeste's model. See
`docs/physics/character-movement.md` for the shape it took; the summary:
`CharacterBody` replaces `RigidBody` for a character (no engine shape at
all), `SolidMover`/`SolidSystem` carry and push actors for moving platforms
and crates, `apply_knockback()` gives `Hazard.knockback_force` something to
consume. `guara_falcao` has a demo patrolling platform and a pushable crate.

**Tier 2 is complete:** `config`, `application`, `scene`, `systems`.
`pyguara/graphics` is complete too — see Completed Subsystems below.

---

## Pending Subsystems

Ordered roughly by dependency depth: foundations first, leaves last.

### Tier 1 — Foundations (no intra-engine dependencies)
- [x] `pyguara/common` — Vector2, Color, Rect, shared components *(done)*
- [x] `pyguara/log` — logging facade *(done)*
- [x] `pyguara/events` — EventDispatcher, Event protocol *(done)*
- [x] `pyguara/di` — DIContainer, auto-wiring, lifetimes *(done)*

### Tier 2 — Core runtime
- [x] `pyguara/ecs` — Entity, Component, EntityManager, QueryCache *(done)*
- [x] `pyguara/config` — configuration loading/merging *(done)*
- [x] `pyguara/application` — Application loop, bootstrap, sandbox *(done)*
- [x] `pyguara/scene` — Scene base, SceneManager, serializer *(done)*
- [x] `pyguara/systems` — system manager / base systems *(done)*

### Tier 3 — Subsystems
- [x] `pyguara/graphics` — ~8,000 lines, audited in five slices:
    - [x] 1. Window boundary — `window.py`, `IWindowBackend` *(active)*
    - [x] 2. Components — camera, particles, animation, geometry, sprite *(active)*
    - [x] 3. Backends — pygame, ModernGL, headless renderers *(active)*
    - [x] 4. Pipeline — graph, passes, framebuffer, viewport, batching *(active)*
    - [x] 5. Assets & effects — spritesheet, ninepatch, materials, vfx, lighting *(active)*
- [x] `pyguara/physics` — protocols, pymunk backend, joints, materials
    - [x] Character movement switched to `CharacterMover` (PRs #24, #25)
    - [x] `collision_system.py`, `trigger_volume.py`, `trigger_system.py`,
      `joints.py` — triggers + joints rebuilt end to end (PR #27)
    - [x] Spatial queries, body sleeping, `substeps` decision, Phase C
      (branch `refactor/physics-queries-sleep-close`)
- [x] `pyguara/input` — input manager, rebinding *(done)*
- [x] `pyguara/audio` — audio manager, spatial audio *(done)*
- [x] `pyguara/animation` — tween, easing, FSM *(done)*
- [x] `pyguara/resources` — loaders, meta, hot reload *(done)*
- [x] `pyguara/persistence` — save/load, migration *(done)*
- [x] `pyguara/ai` — FSM, steering, pathfinding, navmesh, behaviour trees *(done)*

### Tier 4 — Tooling & authoring
- [ ] `pyguara/ui` — layout engine, widgets, theming
- [ ] `pyguara/prefabs` — prefab definition and instantiation
- [ ] `pyguara/editor` — in-engine editor, inspector tools
- [ ] `pyguara/scripting` — coroutines, script hosting
- [ ] `pyguara/replay` — deterministic replay
- [ ] `pyguara/dev` — dev-only helpers
- [ ] `pyguara/cli` — command line entry points
- [ ] `pyguara/tools` — atlas/build tooling

---

## Completed Subsystems

| Subsystem | Closed | Summary |
| --- | --- | --- |
| `pyguara/ai` | 2026-09-08 | One slice (`fsm`, `blackboard`, `components`, `ai_system`, `steering`, `steering_system`, `behavior_tree`, `navmesh`, `pathfinding/*`; ~2,100 lines). **`world_to_grid_coords()` used `int()` not `floor`** — a non-zero grid `offset` or any negative local coord resolved to the wrong cell, and the quadrant left of/above the origin collapsed onto row/col 0 (world `(-10,-10)` → grid `(0,0)`, a sign flip). "Formula that returns a wrong answer" → `math.floor`. **`AISystem` passed the bare `Entity` as the BT context**, so `WaitNode` (any `context.dt` reader) fell back to a hardcoded `1/60` and drifted with frame rate — `WaitNode(1.0)` = ~2.1s @30fps, ~3.5s @144fps; the engine's own game hand-rolled its own AI system to dodge this. Fixed with a small `AIContext` (entity+dt+blackboard), passed to `tree.tick()`. **`SteeringSystem` only dispatched `seek/arrive/flee/wander`** — `pursuit`/`evade` (the only moving-target behaviors) were implemented but unreachable, and an unknown `behavior` string produced zero force silently. `behavior` is now a validated `SteeringBehaviorType` enum, all six wired, `SteeringAgent` gained `target_velocity`. **`behavior="arrive"` overshot and orbited the target forever** — system now enforces the arrive speed ramp on velocity and snaps to rest. **Generic `AStarPathfinder` crashed on a priority tie** with non-order-comparable nodes (`Node` is only `Hashable`; ties are common) — added the monotonic tie-break counter (also to `NavMeshPathfinder`). **`NavMesh.remove_polygon()` left dangling ids in other polygons' `neighbors`** — now pruned. FSM `set_initial_state()` / unknown transition targets were silent no-ops — now logged; a second `set_initial_state()` exits the prior state. `NavMeshPathfinder` docstring claimed a funnel algorithm it lacks — corrected. Recurring shapes: "guard/formula returns a wrong answer", "declared and wired to nothing" (`pursuit`/`evade`, `dt` never threaded), "hardcoded dt", uniform test setup (`TestCoordinateConversion` all-positive; **zero** tests for `AISystem`/`SteeringSystem`). Tests +29 (1770 → 1799). Phase D: BT/FSM authoring gaps (no reactive composites, no FSM transition table, no declarative blackboard nodes) → propose a new issue (sibling of #37/#40/#43); navmesh funnel/partial-portals/generation → parked (flow-field is #28's); steering-vs-physics → parked for the top-down `CharacterMover` slice. Left open: `WaitNode` keeps a named `getattr` dt fallback; the arrive fix is a velocity clamp (`_ARRIVE_STOP_DISTANCE = 1.0`), not a force-model redesign; `NavMeshPolygon.contains_point` has a fragile-but-unreachable `xinters`-before-assignment. |
| `pyguara/persistence` | 2026-09-08 | One slice (`manager`, `storage`, `serializer`, `migration`, `types`; ~970 lines). The **migration half was sound** — the chain-integrity guards compose and the path loop provably terminates; overshoot/infinite-loop probes came back negative. The save/load half held the recurring shapes. **`save_data()` discarded `storage.save()`'s return** — `FileStorageBackend.save` returns `False` on `OSError`, so a full disk logged "Successfully saved" and returned `True`; now checked. **`FileStorageBackend` sanitised keys by deleting bad chars** — `"slot 1"`/`"slot/1"`/`"slot.1"` all collapsed onto `slot1` and silently overwrote each other (the resources F2 stem-collision shape); non-round-tripping keys now raise `ValueError`. **Data + meta were two independent `os.replace` calls** while the load path claimed "atomic save ensures both or neither" — a crash between them made an intact save unreadable (stale checksum → `None`). User chose the systemic fix: metadata is framed into **one blob** (`{header json}\n<payload>`), `StorageBackend` drops its `metadata` param (plain key→blob store), `FileStorageBackend` writes one `{key}.save` file + dir fsync + temp-sweep. **`compress=` was a documented no-op** → gzip, recorded in the header. **`SerializationFormat.MSGPACK` was a public enum member with no impl** though `msgpack` is a declared dep → implemented via the existing `prepare_for_json`/`game_object_hook` path, exposed through a new `fmt=` arg. `SaveMetadata` was hand-copied field by field and never read back on load → now carries `format`/`compressed`, used via `asdict`, engine version from `importlib.metadata` (was `"1.0.0"`), UTC timestamp. Migration gained `from_version >= 1` / `current_version >= 1` guards; `MigrationRegistry` is `eq=False`. Recurring shapes: "declared and wired to nothing" (`compress`, `MSGPACK`, `SaveMetadata`'s metadata half), "guard that returns a wrong answer" (swallowed `save()` failure, key mangling), "identity vs value" (`MigrationRegistry`), uniform test setup (every storage test used an already-safe key; every migration test used versions from 1). BREAKING: on-disk save format changed (`.dat`+`.meta` → `.save`); pre-alpha, no migration. Tests +35 (1735 → 1770). Phase D capability gaps: no backup/retention, no save-menu API (`list_saves`, cheap metadata read, `delete`/`exists` facade), CWD-relative save dir — grouped into #43 ("persistence production layer", sibling of #37); envelope `format_version` parked; run/meta split is #28's. Left open: `BINARY`/pickle load unauthenticated (trusted-input-only); mypy `python_version` 3.10 vs `requires-python` 3.12 forces a `# noqa: UP017` (possible CC). |
| `pyguara/resources` | 2026-09-08 | One slice (`manager`, `meta`, `loader`, `types`, `data`, `data_loader`; hot reload lives downstream in `pyguara/dev`). No headline crash — better shape than recent subsystems — but the recurring shapes held. **Reference counting was internally inconsistent and wired to nothing**: `load()` auto-incremented on every call incl. cache hits, `release()` auto-unloaded at 0, so `unload_unused()` could never evict anything in use and a released resource was already gone — dead. No engine caller of acquire/release/unload/unload_unused; `AudioManager` `load()`s per play → count climbs forever. `Resource._ref_count` was a *third* dead counter. Reworked (user: "fix the model + add reload()"): `load()` is a pure cache-get → unpinned (0); `acquire()`/`release()` pin; `unload_unused()` now sweeps. `index_directory()` **silently resolved a stem collision to the last file walked** — now the ambiguous bare stem is dropped with a warning, full-name keys always win. `MetaLoader` **cached parsed meta by path with no invalidation** (stale after a disk change — wrong under hot reload) and the path-only key **swallowed the `expected_type` mismatch warning** after the first call — now mtime-pinned + re-read + `invalidate()`, check runs every call. `DataResource` docstring claimed "hot-reloaded by the ResourceManager" with **no reload API** — added `ResourceManager.reload()` (re-run loader, re-read `.meta`, swap in place, keep count). The **`.meta` import pipeline was ~70% scaffolding** (`AudioMeta`/`SpritesheetMeta` had no consumer, GL loader hardcoded `LINEAR`) — wired end to end (user: "wire it up in this slice"): `Resource.import_meta` carries the resolved sidecar; `GLTextureLoader` honours `filter` (default flips to `NEAREST`, matching the pygame path); audio backend applies `AudioMeta.volume_db` as a per-asset channel gain; `SpriteSheet` gained `margin`/`spacing` (previously meaningless) + `slice_from_meta`. Recurring shapes: "declared and wired to nothing" (the whole ref-count half; `AudioMeta`; `_ref_count`) and uniform test setup (`test_resources.py` asserted on `_reference_counts`/`_cache`/`_path_index` privates and hand-poked an impossible state into `test_unload_unused`; every `test_meta.py` test used a fresh `MetaLoader()`). Tests +21. Left open: `AudioMeta.loop_*`/`normalize`/`load_mode`, `TextureMeta.mipmaps`/`wrap_*` still unconsumed (need streaming/DSP/GL-state — authoring-layer gap, sibling of #37); audio should `acquire()` its clips under the new model (small `pyguara/audio` follow-up, no behaviour change today); no lock on the cache dicts (no concurrent caller, parked CC). |
| `pyguara/animation` | 2026-09-08 | One slice, both halves (`pyguara/animation` tween+easing, plus the sprite-animation FSM in `pyguara/graphics` only surveyed during the graphics audit). **`Tween` accepted only `float` scalars / `tuple`s**: `Tween(0, 100, 1.0)`, a `list`, mixed int/float, or a `Color` constructed fine then crashed on first `update()` with a bare `AssertionError` (`_interpolate` used `assert isinstance(x, float)` as validation, stripped under `-O`). `Tween` was a value-equality `@dataclass`, so `TweenManager.remove(b)` removed an equal-but-different `a` — now `@dataclass(eq=False)`. `Animator.update()` advanced ≤1 frame per call (`if`, not `while`) so a lag spike dropped frames and drifted behind forever while `_current_time` grew unbounded — now O(1) catch-up. `AnimationStateMachine` re-fired `on_complete` + the transition check every frame a non-looping clip sat finished (callback storm for any terminal state) — fixed with a `_completion_handled` latch reset on transition. `AnimationClip` gained `__post_init__` validation (`frame_rate<=0` → `ZeroDivisionError`, `frames=[]` → `IndexError`). `TransitionCondition.IMMEDIATE` was declared but `_check_transitions()` had no branch — now honoured (fires on entry). `Scene.update_animations()` removed: its docstring told games to call it from `scene.update()`, but `AnimationSystem` has been auto-registered on the scene's `SystemManager` since wayfinder ticket 24, so following the docs double-updated every animation; it had no real callers. Recurring shapes: "assert as runtime validation", "identity vs value" (the gamepad-index shape), "one advance per frame" (the audio/application shape), the `on_complete` retrigger storm (audio F5), "no `__post_init__`" (audio F6 / physics config), "declared and wired to nothing" (`IMMEDIATE`), and uniform test setup — every tween test used float `0.0→100.0`, every FSM test stepped `dt == 1/frame_rate` exactly and stopped updating on the completion frame. Left open: a single huge `dt` still resolves only one loop boundary per `Tween.update()` (catches up over later frames, documented); `Color` tweening unsupported (documented); `_allow_methods = True` on both FSM components stays CC-6. |
| `pyguara/audio` | 2026-09-08 | One slice. **SFX playback was dead end to end**: the pygame backend called `Channel.get_id()` (pygame-ce has `Channel.id`), so every real `play_sfx`/`play_sfx_at_position` raised, was swallowed by `except (AttributeError, Exception)`, and returned `None` while the sound played on untracked — hidden because all 107 audio tests `patch("pygame.mixer")` wholesale. Loudness/pan were set on the ResourceManager-shared `Sound` not the channel, so concurrent plays of one clip corrupted each other and recycled channels kept the last sound's hard pan. `AudioSourceSystem` never detected a finished one-shot — `is_playing` lied forever, a source could not be replayed, and stale channel ids kept receiving spatial mix updates meant for whatever reused the channel; fixed with a new `IAudioSystem.is_channel_active()` reconciled each frame, plus an `_auto_played` latch (auto_play is "on awake", not loop — the fix exposed a retrigger storm). `SpatialAudioConfig` gained `__post_init__` validation (0 → `ZeroDivisionError` in `calculate_pan`; inverted range → attenuation cliff). Added `IAudioSystem.shutdown()` (idempotent `pygame.mixer.quit()`), wired into `Application.shutdown()`. Recurring shapes: "mock away the unit under test" (the whole `test_audio.py`) and "declared and wired to nothing" (`AudioManager._active_channels`, removed). Left open: bus/master volume changes don't re-mix already-playing non-spatial SFX (mixer limitation, documented). |
| `pyguara/input` | 2026-09-08 | One slice. `InputContext` was inert end to end — `InputManager._context` was pinned to `GAMEPLAY` with no setter, so three of four contexts and the `context=` arg on `bind_input()` could never fire; `test_context_switching` only passed by poking the private attr. Gamepad identity was the pygame device index, not the SDL instance id, so unplugging a non-last pad flagged the wrong one and kept a stale handle. `rebind(SWAP)` returned `SWAPPED` when the action had no prior key and it had really just unbound the other; `RebindResult.CONFLICT` was unreachable (ERROR raises). `OnAction`/`OnRawKey`/`OnMouse` events were frozen at `timestamp=0.0` — the idiom the `events` audit already killed. Recurring shapes again: "declared and wired to nothing" (contexts, the whole rebind/serialize surface has no `InputManager` entry point — added `bindings`) and uniform test setup (every gamepad test unplugged only the last pad; every swap test pre-bound both actions). Phase B also found the softer test smells — assertions on `_controllers` privates, `assert x is not None` on a list literal, `assert not raises` as the only check — and rewrote them. `input/manager.py` stays a CC-11 / issue #9 offender (raw pygame events) — parked. |
| `pyguara/physics` | 2026-09-08 | Judged as *game* physics. Four slices: substepping stops ordinary-speed tunnelling (PR #24); characters moved off dynamic bodies onto `CharacterMover`/`CharacterBody` with full parity — knockback, platform riding, crate pushing — on Celeste's integer+remainder model (PR #25); trigger volumes and the entire `Joint` ECS layer were both inert end to end and were rebuilt and tested (PR #27); the close added five spatial queries, body sleeping, kept `substeps` at 4 on benchmark evidence, and froze `PhysicsMaterial`. Recurring shape: "declared and wired to nothing" (`fixed_rotation`, `gravity_scale`, the `return False` collision contract, `Joint`, `TriggerVolume`) and uniform test setup (every test a slow body already at rest). |
| `pyguara/graphics` | 2026-09-06 | Audited in five slices: window boundary, components, backends, pipeline, assets. Window reported the requested size not the granted one; `Box`/`Circle` were hard-wired to pygame; the pygame stubs had drifted; a zero-height window produced a 450px viewport; nine-patch produced negative source rects. PRs #12, #14, #15, #17, #18. |
| `pyguara/systems` | 2026-09-06 | Fixed every game system starting up uninitialised (`initialize()` runs before `on_enter()`), an `unregister()` testing truthiness rather than `None`, and silent duplicate registration keys. PR #11. |
| `pyguara/scene` | 2026-09-06 | Fixed `switch_to()` abandoning every stacked scene, unguarded re-entrancy during transitions, and a `pop_scene()` that stranded the scene it returned to. PR #10. |
| `pyguara/application` | 2026-09-06 | Fixed an event budget spent per fixed step (15x per lagged frame), a `shutdown()` that skipped everything after the first failure, and three lifecycle events with no publisher. PR #8. |
| `pyguara/config` | 2026-09-06 | Fixed `Color` not surviving a save/load round trip (a second-launch crash), `fixed_dt` dividing by zero unvalidated, and `update_setting` accepting wrong types and out-of-range values. PR #7. |
| `pyguara/log` | 2026-09-06 | Fixed source attribution (every record reported `logger.py:138`), a `shutdown()` that did not stop logging, handler clobbering on a process-global logger, and a docs page describing a nonexistent API. PR #5. |
| `pyguara/di` | 2026-09-06 | Fixed a missing lock in `DIScope.get()` that fabricated circular dependencies under concurrency (140/160 resolutions), plus captive lifetimes, dead-scope resolution, silent re-registration and varargs injection. PR #4. |
| `pyguara/events` | 2026-09-06 | Broke a latent `log` <-> `events` import cycle, fixed a timestamp sentinel that made 0.0 inexpressible, brought filter errors under the error strategy, and memoised handler resolution (5.7us -> 3.1us per dispatch). PR #3. |
| `pyguara/common` | 2026-09-06 | Fixed `Transform.up` pointing down, an unguarded parent cycle and a falsy-`Vector2` default; renamed `Vector2.rotate` to `rotate_degrees`; wrote the first tests for `Vector2` and `Transform`. PR #2. |
| `pyguara/ecs` | 2026-09-06 | Fixed two silent query bugs (`add_entity()` bypassing the query cache; dead-entity resurrection), replaced the private removal hook with a subscribe/unsubscribe API, and modernised the module. PR #1. |

---

## Tracked as GitHub issues

Concerns that outgrew this file, or that need a decision rather than a fix:

| Issue | Subject |
| --- | --- |
| [#9](https://github.com/Wedeueis/pyguara/issues/9) | pygame reaches into the backend-agnostic core (CC-11) — nine non-backend files across five subsystems |
| [#16](https://github.com/Wedeueis/pyguara/issues/16) | `IFramebuffer`/`IRenderPass` not `runtime_checkable`; `IRenderPass` vs `BaseRenderPass(ABC)` overlap |
| [#19](https://github.com/Wedeueis/pyguara/issues/19) | ~2,700 lines of GPU-dependent graphics code are read-audited only, with no headless GL coverage |
| [#23](https://github.com/Wedeueis/pyguara/issues/23) | `camera.rotation` is applied by `Camera2D.world_to_screen` but ignored by the render path; three definitions of world-to-screen disagree |
| [#28](https://github.com/Wedeueis/pyguara/issues/28) | Roguelike core — framework-level subsystems the target genre needs (combat spine, seeded RNG service, stat/modifier system, projectile layer, procgen, tilemap, run/meta save split, flow-field pathfinding, hit-stop, combat juice, local co-op input) |
| [#30](https://github.com/Wedeueis/pyguara/issues/30) | `docs/guides/*` physics references have drifted (pre-`CharacterMover`; style guide calls a nonexistent `get_body`) — a `docs/guides` pass, out of scope for the physics subsystem slice |
| [#37](https://github.com/Wedeueis/pyguara/issues/37) | Animation authoring layer — the `pyguara/animation` audit found the primitives correct but barely wired to the ECS/game layer: no tween↔ECS integration, no sequences/timelines, no directional (8-way) animation, no animation frame events, no `Color` tween, no `Animator.playback_speed`. Time-scale/hit-stop is owned by #28 |
| [#40](https://github.com/Wedeueis/pyguara/issues/40) | Resources capability gaps (from the `pyguara/resources` audit) — no async / batch / `preload` loading (every load blocks the main thread), hot-reload has a `reload()` primitive but nothing watches the filesystem and stale holders keep the old instance, no path/context on a missing-or-broken file, no asset dependency graph |
| [#43](https://github.com/Wedeueis/pyguara/issues/43) | Persistence production layer — the `pyguara/persistence` audit (Phase D) found the subsystem defect-free but thin for a shipped game: no backup / prior-version retention, no save-menu API (`list_saves`, cheap metadata-header read, `delete`/`exists` facade), `FileStorageBackend` rooted at a CWD-relative dir not the OS user-data dir. Envelope `format_version` and run/meta split (#28) noted separately |

---

### Out-of-band: render pipeline snapshots (PR #22)

Not a queued subsystem. Adding Syrupy snapshots of the backend call stream
`RenderSystem.flush()` produces turned up a live defect on the first run.

**Found:** the batcher added `viewport.position` to `viewport.center_vec`,
which is already absolute — the viewport origin was counted twice, displacing
everything by it. Invisible at fullscreen (origin `(0,0)`), so 1514 tests
passed over it. Pre-existing from `bb5fa03`, unchanged at `35ed7fa`.

**Latent, not shipped:** nothing produces an offset viewport.
`RenderSystem.flush()` has one call site passing none, `WorldPass._viewport`
is never set, `Viewport.create_best_fit` has no production callers, and no
config option letterboxes.

**The deeper defect:** `particles.py` already had the transform right. Two
copies of one formula had drifted apart, and under a letterboxed viewport
they disagreed by the viewport origin — which would have presented as
particles detaching from the sprites emitting them, not as a uniform shift.
Both now call `Camera2D.screen_offset()`; a test pins them together.

**Pattern, third instance:** the recurring blind spot here is uniform setup,
not missing coverage. Every existing viewport test used a fullscreen
viewport, exactly as every query-cache test used `create_entity()` and every
config test mocked the filesystem.

**Left open:** issue #23, camera rotation.

## Cross-Cutting Concerns

Architectural issues that span subsystems. Do **not** fix these inside a
single-subsystem iteration; schedule a dedicated pass.

### CC-1 — RESOLVED 2026-09-06 — Ruff `target-version` was `py39`
`pyproject.toml` pins `target-version = "py39"` while `requires-python` is
3.12+. Ruff therefore refuses modernisation fixes engine-wide, which is the
root cause of the legacy `typing.Dict`/`Optional[X]` style found in every
module audited so far. **Fix:** bump to `py312` and enable the `UP`
(pyupgrade), `B` (bugbear) and `D` (pydocstyle, `convention = "google"`) rule
sets in one deliberate formatting commit, so per-subsystem diffs stay
reviewable.
Bumped to `py312` and enabled `UP`, `B`, `I`, `SIM`. 1455 findings fixed
mechanically, the rest by hand. Surfaced one real defect: a mutable `Color`
shared as a default argument in `WorldPass`.
*Discovered in:* `ecs`. *Status:* **resolved**.

### CC-2 — RESOLVED 2026-09-06 — Lint rule set was minimal
No pydocstyle, no bugbear, no pyupgrade, no complexity ceiling. Google-style
docstrings (mandated by this refactor) are therefore unenforced and will drift
straight back.
Resolved with CC-1. Ruff's `D` rules stay off deliberately: pydocstyle runs as
its own hook, and two tools disagreeing about docstring style is worse than one
enforcing it. That hook was also found to be mis-scoped -- it used a `match:`
key pre-commit does not recognise, so it had been linting the whole repository
instead of `pyguara/`.
*Discovered in:* `ecs`. *Status:* **resolved**.

### CC-3 — Internal ticket ids leak into public docstrings
Strings like `P1-008` appear in user-facing API docstrings (`EntityManager
.register_cached_query`, `QueryCache` module header) and in test module
docstrings. Tracker ids are not documentation. **Fix:** sweep
`grep -rn "P[0-9]-[0-9]" pyguara/ tests/` once the per-subsystem passes are
done.
*Discovered in:* `ecs` (removed there). *Status:* open elsewhere.

### CC-4 — Unverifiable benchmark numbers embedded in docstrings
Hard-coded claims ("~8ms for 10,000 entities", "8x faster") sit in docstrings
with no benchmark backing them in CI. They are untestable and rot silently.
**Fix:** move to `.benchmarks/` with an actual `pytest-benchmark` run, and
reference the benchmark rather than restating a number.
*Discovered in:* `ecs` (removed there). *Status:* open elsewhere.

### CC-5 — `EntityManager` internals reached into from outside the package
**Removal hook: RESOLVED (2026-09-06).** `_on_entity_removed` was a single
callback slot assigned directly by `pyguara/scene/base.py`, so any second
observer would have silently displaced the scene's `EntityDestroyed` dispatch.
Replaced with `subscribe_entity_removed()` / `unsubscribe_entity_removed()`,
which fan out to every subscriber, dedupe by equality (so a bound method
subscribed twice notifies once), and tolerate unsubscription during
notification. `Scene`, `tests/test_ecs.py` and `tests/test_physics.py` migrated;
no references to the private attribute remain anywhere in the tree.

**Still open:** `Entity._components` and `_on_component_added` are read across
module boundaries — by `EntityManager` itself (acceptable, same package) and by
serialisation and prefab code (not). Audit when `persistence` and `prefabs` come
up; the likely fix is a public read-only components view.
*Discovered in:* `ecs`. *Status:* partially resolved.

### CC-6 — Component data-purity is advisory, not enforced
`BaseComponent` only *warns* on logic methods; `StrictComponent` errors but is
opt-in and, at the time of the `ecs` audit, had no adopters outside tests.
**Named offender:** `common.Transform` sets `_allow_methods = True` and carries
the whole parent hierarchy, world-transform caching and coordinate conversion
(~330 lines). It is the largest violation in the engine and the one a
`TransformSystem` would have to absorb; every other subsystem touches it, so it
is deliberately not attempted piecemeal. **Fix:** once `physics`, `ui` and `ai`
are audited and the true extent is known, migrate the tree to `StrictComponent`
and consider making it the default.
*Discovered in:* `ecs`; offender identified in `common`. *Status:* parked.

### CC-10 — RESOLVED 2026-09-06 — Documentation described APIs that do not exist
`docs/core/logging.md` documented `pyguara.log.config.setup_logging()` and
`pyguara.log.config.get_logger()`. Neither the module nor the function exists
anywhere in the tree; every code sample on the page raised
`ModuleNotFoundError`. Nothing catches this, because docs are never executed.
**Fix:** enable `pytest --doctest-glob='*.md'` over `docs/`, or add a smoke
test that imports every symbol the docs reference. Until then, treat "verify
the documented API actually exists" as an explicit Phase C step in every
iteration.
`tests/test_docs_api.py` now extracts every `pyguara...` import and backticked
dotted reference from the Markdown under `docs/` and asserts it resolves. It
immediately found two more: `docs/core/application.md` documented an entire
error hierarchy (`pyguara.error`, `EngineException`, `@safe_execute`, `@retry`)
that has never existed, and `PROJECT_STRUCTURE.md` referenced
`create_application_container` instead of `create_application`. Both fixed.
*Discovered in:* `log`. *Status:* **resolved**.

### CC-9 — RESOLVED 2026-09-06 — `ErrorHandlingStrategy` was defined twice
`pyguara/di/types.py` and `pyguara/events/types.py` each declare their own enum
of the same name with identical members (LOG / RAISE / IGNORE) and identical
semantics. They are not interchangeable -- `di.RAISE != events.RAISE` -- so
passing one where the other is expected fails a comparison silently rather than
loudly. **Fix:** hoist a single definition to a shared home once more
subsystems are audited and the full set of consumers is known; `di` must not
import `events` (see CC-8) so it cannot simply re-export.
Hoisted to a new top-level `pyguara/errors.py`, which imports nothing from the
engine and so cannot cycle. `di/types.py` and `events/types.py` re-export it, so
existing import paths keep working. `di.RAISE == events.RAISE` is now True.
*Discovered in:* `di`. *Status:* **resolved**.

### CC-11 — pygame reaches into the backend-agnostic core
**Tracked as GitHub issue #9.**
CLAUDE.md states the engine is backend-agnostic and that code should never
import pygame directly, but `Application` uses `pygame.time.Clock` for all
frame timing, compares against `pygame.QUIT`, calls `pygame.event.pump()` and
catches `pygame.error`. `SandboxApplication` uses `pygame.K_F1`-style constants
for its tool hotkeys. The ModernGL path therefore still depends on pygame for
timing and quit detection.
Not fixed in the `application` pass because the fix belongs on the other side
of the boundary: `Window.poll_events()` would have to yield engine events
rather than raw SDL ones, and a `Clock` protocol would have to join the
graphics protocols. **Fix:** take it with the `graphics` audit, so the protocol
and both backends move together. `WindowResizeEvent` is defined and never
dispatched for the same reason -- nothing detects the resize.
*Discovered in:* `application`. *Status:* parked until `graphics`.

### CC-8 — Package `__init__.py` files export nothing
Most subsystem packages have a docstring-only `__init__.py`, so callers reach
into submodules (`from pyguara.events.dispatcher import ...`). Beyond the
ergonomics, it actively hides import cycles: adding re-exports to
`events/__init__.py` immediately exposed a latent `log` <-> `events` deadlock
(fixed in that pass). Every package still lacking exports may be hiding the
same thing. **Fix:** add a curated `__all__` per package as each is audited,
and treat any cycle it reveals as a finding rather than a reason to revert.
*Discovered in:* `events`. *Status:* open.

### CC-7 — `x or default` used with falsy value types
`pymunk.Vec2d` defines `__bool__`, so `Vector2(0, 0)` is falsy. `Transform
.__init__` used `scale or Vector2(1, 1)`, which silently rewrote an explicitly
requested zero scale to unit scale. Fixed there, but the idiom is common and
the same trap applies to any zero vector, `Color(0,0,0,0)`, an empty `Rect`, or
`0.0` defaults. **Fix:** sweep `grep -rn "or Vector2(\\|or Color(" pyguara/` and
convert to explicit `is None` checks as each subsystem is audited.
*Discovered in:* `common`. *Status:* open.

---

## Iteration Log

### `pyguara/ai` — CLOSED 2026-09-08 (branch `refactor/ai-audit`)

One slice, ~2,100 lines: `ai/{fsm,blackboard,components,ai_system,steering,
steering_system,behavior_tree,navmesh}.py` and `ai/pathfinding/{core,astar,
grid}.py`. Every defect reproduced with a probe against the real code
first. `games/protocolo_bandeira` is a *consumer* (its `EnemyAISystem`
hand-rolls an `AIContext`-shaped object) and confirmed F2 from the outside;
it was not modified.

**Verification:** 1799 tests pass (up from 1770; +29 across a rewritten
`test_ai.py`, a new `test_steering.py`, and additions to
`test_behavior_tree.py` / `test_navmesh.py` / `test_pathfinding.py`).
`ruff check .` clean; `ruff format --check` clean; `mypy pyguara` clean
across 226 files; `mkdocs build --strict` exit 0; `test_docs_api.py` (54)
passes.

Two upfront decisions put to the user. **F2 fix depth:** a contained
`WaitNode`-only patch, a lightweight proxy, or a real context object — the
user took the **`AIContext`** (entity + dt + blackboard), so `AISystem` now
constructs one per frame and hands it to `tree.tick()`; this changes what
leaf callables receive under `AISystem` (bare `Entity` → `AIContext`), a
breaking change that pre-alpha and the fact that `AISystem` was unusable for
timed nodes make acceptable. **F3 scope:** validate-only, wire pursuit/evade,
or a full enum — the user took the **full enum**: `SteeringBehaviorType`
(`str, Enum`) with `__post_init__` coercion+validation, all six behaviors
wired, `SteeringAgent.target_velocity` added for the moving-target pair.

**F1 — `world_to_grid_coords()` truncated toward zero.** `int((p.x -
offset.x) / cell_size)` rounds toward zero, not down. Probe: `cell_size=32`,
world `-1` → grid `0` (should be `-1`), `-33` → `-1` (should be `-2`); with
`offset=(100,100)`, world `(90,90)` → `(0,0)` (should be `(-1,-1)`). Any
centred or camera-relative grid, and the entire quadrant left of / above the
origin, was mis-resolved — a sign flip near the axes. Now `math.floor`.
`TestCoordinateConversion` had used only positive coords and positive
offsets — uniform setup, third instance of the pattern this audit keeps
hitting.

**F2 — `AISystem` never threaded `dt` into the tree.** `AISystem.update(dt)`
called `ai.behavior_tree.tick(entity)`. `WaitNode.tick` does
`getattr(context, "dt", <fallback>)`; an `Entity` has no `dt`, so every
`WaitNode` (and any custom timing node) advanced by a hardcoded `1/60` per
*tick*, not per real second. Probe: `WaitNode(1.0)` driven by `AISystem`
completed after ~2.08 s at 30 fps and ~3.47 s at 144 fps. `protocolo_bandeira`
already worked around this by building its own context object carrying `dt`.
Fix: new `pyguara/ai/context.py::AIContext` (`entity`, `dt`, `blackboard`);
`AISystem` builds one per component per frame. `WaitNode`'s literal `0.016`
became a named `_WAIT_FALLBACK_DT` for the bare-object case. "Declared and
wired to nothing" / "hardcoded dt".

**F3 — `pursuit`/`evade` were implemented but unreachable; unknown behavior
was silent.** `SteeringSystem._calculate_steering` branched only on
`seek/arrive/flee/wander` (lower-cased string compare).
`SteeringBehavior.pursuit()` / `.evade()` — the only behaviors that lead a
moving target — had no branch, and `behavior="chase"` (a typo) or
`"pursuit"` produced `Vector2(0,0)` every frame with no diagnostic. Probe:
`behavior="pursuit"` with a target set → agent never moved. Fix per the
user's choice: `SteeringBehaviorType(str, Enum)` with the six members;
`SteeringAgent.__post_init__` does `self.behavior =
SteeringBehaviorType(self.behavior)` (raises `ValueError` on an unknown
name); `_calculate_steering` dispatches on the enum with all six wired;
`SteeringAgent.target_velocity: Vector2` added, refreshed by the caller
alongside `target`, consumed by pursuit/evade.

**F7 — `arrive` overshot and orbited the target forever.** Probe: target at
x=300, `max_speed=200`, `slowing_radius=100` — the agent reached x≈357 then
swung 306 → 285 → 288 → … indefinitely, never settling.
`SteeringBehavior.arrive`'s `if distance < 0.1: return -current_velocity`
returns a *velocity* as a *force* and only fires within 0.1 px (never hit);
the real brake is `desired - current_velocity` scaled by `dt/mass`, a weak
proportional term the `max_force` cap plus Euler integration make unstable.
Fix: `SteeringSystem.update` now enforces the arrive ramp on the resulting
velocity — cap speed to `max_speed * distance / slowing_radius` inside the
radius, snap to rest within `_ARRIVE_STOP_DISTANCE = 1.0`. A system-side
clamp, not a redesign of the force model all behaviors share.

**F4 — generic `AStarPathfinder` crashed on a priority tie.** `frontier`
held `(priority, node)`; on equal priorities heapq compares the second
element, and `core.Node` is bound only to `Hashable`. Probe: a 4-node
diamond graph with a zero heuristic (so both mid nodes get priority 1.0) and
nodes that are hashable but define no `__lt__` → `TypeError: '<' not
supported between instances of 'Cell' and 'Cell'`. Latent for the shipped
`GridGraph` (tuple nodes are orderable) but ties are the normal case. Fix:
`itertools.count()` tie-breaker — `(priority, next(counter), node)` — so the
node is never compared. Applied the same to `NavMeshPathfinder.
_find_polygon_path` (int nodes today, same latent shape).

**F5 — `NavMesh.remove_polygon()` left dangling neighbor ids.** It deleted
the polygon and its edges but not the id from other polygons' `neighbors`
lists. Probe: three rects in a row, `build_connections()`, `remove_polygon(2)`
→ `get_neighbors(1)` still `[0, 2]`. `NavMeshPathfinder` defends
(`get_polygon → None → continue`) but `get_neighbors` is public — a debug
overlay or a third-party pathfinder hits the `None`. Fix: prune every
remaining `neighbors` list in `remove_polygon`.

**F6 — FSM silent failures.** `set_initial_state("Typo")` left the machine
permanently `None` with no diagnostic; a state whose `update()` returns an
unregistered name was silently ignored. Probes confirmed both. Fix: both
paths `logger.warning(...)` (matching how `di`/`systems`/`input` handle
unknown keys post-audit); `set_initial_state` also now calls the previous
state's `on_exit()` if called a second time.

**Phase B verdict.** The BT and pathfinding/navmesh suites are substantial
(797 / 589 / 670 lines) and load-bearing — node-status truth tables,
corner-cut prevention, A* around obstacles. But `test_ai.py` was 54 lines
(only `Blackboard` + one FSM transition, asserting on `fsm._current_state`),
there was **no `test_steering.py` at all** despite `SteeringSystem` being
auto-registered on every scene, and no test exercised `AISystem`. Uniform
setup hid F1 (`TestCoordinateConversion`: positive coords + positive offsets
only) and `test_wait_completes` had `# 0.016 * 4 = 0.064 > 0.05` baked into
its comment — a test pinning the bug. Added: negative/offset
`world_to_grid_coords` cases; an A* test over a non-orderable-node graph;
`remove_polygon` neighbor-pruning; `WaitNode`-honours-real-`dt`; a rewritten
`test_ai.py` (FSM warnings, `AISystem`/`AIContext` integration incl. the
frame-rate-independence regression); a new `test_steering.py` (all six
behaviors reachable, arrive settles and does not re-oscillate, enum
validation, wander-state persistence + cleanup, Navigator path-follow).

**Phase D — capability gaps.** Defect-free but thin for a shipped game:

- *BT/FSM authoring* (**propose new issue**, sibling of #37/#40/#43):
  `SequenceNode`/`SelectorNode` have memory and there is no *reactive*
  variant, so a guard `ConditionNode` at the front of a sequence is not
  re-checked once the sequence advances past it — the "attack while visible,
  else patrol" pattern silently keeps attacking; `ParallelNode` re-ticks
  already-completed children (no latching, re-fires one-shots); FSM
  transitions are only `update()`-returns-a-name (no `add_transition(from,
  to, predicate)` table, no event-driven transitions); every BT leaf is a
  hand-written closure (no `BlackboardCondition` / `SetBlackboard` /
  cooldown / random-selector nodes).
- *Navmesh* (**parked** — needs a real consumer; flow-field pathfinding is
  already #28's): polygons must share a *full* edge (no partial-edge portals
  / T-junctions), `NavMeshPathfinder` returns polygon-*centre* waypoints (no
  funnel string-pulling — paths zig-zag), and nothing *generates* a mesh
  (you supply convex polygons by hand).
- *Steering vs. physics* (**parked** for the top-down `CharacterMover`
  slice): `SteeringSystem` writes `transform.position` directly, so agents
  don't collide with solids, don't separate from each other, and
  double-integrate if they also carry a body.
- *`_wander_targets` eviction* (**left-open note**): cleared only on scene
  exit, not per destroyed entity — a scene that spawns/despawns many
  wanderers leaks entries keyed by dead entity ids. The scene already has
  `subscribe_entity_removed`; wiring it in is small.

**Left open.** `WaitNode` keeps a `getattr(context, "dt",
_WAIT_FALLBACK_DT)` for trees ticked with a bare object. The arrive fix is a
velocity clamp, not a rework of the `dt`-scaled force/integration model.
`NavMeshPolygon.contains_point` references `xinters` before assignment on a
branch the outer `y > min / y <= max` guards make unreachable for a
horizontal edge — fragile, not touched.

### `pyguara/persistence` — CLOSED 2026-09-08 (branch `refactor/persistence-audit`)

One slice, ~970 lines: `persistence/{manager,storage,serializer,migration,
types}.py`. Every defect reproduced with a probe against the real code
first. `pyguara/scene/serializer.py` is a *consumer* (goes through
`save_data`/`load_data`) and was audited under `pyguara/scene`; only its
test's in-memory backend was touched here, for the protocol change.

**Verification:** 1770 tests pass (up from 1735; +35 across
`test_persistence.py` — rewritten — `test_migration.py`, and
`tests/integration/test_persistence_backend.py` — rewritten). `ruff check .`
clean; `ruff format --check` clean; `mypy pyguara` clean across 225 files;
`mkdocs build --strict` exit 0; `test_docs_api.py` (54) passes. Both commits
verified standalone in a detached worktree (`git worktree add --detach`,
`uv sync --extra dev`): code commit 1768 / 1768, docs commit 1770 / 1770.

One upfront decision put to the user: F3's fix depth. Options were a
contained single-file fix in the backend, a manager-layer envelope, or
leave-and-document; the user asked which was more systemic and took the
**envelope** — the `metadata` argument on `StorageBackend` is what forced
every backend to keep two things consistent, and it is purely a
`PersistenceManager` concern. `compress` and `MSGPACK` the user chose to
implement rather than delete.

**F1 — `save_data()` ignored `storage.save()`'s return value.** The
`StorageBackend` protocol returns `bool`; `FileStorageBackend.save` returns
`False` on `OSError` rather than raising. `save_data` called
`self.storage.save(...)` and discarded the result, logged "Successfully
saved" and returned `True`. Probe: a backend whose `save` returns `False`
→ `save_data` returned `True`. "Guard that returns a wrong answer." Now the
result is checked; `save_data` returns `False` and logs the rejection.

**F2 — `FileStorageBackend._get_paths` collapsed distinct keys.** The key
was sanitised by *deleting* every character that was not alphanumeric,
`_` or `-`. Probe: `save("slot 1", …)`, `save("slot/1", …)`, `save("slot.1",
…)` all wrote `slot1.dat`; the last write won and the first two were gone.
An all-punctuation key → empty stem → literal `.dat`/`.meta` files, and
every punctuation-only key aliased together. Exactly the resources F2
shape ("silently resolved a stem collision to whichever file the walk hit
last"). Now `FileStorageBackend` raises `ValueError` for any key that is
empty or contains a character outside `[A-Za-z0-9_-]` — a save key is
developer-controlled, so reject it loudly (the `config` precedent) rather
than pick a wrong file.

**F3 — the data file and the meta file were replaced by two independent
`os.replace` calls.** `storage.save()` wrote `{key}.dat` atomically, then
`{key}.meta` atomically. `load()`'s comment: "Check both files exist
(atomic save ensures both or neither)" — false; two replaces are not
jointly atomic. A crash between them leaves new data + a stale-checksum
meta, and `load_data(verify_integrity=True)` then returns `None` for a save
whose bytes are perfectly intact. Probe: desync the two files → `load_data`
→ `None`. Fixed by the envelope: `PersistenceManager._frame` writes a
one-line compact-JSON metadata header, a `\n`, then the payload bytes;
`_unframe` splits on the first `\n`. `StorageBackend` becomes
`save(key, blob) -> bool` / `load(key) -> bytes | None` (no `metadata`
param). `FileStorageBackend` writes one `{key}.save` file with the existing
temp-then-`os.replace`, plus a directory `fsync` after the rename and an
orphaned-`.tmp_*` sweep on init. **Breaking on-disk format change** —
pre-alpha, no existing saves, no migration path provided.

**F4 — `compress` was a documented no-op.** `save_data(…, compress=True)`
did nothing; the docstring said "Not implemented in this snippet". Probe:
`compress=True` and `compress=False` produced identical file sizes. Now
`gzip.compress` runs on the payload when set, `compressed: true` goes in
the header, and `load_data` reverses it transparently. The checksum covers
the payload as written (post-compression).

**F5 — `SerializationFormat.MSGPACK` had no implementation.**
`serializer.serialize(…, MSGPACK)` raised `ValueError: Unsupported
serialization format`, though `msgpack>=1.1.2` is a declared dependency and
a PyInstaller hidden-import, and the package docstring advertises
"MessagePack". Implemented: `msgpack.packb(prepare_for_json(data),
use_bin_type=True)` and `msgpack.unpackb(data, object_hook=game_object_hook,
raw=False, strict_map_key=False)` — the same engine-value-type path JSON
uses. Exposed through a new `fmt: SerializationFormat` argument on
`save_data` (it previously hard-coded JSON, so the format was unreachable
from the facade). `msgpack.*` added to the mypy `ignore_missing_imports`
overrides.

**Minor.** `SaveMetadata` was constructed then hand-copied field by field
into a dict (`# (In a real scenario, use asdict)`) and never reconstructed
on load; now it carries `format`/`compressed`, is serialised with
`asdict()`, takes the engine version from `importlib.metadata.version`
(was hard-coded `"1.0.0"` while pyproject is `0.4.0`), and uses a
timezone-aware UTC timestamp. `FileStorageBackend.__init__` now
`os.makedirs(..., exist_ok=True)` (was check-then-create, a TOCTOU race).
`delete()` returns whether a file was actually removed and guards
`os.remove`.

**Migration — audited, largely sound.** Probes for a version overshoot, an
infinite `get_migration_path` loop, and a mid-chain gap all came back
negative: `register()`'s `to_version <= current_version` guard plus the
"version not in `_migrations` → raise" plus `to_version > from_version`
(strictly increasing loop variable) compose to a terminating, gap-free
walk, and downgrades are already rejected. Added only construction-time
guards (`Migration.from_version >= 1`, `MigrationManager.current_version
>= 1` — the "no `__post_init__` validation" recurring theme) and
`@dataclass(eq=False)` on `MigrationRegistry` (two registries with
equivalent migrations compared `==` — the `Tween` identity-vs-value shape
from the animation audit; low stakes here, fixed for consistency). The
in-place mutate-and-return contract of migration functions is *documented*
(the `@migration` docstring example does `data.pop`) and left as is; a test
now pins it.

**Phase B — verdict on the 27 existing tests (+35; `test_persistence.py`
and `test_persistence_backend.py` rewritten, `test_migration.py` extended).**

*`test_migration.py` (24, +7) — the strong file.* Real assertions on real
return values through the public surface: `Migration` validation, register
/ path / single- and multi-step `migrate` / decorator / registry. Good
coverage of the ordering guards. **Uniform version setup** was the blind
spot — every `Migration` used small positive ints from 1, so the F-guards
(version 0 / negative) had no test, and `MigrationRegistry` equality was
never probed. Added: the `>= 1` rejections, the identity-equality
guarantee, and a test pinning the mutate-and-return chain threading one
dict.

*`test_persistence.py` (3 → ~12) — thin, rewritten.* Only `Serializer`
JSON round-trips for `Vector2`/`Color`/one dataclass. No msgpack, no
BINARY, no `PersistenceManager`, no compression, no integrity, no envelope.
Rewrote as a `Serializer` unit file: JSON + MSGPACK (parametrised over
`Vector2`/`Color`/`Rect`/nested) + BINARY round-trips, msgpack-is-smaller,
default-format selection.

*`tests/integration/test_persistence_backend.py` (4 → ~20) — rewritten.*
Decent shape (real `tmp_path`, real files) but pinned to the old two-file
`.dat`/`.meta` protocol and the 3-arg `save`, and every key was already
filesystem-safe (`save1`, `slot_a`, `autosave`) so F2 was unreachable.
Rewrote for the blob protocol: save/load/overwrite, the key-rejection
parametrisation (space, slash, dot, `..`, NUL, `:` , `\`), `list_keys` /
`delete` semantics, `makedirs` idempotence, the temp-file sweep; then
`PersistenceManager` end to end — envelope layout, integrity failure →
`None` (and `verify_integrity=False` surfacing the tampered value), the F1
backend-failure → `False`, gzip round-trip + size, msgpack via `fmt=`, and
migrate-on-load.

**Phase C.** `pyguara/persistence` had **no docs page at all** (the
resources iteration's Phase C note anticipated this: "gets its own page").
Wrote `docs/systems/persistence.md` in the resources-page voice:
`save_data`/`load_data` (keys, `fmt`, `compress`, `save_version`), the
single-blob on-disk format + its MD5 checksum, the `StorageBackend`
protocol and `FileStorageBackend`'s key rule, and the migration pipeline
(registration, contiguous chain, load-time application, no downgrade,
`MigrationError`). Added to the mkdocs nav; `test_docs_api.py` picks up the
new backticked references (52 → 54) and they resolve. Notes the
`BINARY`/pickle "trusted files only" caveat.

**Phase D — capability gaps.** The subsystem is defect-free after this
slice but thin for a shipped game, especially a permadeath roguelike (#28).
The first three below are grouped into **#43** ("persistence production
layer", sibling of #37).

- **Backup / prior-version retention** — *#43.* One `.save` file per key;
  the atomic write stops a torn write but not a valid save of corrupt
  state, bit-rot, or a bad migration, and there is no fallback copy. Cheap
  (`{key}.save.bak` + fall back on integrity failure) and high-value;
  grouped with the save-UI gap rather than widening this slice.
- **Save-menu support on the manager** — *#43.* No `list_saves()`, no way
  to read a slot's metadata header without deserializing the whole
  payload, no `delete`/`exists` facade (callers reach into `.storage`). Any
  load-game screen needs these.
- **User-data-dir backend** — *#43.* `FileStorageBackend`'s
  `base_path="saves"` is CWD-relative; a shipped game needs the OS
  user-data dir (`platformdirs`).
- **Envelope `format_version` in the header** — *parked, small.* The header
  has `save_version` (game schema) and `version` (engine) but nothing
  identifying the container format; this slice changed that format with no
  detection field. Add on the next persistence touch.
- **Run vs. meta save split** — *owned by #28.* The namespaced-store /
  `SaveProfile` primitive belongs here; the policy is roguelike-core's.
- **Async / non-blocking save**, **tamper resistance (HMAC vs.
  user-editable)** — *parked, need a decision / their own slice.*

**Left open.** `save_data` records the payload `fmt` but the *metadata*
header is always JSON — deliberate, it stays greppable. `BINARY`/pickle
load is unauthenticated (an MD5 the attacker can recompute is no defence);
documented as trusted-input-only, a signing scheme is its own slice. The
missing `PersistenceManager` `delete`/`list`/`exists` facade moved up into
Phase D (#43). No lock on anything, but persistence has no concurrent
caller. Mypy's `python_version = "3.10"` vs `requires-python`
3.12 makes ruff's UP017 (`datetime.UTC`) and mypy disagree — one
`# noqa: UP017`; worth a CC if it recurs.

### `pyguara/resources` — CLOSED 2026-09-08 (branch `refactor/resources-audit`)

One slice, ~1,100 lines: `resources/{manager,meta,loader,types,data,
exceptions}.py` + `resources/loaders/data_loader.py`. Hot reload as a
*mechanism* lives downstream in `pyguara/dev` (Tier 4); this slice covered
the reload primitive the ResourceManager owes it. Every defect reproduced
with a probe against the real code first.

**Verification:** 1735 tests pass (up from 1714; +21 across
`test_resources.py` — rewritten — `test_meta.py`, `test_audio.py`,
`test_graphics_spritesheet.py`). `ruff check .` clean; `ruff format --check`
clean; `mypy pyguara` clean across 225 files; `mkdocs build --strict`
exit 0; `test_docs_api.py` (52) passes. Both commits verified standalone in
a detached worktree (`git worktree add --detach`, `uv sync --extra dev`):
1735 / 1735.

Two upfront decisions put to the user (both shape the whole PR): F1 → "fix
the model + add `reload()`"; F4 → "wire it up in this slice".

**F1 — the reference-counting lifecycle was internally inconsistent and
wired to nothing.** `load()` auto-incremented the count on *every* call,
including cache hits ("Auto-increment ref count on load"); `release()`
auto-unloaded at 0. So `unload_unused()` — documented "useful for cleanup
between scenes" — could never evict a resource anything still held (those
are at ≥1), and a properly released one was already gone (evicted at 0). It
was dead. Probe: `load()`×2 of one asset → count 2; `unload_unused()` → 0
freed. No engine code calls `acquire`/`release`/`unload`/`unload_unused`;
`AudioManager` / `AudioSourceSystem` call `load()` per play, so the
audio-clip count climbed monotonically forever. `Resource._ref_count`
(types.py) was a *third* counter, assigned once in `__init__` and read
nowhere. New model: `load()` is a pure cache-get — the resource enters the
cache **unpinned** (count 0) and a repeated `load()` does not change that;
`acquire()`/`release()` are the explicit balanced pin API; `release()`
below 0 raises `ValueError` ("you didn't acquire"); `unload_unused()` now
meaningfully sweeps everything unpinned. Removed `_ref_count`.
`test_reference_counting_basic` / `test_acquire_release` /
`test_release_zero_refcount_error` / `test_force_unload` / `test_cache_stats`
pinned the old model — rewritten.

**F2 — `index_directory()` silently resolved a stem collision to whichever
file the walk hit last.** `chars/hero.png` and `fx/hero.png` both claim the
bare name `hero`; the second overwrites the first with no warning (whereas
`register_loader` *does* warn on an extension clash). `load("hero", …)`
then returns the wrong file. Probe confirmed. Now: on collision the
ambiguous bare stem is removed from the index and a warning names both
paths; the unambiguous full-name keys (`hero.png`) are always kept, so the
caller resolves the clash with the full name or path.

**F3 — `MetaLoader` cached parsed meta by path with no invalidation, and
the cache swallowed the `expected_type` warning.** After a `.meta` changed
on disk, `load_meta()` kept returning the stale object (probe); the only
escape was the process-wide `clear_cache()`, which `ResourceManager` never
called — wrong in the hot-reload context this subsystem owns. And because
the cache key was the path alone, `load_meta(p)` then `load_meta(p,
OtherType)` served the cached object and skipped the type-mismatch warning
entirely. Now: each cache entry is pinned to the `.meta` file's mtime and
re-read when it changes; a deleted file drops the entry; the
`expected_type` check runs on *every* call including cache hits; and
`MetaLoader.invalidate(path)` forces a re-read (called by `reload()`).

**F5 — `DataResource` docstring claimed "hot-reloaded by the
ResourceManager"; no reload API existed.** Added `ResourceManager.reload()`:
re-runs the loader (re-reading the `.meta` sidecar via `invalidate()`),
type-checks the result against the previously cached instance, swaps it
into the cache in place, and preserves the reference count. Callers holding
the *old* instance keep that stale object — documented; this is what a
file-watching loop does. `_load_from_disk()` extracted so `load()` (miss)
and `reload()` share the loader+meta+type-check path.

**F4 — the `.meta` import pipeline was ~70% scaffolding.** `AudioMeta`
(fully built + tested — dB math, loop points) had **no consumer**:
`PygameSoundLoader` was not meta-aware. `SpritesheetMeta` had no consumer.
`GLTextureLoader` was not meta-aware and hardcoded `moderngl.LINEAR`,
ignoring `TextureMeta.get_filter_mode()` — the one setting the pygame
loader's own comment says GL is meant to honour. Wired end to end:
- `Resource.import_meta` — a settable slot carrying the resolved sidecar;
  `ResourceManager._load_from_disk()` attaches it after a meta-aware load
  so systems read import settings there instead of round-tripping the
  manager.
- `GLTextureLoader` is meta-aware and maps `filter` → `moderngl.NEAREST` /
  `LINEAR`. **Its default flips from LINEAR to NEAREST** — matching the
  pygame image path (the two backends silently disagreed) and
  `TextureMeta`'s own default for a pixel-art engine. Called out as an
  intentional backend-alignment change, not a silent regression.
- `PygameSoundLoader` is meta-aware; `load_mode: stream` warns (clips via
  the ResourceManager are always fully decoded — that is `play_music`'s
  job). The pygame audio backend multiplies `AudioMeta.volume_db`'s linear
  gain into the **channel** volume per play (never the shared `Sound` —
  respecting the audio audit's D2 fix).
- `SpriteSheet.slice_grid()` gained `margin` / `spacing` (grid maths now
  `margin + i*(frame+spacing)`) — `SpritesheetMeta.margin`/`spacing` were
  meaningless everywhere before — and raises on a non-positive frame size
  instead of `ZeroDivisionError`. `SpriteSheet.slice_from_meta(meta)` reads
  the geometry off a `SpritesheetMeta`.

**Minor.** `get_cache_stats() -> dict[str, Any]` with a real field spec in
the docstring (was bare `dict`). Portuguese comments in `manager.py` /
`audio/backends/pygame/loaders.py` translated. `load_atlas()` now
`acquire()`s its texture (under the new model `load()` no longer pins it,
so `unload_unused()` could pull it out from under the atlas). Curated
`__all__` on `pyguara.resources` and a new `loaders/__init__.py` (CC-8) —
no import cycle exposed.

**Phase B — verdict on the 69 existing tests (+21; `test_resources.py`
rewritten, nothing else wholesale).**

*`test_meta.py` (55, +5) — the strong file.* Real `tmp_path` files, real
save/load round-trips, all through the public surface — none of the
"mock away the filesystem" smell. Its one blind spot was **uniform
setup**: every test built a fresh `MetaLoader()`, so nothing reloaded the
same loader after a disk change and F3 was unreachable;
`test_load_meta_caches_result` actively pinned the stale behaviour as
intended. Added: reparse-on-mtime-change, drop-cache-on-delete,
`invalidate()`, and the cache-hit `expected_type` warning.

*`test_resources.py` (14 → rewritten, now ~40) — the weak file.* Decent
behavioural coverage of ref counting, but: every test built the manager
the same way (`MockLoader`, no real files); assertions read
`manager._reference_counts[...]` / `._cache` / `._path_index` (the
tracker's named private-state smell) rather than `get_cache_stats()`;
`test_indexing` mocked `Path.rglob` (mock-away-the-filesystem — so F2 was
unreachable); and `test_unload_unused` *hand-poked*
`manager._reference_counts["res1.mock"] = 0` and re-inserted into `_cache`
to manufacture a state the public API cannot produce — proving the method
works only against an impossible input. Rewritten: real `tmp_path` files, a
`MockLoader` that counts its own calls, assertions via `get_cache_stats()`,
and new coverage for the F1 lifecycle, `reload()` (incl. changed meta), the
F2 collision, and meta-aware load + `import_meta` attach through the
manager.

*`tests/test_graphics_spritesheet.py` (+3), `tests/test_audio.py` (+1).*
`SpriteSheet` margin/spacing + `slice_from_meta` + zero-dim rejection; the
`AudioMeta.volume_db` → channel gain path on the real dummy-driver mixer.
`GLTextureLoader`'s filter branch is not covered — no headless GL context
in CI (issue #19 shape: a real adapter, read-audited only).

**Phase C.** `docs/systems/resources.md` (15 lines) documented `load()`,
type safety, caching and indexing — and **nothing else**: no
reference-counting API, no `.meta` system (a module with its own test
file), no `reload()`, `load_atlas()` or `get_cache_stats()`. It also
carried a stale duplicated **"Audio System"** section (`systems/audio.md`
owns that since the audio audit) and a **"Persistence"** section belonging
to that subsystem. Rewritten: loader table, the name index + collision
rule, the `load()`/`acquire()`/`release()`/`unload_unused()` lifecycle,
`reload()` and its stale-holder caveat, the `.meta` pipeline with an honest
per-type table of what each setting *currently* affects, atlases,
`get_cache_stats()`. Audio and persistence sections dropped —
`pyguara/persistence` is next in the queue and gets its own page.

**Left open.** `AudioMeta.loop_start` / `loop_end` / `normalize` /
`load_mode` and `TextureMeta.mipmaps` / `wrap_s` / `wrap_t` still have no
consumer — honoring them needs real streaming / DSP / GL-state work beyond
a single slice (authoring-layer gap, sibling of #37). Under the new
lifecycle the audio system should `acquire()` the clips it wants to survive
a between-scene `unload_unused()` — a small `pyguara/audio` follow-up, no
behaviour change today (nothing calls `unload_unused()`). `ResourceManager`
does check-then-act on `_cache` / `_reference_counts` with no lock — no
concurrent caller exists, parked as CC (the DI audit's shape, if resource
loading ever moves to a background thread). `load_atlas()` still re-parses
its JSON every call (no `Atlas` cache) — a perf nicety, not a defect.

### `pyguara/animation` — CLOSED 2026-09-08 (branch `refactor/animation-audit`)

One slice, ~1,100 lines across both halves: `pyguara/animation/{easing,tween}.py`
and the sprite-animation FSM in
`pyguara/graphics/{animation_system.py,components/animation.py}` — the latter
was only "read and probed on degenerate input" during graphics slice 5, never
audited. Every defect was reproduced with a probe against the real code before
being touched.

**Verification:** 1714 tests pass (up from 1678; +36 across the three
animation test files, 102 → 138). `ruff check .` clean; `ruff format --check`
clean; `mypy pyguara` clean across 224 files; `mkdocs build --strict` exit 0;
`test_docs_api.py` (52) passes. Each commit verified standalone in a detached
worktree.

**F1 — `Tween` accepted only `float` scalars and `tuple`s.**
`Tween(0, 100, 1.0)` (int — the natural call), a `list`, mixed int/float, and
`Color` all constructed fine, then crashed on the first `update()` with a
bare `AssertionError` (empty message): `_interpolate` used
`assert isinstance(self.start_value, float)` as runtime validation.
`__post_init__` checked tuple-vs-tuple shape and length but never that a
scalar was a number, and never rejected a non-`tuple` sequence. Under `-O`
the asserts vanish and `list` misbehaves silently. Fixed: `__post_init__`
classifies each endpoint as number-or-sequence (`_is_scalar` / `_is_sequence`
`TypeGuard`s), rejects anything else (`Color`) with a clear `TypeError`, and
`_interpolate` handles `int`/`list` without asserts. `Vector2` keeps working
(it is a `pymunk.Vec2d`, a `tuple` subclass) but yields a plain `tuple` —
documented.

**F2 — `Tween` was a value-equality `@dataclass`.** Two independently
created tweens with identical config compared `==`, so
`TweenManager.remove(b)` removed the first equal element `a` (returned
`True`, left `b`); `TweenManager.update()`'s internal `self._tweens.remove`
had the same hazard. Bites any bag of identical fire-and-forget tweens
(fade-outs, hit flashes). `@dataclass(eq=False)` restores identity equality
(and makes `Tween` hashable again). "Identity vs value" — the gamepad-index
shape from the `input` audit.

**F3 — `Animator.update()` advanced at most one frame per call.** `if
self._current_time >= seconds_per_frame`, not `while`. A 10fps clip given
`update(0.5)` advanced one frame, not five; `_current_time` then climbed
unbounded (0.4, 0.8, …). Any host slower than the clip's `frame_rate`, or any
lag spike, silently dropped frames and fell permanently behind; a
non-looping clip's `is_finished` was delayed arbitrarily. Replaced with an
O(1) whole-frames-owed computation that wraps a looping clip with `%` and
clamps a non-looping one to the last frame. Same "one advance per frame"
shape as the audio one-shot reconciliation and the `application` event
budget.

**F4 — `AnimationStateMachine` re-fired `on_complete` and re-ran
`_check_transitions()` every frame while a non-looping clip sat finished.**
`Animator.is_finished` latches `True` for a non-looping clip until a new clip
plays; the FSM gated purely on that flag. A terminal state with no
`ANIMATION_END` transition (a death pose) → `on_complete` called 60×/s
(probe: 9 calls in 10 frames). Fixed with a `_completion_handled` latch,
reset in `transition_to()`. Exact shape of the audio F5 `_auto_played` latch.

**F5 — `AnimationClip` had no validation.** `frame_rate=0` →
`ZeroDivisionError` mid-`update()`; `frame_rate<0` → advances every frame,
`_current_time` drifts negative; `frames=[]` → `IndexError` in `_apply_frame`
on `play()`. `__post_init__` rejects all three at construction. Same
"no `__post_init__`" pattern as `SpatialAudioConfig` (audio F6) and
`PhysicsConfig`.

**F6 — `TransitionCondition.IMMEDIATE` was declared but unreachable.**
`_check_transitions()` only handled `ANIMATION_END`, and was only *called*
when `is_finished`. An `IMMEDIATE` transition in a state's `transitions` list
was silently never taken (probe: A→B IMMEDIATE, stuck in A). Now
`_check_transitions()` runs every frame and honours `IMMEDIATE` (fires on the
tick after entry) as well as `ANIMATION_END` (fires on finish); still one
transition per update, priority-ordered. "Declared and wired to nothing."

**F7 — `Scene.update_animations()` removed.** Its docstring Example told
games to call it from `scene.update()`. But `AnimationSystem` has been
auto-registered on every scene's `SystemManager` (priority 300, ticked at the
fixed timestep) since wayfinder ticket 24 (`a934c8f`) — later than this
method (`76a0203`). Following the doc updated every animation **twice per
frame** (once fixed-rate, once variable-rate). Zero real callers. Touches
`pyguara/scene`, but it is squarely a stale animation API.

**F8 (Phase C) — `docs/systems/animation.md` was wrong.** Its usage example
tweened `Vector2` and claimed `Color` works (`Color` crashes; `Vector2`
yields a bare tuple); it said the `TweenManager` "is handled automatically by
the `AnimationSystem`" — `AnimationSystem` never touches `TweenManager` and
nothing in the engine does, so a reader got a tween that never advanced;
easing, `Animator`, `AnimationClip` and the entire state machine were
undocumented. Rewritten to cover both halves accurately, including the
"you must tick `TweenManager` yourself" note, the identity-equality
guarantee, the frame catch-up, the once-per-completion callback, and
`IMMEDIATE` vs `ANIMATION_END`. `test_docs_api` won't catch a behavioural
claim like this — CC-10 family.

**Phase B — verdict on the 102 existing tests (+36; nothing rewritten
wholesale, three `AnimationSystem` asserts moved off private state).**

*`test_animation_easing.py` (48) — the strong file.* Endpoints for every
`EasingType`, ease-in monotonicity, elastic/back overshoot, `ease()` input
clamping, `isinstance(result, float)`. Real assertions on real returns
through the public surface. Only gap was the two properties it never pinned:
`ease_out` as the mirror of `ease_in`, and midpoint continuity for the
`ease_in_out_*` family. Added both (10 params each).

*`test_animation_tween.py` (30) — broad but uniform.* Every test built the
subject with `start_value=0.0, end_value=100.0` (float) or `(0.0, 0.0)`
tuples — never an int, list, `Vector2` or `Color`, so F1 was unreachable.
Every `TweenManager` removal/query test used a single tween or tweens with
deliberately *different* duration/end so no two were ever equal — F2
invisible. `test_infinite_loop` stepped exactly one `duration` per `update()`
so big-`dt` was never exercised. Added `TestTweenValueTypes` (int / mixed /
list / `Vector2` / `Color`-rejected / str-rejected), two identity-isolation
tests for the manager, and a test pinning the single-huge-`dt` one-cycle
catch-up.

*`test_animation_fsm.py` (24) — mixed.* `test_animator_is_finished` and the
auto-transition tests stepped a uniform 10fps clip at `dt == 0.1` exactly, so
F3 had no test that could see it; `test_state_machine_on_complete_callback`
stopped updating *on* the completion frame, so F4's storm was invisible.
`IMMEDIATE`, empty frames and zero `frame_rate` untested. The three
`AnimationSystem` tests asserted on `animator._current_frame_index` (private
— the tracker's named smell). Added multi-frame catch-up, the non-looping
large-`dt` clamp, held-past-completion (fires once), replay re-arms,
`IMMEDIATE`-on-entry, and `AnimationClip` validation; the `AnimationSystem`
asserts now observe the driven `Sprite.texture`.

**Left open.** A single `Tween.update(dt)` spanning many loops still resolves
one loop boundary and carries the overshoot forward (catches up over the next
few frames, no state lost) — a proper fix raises per-cycle-callback design
questions; documented and pinned by a test. `Color` tweening is unsupported
(tween its components / packed tuple) — documented. `_allow_methods = True`
on `Animator` and `AnimationStateMachine` stays CC-6. `ease()` rebuilds its
dispatch dict on every call — micro-perf, not touched.

### `pyguara/audio` — CLOSED 2026-09-08 (branch `refactor/audio-audit`)

One slice, ~1,700 lines (`manager`, `audio_system`, `audio_source_system`,
`components`, `types`, the pygame backend + loaders). Every defect was
reproduced with a probe against the **real** pygame-ce mixer (`SDL_AUDIODRIVER
=dummy`) before being touched — which is how the headline one surfaced at
all, since it is invisible to a mocked mixer.

**Verification:** 1678 tests pass (up from 1658; the fix commit alone is
1676, the docs commit adds 2 `test_docs_api` parametrisations for the new
page); `ruff check .` clean; `ruff format --check` clean; `mypy pyguara`
clean across 224 files; `mkdocs build --strict` exit 0; `test_docs_api.py`
(52) passes. Fix commit verified standalone in a detached worktree.

**F1 — SFX playback was dead end to end.** `PygameAudioSystem._play_sound`
read the channel id with `played_channel.get_id()`. pygame-ce's
`pygame.mixer.Channel` has **no `get_id()`** — the attribute is `.id`. So the
call raised `AttributeError` on every real `play_sfx` /
`play_sfx_at_position`, was caught by a blind
`except (AttributeError, Exception)`, logged as "Error playing sound", and
returned `None`. The sound had already been started by `native_sound.play()`
one line earlier, so it played — untracked, unstoppable (caller got `None`),
invisible to priority stealing / `set_channel_mix` / `stop_sfx` /
`get_active_sound_count` (all of which read the never-populated
`_playing_sounds`). **All 107 audio tests missed it**: `test_audio.py` and
`test_audio_backend.py` `patch("pygame.mixer")` or hand a `MagicMock` as the
`Sound`, and a Mock grows a `get_id()` on demand. The "fixtures that mock
away the unit under test" smell, same shape as `test_config.py` mocking the
filesystem. Fixed: acquire a `Channel`, call `channel.play(sound, loops=)` on
it, id is `channel.id`; `except` narrowed to `pygame.error`.

**F2 — loudness and pan were set on the shared `Sound`, not the channel.**
`native_sound.set_volume(effective_volume)` where `native_sound` is the
`AudioClip.native_handle` — one object the `ResourceManager` hands to every
concurrent play of that clip. Probe: play one explosion near (vol 1.0) then
another far (vol 0.16); the near one's loudness silently dropped to 0.16.
`set_channel_mix` had the same bug on the update path. Fixed: volume+pan go
on the channel via a `_set_channel_volume` helper — single-arg
`set_volume(v)` when centred (also clears any stale split), two-arg
`set_volume(l, r)` when panned. The `Sound` is never touched.

**F3 — a recycled channel kept the previous sound's hard pan.** `_apply_pan`
was only called when `abs(pan) > 0.01`, so a centred sound landing on a
channel that last played a hard-panned one inherited its `(1.0, 0.0)` split.
Fixed by F2's unconditional `_set_channel_volume`.

**F4 — `AudioSourceSystem` never noticed a one-shot ending.** Nothing polled
the mixer, so `_channel_id` / `_is_playing` were set once and cleared only by
an explicit `stop()`. Consequences: `AudioSource.is_playing` reported `True`
forever; a non-looping source could not be replayed (`_play_source`'s guard
is `_is_playing and _channel_id is None`, and `_channel_id` never went
`None`); the stale id kept getting `set_channel_mix` every frame, landing on
whatever sound now owned that recycled channel. Fixed: new
`IAudioSystem.is_channel_active(channel)` — `True` only while the exact sound
this system started is still on that channel (verified by `get_busy()` **and**
`get_sound() is` identity, reaping the tracking tables as a side effect) —
called each frame by `AudioSourceSystem` to reconcile.

**F5 — the F4 fix exposed an `auto_play` retrigger storm**, plus a latent
falsy-`0` bug. With reconciliation clearing an ended one-shot,
`auto_play and not _is_playing and not _channel_id` re-fired it every
subsequent frame. Added an `_auto_played` latch (auto_play is "on awake",
not loop). `not source._channel_id` also treated channel id **0** — a real
channel — as "no channel"; changed to `is None`, matching the check four
lines below it. A failed clip load now latches too, instead of hammering the
loader once per frame.

**F6 — `SpatialAudioConfig` had no validation.** `SpatialAudioConfig(
max_distance=0)` constructed fine and `calculate_pan` then raised
`ZeroDivisionError`; an inverted range (`max_distance < reference_distance`)
gave a hard volume cliff dressed as a rolloff. `__post_init__` now rejects
`reference_distance <= 0`, `max_distance <= reference_distance`, and negative
`rolloff_factor` / `pan_strength`.

**Also:** added `IAudioSystem.shutdown()` (idempotent `pygame.mixer.stop()` +
`music.stop()` + `mixer.quit()`), wired as a step in `Application.shutdown()`
— the mixer was previously never torn down. Removed
`AudioManager._active_channels` (declared, written nowhere, `.clear()`d in
cleanup — "wired to nothing"). `except (AttributeError, Exception)` →
`except pygame.error`; two `try/except pygame.error: pass` →
`contextlib.suppress`.

**Phase B — verdict on the 107 existing tests (+18; `test_audio.py` and one
integration test rewritten).**

*`test_spatial_audio.py` (39) — the strong file.* Pure maths on
`SpatialAudioConfig` / `AudioBus` / `AudioBusManager`, all through public
surface, real assertions on real return values. Its one gap was the missing
validation cases (F6) — added 3.

*`test_audio.py` (34, was 30) — rewritten.* It did
`patch("pygame.mixer")` for the whole module, so `Channel.id`, channel
volume, the shared-`Sound` trap and F1 itself were unreachable — the mock
supplied whatever attribute was asked for. Now runs the real dummy-driver
mixer with real `Sound` buffers; only `pygame.mixer.music` (needs a file on
disk) stays mocked. New tests: F1 (id names the busy channel), channel id 0
is valid, F2 (concurrent plays don't share volume; `Sound` untouched), F3
(recycled channel resets), `is_channel_active` across finish / reuse /
unknown, `shutdown` idempotence. Learned that `Channel.get_volume()` only
reflects a **single-arg** `set_volume`, so the panned split is verified via
`_channel_stereo` as a pure unit.

*`test_audio_components.py` (41, was 30) — mixed.* The `AudioSourceSystem`
tests build a `MagicMock` audio system and drive real components/Entity
Manager, which is honest for the ECS logic. Gaps were all uniform setup:
every source was played and left playing — nothing simulated a sound
*ending*, so F4/F5 had no test that could see them. Added finished-one-shot
reconciliation, replay-after-end, the looping-source-not-reaped case, the
`auto_play` latch, the failed-load latch, and channel-id-0.

*`tests/integration/test_audio_backend.py` (5) — honest, thin.* Already
dummy-driver + real mixer, but `test_play_sfx_mock` still handed a
`MagicMock` as the `Sound`, dodging F1. Rewritten to a real `Sound`.

**Phase C.** New `docs/systems/audio.md` (added to nav): the three layers,
music, the SFX channel contract (including "id 0 is valid"), the one-shot
lifecycle, spatial components + `SpatialAudioConfig` validation rules, buses,
and the documented limitation that a bus/master volume change does not
re-mix already-playing non-spatial SFX. `test_docs_api` and
`mkdocs build --strict` pass. The subsystem had **no** doc page before.

**Left open.** Bus / master / per-category volume changes re-apply to music
and to spatial SFX (re-mixed every frame) but not to already-playing
non-spatial SFX — a pygame-mixer limitation, documented rather than worked
around. `calculate_pan` keys stereo spread off horizontal offset only
(`test_pan_ignores_y_axis` pins this as intentional). `pygame_audio.py` and
`loaders.py` import pygame — legitimately, they are the backend.

### `pyguara/input` — CLOSED 2026-09-08 (branch `refactor/input-audit`)

One slice, ~1,500 lines (`manager`, `binding`, `gamepad`, `types`, `events`,
`protocols`, `keys`, the pygame backend). Four defects, each reproduced with
a probe against the real code before being touched, plus the unreachable
public surface they hid behind.

**Verification:** 1658 tests pass (up from 1644); `ruff check .` clean;
`ruff format` clean; `mypy pyguara` clean across 224 files;
`mkdocs build --strict` clean. The fix commits were each verified in a
detached worktree (`git worktree add --detach`, `uv sync --extra dev`):
1649 / 1652.

**F1 — `InputContext` was inert end to end.** `InputManager._context` was
set to `GAMEPLAY` in `__init__` and there was no public way to change it:
`dir(InputManager)` had `bind_input`, `register_action`, `update`,
`process_event` and nothing else. So `KeyBindingManager`'s entire
per-context machinery, the `context=` parameter on `bind_input()`, and three
of the four `InputContext` members (`UI`, `MENU`, `DEBUG`) were unreachable —
a binding registered for any of them could never fire. `test_context_switching`
"passed" only because it assigned `manager._context = InputContext.MENU`
directly, a private attribute, because no public one existed. Added a
`context` property + `set_context()` alias that publishes a new
`InputContextChangedEvent` on a real change (silent no-op when unchanged),
and a `bindings` property — `rebind()` / `import_bindings` / `export_bindings`
had *no* entry point on `InputManager` at all, and no caller anywhere in the
tree outside their own unit test.

**F2 — gamepad identity was the device index, not the SDL instance id.**
`GamepadManager` keyed `_joysticks`/`_controllers` by pygame device index and
detected unplugs with `controller_id >= joystick_count` — a tail-only check.
SDL renumbers the remaining devices when one in the *middle* unplugs. Probe:
Pad-A at index 0, Pad-B at index 1; unplug Pad-A; the manager reported
*Pad-B* disconnected, kept Pad-A's stale handle as controller 0, and would
have polled the dead device every frame. `instance_id` was already stored in
`GamepadState` and never used. `_scan_devices()` now reconciles against the
set of instance ids SDL reports, takes a fresh handle for every present
device each scan, and pins `controller_id` to one instance id for the life
of the connection — "player 1" stays player 1 when "player 2" unplugs.

**F3 — `rebind(SWAP)` lied when the moved action had no prior binding.**
No key to trade back, so the conflicting action was just unbound while the
call still returned `SWAPPED`. Now returns `UNBOUND`.

**F4 — `RebindResult.CONFLICT` was unreachable.** The `ERROR` resolution
raises `ValueError` rather than returning, so `CONFLICT` and half the
`-> tuple[RebindResult, BindingConflict | None]` return type were dead.
Removed; the enum is `SUCCESS` / `SWAPPED` / `UNBOUND`, all produced.

**F5 — input event timestamps frozen at 0.0.** `pyguara/input/events.py`
still used `timestamp: float = 0.0` with no `default_factory` — the exact
idiom the `events` audit replaced across `pyguara/events/*.py` — and
`InputManager` constructs `OnActionEvent` / `OnRawKeyEvent` / `OnMouseEvent`
without a timestamp, so every one read 0.0. All five event dataclasses now
use `field(default_factory=time.time)`; the redundant explicit
`timestamp=time.time()` in `gamepad.py` is gone.

**Patterns, extended.** *Declared and wired to nothing*: the context system,
and the whole rebind/conflict/serialization layer (reachable only via a
private attribute, used by nothing). *Uniform test setup*: every gamepad
hot-plug test unplugged only the last/only pad, so the mid-list reindex bug
had no test that could see it; every `rebind` SWAP test pre-bound both
actions, so the degenerate case returned the wrong result unnoticed.
Seventh and eighth instances.

**Phase B — verdict on the 29 existing tests (+14, 3 rewritten).**

*`test_input_rebinding.py` (18) — the strong file.* All four
`ConflictResolution` strategies, export/import, roundtrip, reset, all
through the public `KeyBindingManager` surface. Real gaps, all uniform
setup: every `rebind` test pre-bound the action being moved (so F3's
degenerate case was invisible), every SWAP test used one same-device key
(cross-device / multi-key / cross-context swap untested), the version guard
was only ever hit with `999` (the `> FORMAT_VERSION` boundary and the
warn-and-skip branches for a bad device / missing key / unknown context had
no coverage), and `test_export_import_roundtrip` keeps the dict in memory —
never through `json`, `test_config.py`'s exact blind spot. Added 5.

*`test_input.py` (11) — mixed.* `test_bound_gamepad_action_fires_from_polled_state`
is the model: end to end through the real path. But
`test_input_registration` / `test_keyboard_event_processing` /
`test_deadzone_filtering` build the manager by assigning
`manager._registered_actions[...]` and `manager._bindings.bind(...)`
directly, so the public `register_action()` / `bind_input()` path was
exercised by exactly one test — and only because a past field-order bug had
forced it. `test_gamepad_detection` asserted on `manager._controllers`
rather than the getters. `test_gamepad_manager_initialization` asserted
`manager is not None` and `get_connected_controllers() is not None` (a list
literal) — nothing. `test_input_manager_gamepad_integration` asserted only
"does not raise". Axis tests asserted `abs(value) > 0.0`, pinning none of
the deadzone rescale. Rewrote the three empty/private ones to assert real
behaviour (config actually drives the deadzone; getters report the
controller); added a test pinning the rescale formula
`(|raw|-dz)/(1-dz)`.

*`tests/integration/test_input_backend.py` (3) — honest but thin.* Headless,
so `get_joystick_count()` is always 0 and the entire `PygameJoystick`
wrapper (`get_button`, `get_axis`, `rumble`, `get_instance_id`) is
**untested** — the issue-#19 shape, a real adapter that is read-audited
only. Not fixable without hardware in CI; noted here.

*New for the fixes:* `test_context_switching` moved off the private
`_context`; a dormant non-active-context binding; one
`InputContextChangedEvent` per real change; `OnActionEvent` /
`GamepadButtonEvent` timestamps; gamepad mid-list unplug parametrised on
which pad goes; reconnect reuses the freed slot.

**Phase C.** `docs/systems/input.md` rewritten — it had described contexts
(no public API), an "SDL2" backend (does not exist), and told game code to
pass `pygame.K_SPACE` (CLAUDE.md forbids it). Now: the action/binding/context
model with the new accessors, the full event table, the gamepad API with the
stable-slot rule, and the rebinding + export/import surface with the honest
`RebindResult` set. `test_docs_api` and `mkdocs build --strict` pass. Also
added a curated `__all__` to `pyguara/input` (CC-8).

**Left open.** `input/manager.py` imports `pygame` directly and
`process_event()` consumes raw pygame key/mouse events and `KMOD_*`
constants — a CC-11 / issue #9 offender, parked with the rest of that
cross-cutting concern (the fix is `Window.poll_events()` yielding engine
events). `_handle_input` silently does nothing for an `ANALOG` action bound
to a digital key, or a `PRESS`/`RELEASE` action bound to an axis — documented
in the new page rather than changed. `import_bindings` does not coerce
`code` to `int`, so a hand-edited string code binds but never matches a
lookup — noted, not fixed.

### `pyguara/physics` close — spatial queries, sleeping, substeps, Phase C — CLOSED 2026-09-08 (branch `refactor/physics-queries-sleep-close`)

The fourth and final physics slice. Two capability gaps and a decision, none
of them a reproduced defect — the audit found them by comparing pymunk's
surface against what a game can reach. Every query and the sleep behaviour
was probed against the real backend before code went in.

**Verification:** 1644 tests pass (up from 1608); `ruff check .` clean;
`ruff format` clean; `mypy pyguara` clean across 224 files. `guara_falcao`
re-checked through `tools/agent_view.py` — title, gameplay, coins, patrolling
platform, crate all render and move.

**Q1 — spatial queries.** `raycast` and `overlap_box` were the only queries
on `IPhysicsEngine`, which ruled out click-picking, explosion radii, melee
arcs, piercing shots and "roughly what is around here" — and the projectile
layer in issue #28 names multi-hit queries as a dependency. Added five, all
in the existing style (`mask` + `ignore_entity_id`, entity ids not handles,
sensors skipped, an entity reported once): `point_query` (most-enclosed
first), `overlap_circle`, `overlap_box_all`, `region_query` (broad-phase,
bounding boxes not shapes), `raycast_all` (near→far). `overlap_box` gained a
`mask` parameter for parity — its four positional call sites in
`character_mover`/`platformer_system` now pass `ignore_entity_id` by keyword.
`set_collision_system` joined the `IPhysicsEngine` protocol (it worked only
because bootstrap holds the concrete `PymunkEngine`), and a stray
`# <--- Add this` marker is gone.

**Q2 — body sleeping.** `space.sleep_time_threshold` was left at Chipmunk's
`inf`, so every settled prop and debris body is simulated forever.
`PhysicsConfig.sleep_time_threshold` (default 0.5s, 0 disables) now drives
it. The probe settled a five-box stack and confirmed pymunk 7.2 wakes a body
on *any* state write — `position`, `velocity`, `rotation`, `apply_force`,
`apply_impulse` — so no adapter change was needed; a test pins that
behaviour since `SolidSystem` and manual kinematic moves depend on it. The
config validator now also rejects a negative threshold and `substeps < 1`,
which `PymunkEngine` otherwise only caught as a bare `ValueError` at startup.

**Q3 — `substeps` default: stays 4.** This file feared "~half a 60Hz frame at
200 dynamic bodies". The benchmark (200/500 bodies, settled and churning)
put substeps=4 at **0.65 ms/update at 200, 2.5 ms at 500** — an order of
magnitude less. Against a 10px wall, substeps 1/2/4 stop a body up to
~200/400/900 px/s. The cost of 4 is trivial and the tunnelling headroom
matters for knockback and explosion-flung props in the target genre; body
sleeping cuts the settled-props cost further. `substeps=2` is documented as
the knob for many hundreds of fast bodies. Both why-comments
(`config/types.py`, `pymunk_impl.py`) rewritten with the real numbers.

**Phase C.** New `docs/physics/queries.md` — all seven read-only queries with
a "reach for it when" table, the shared rules, and the precise-vs-broad-phase
distinction. `simulation.md` gains Substepping and Body sleeping subsections,
a Spatial-queries pointer, and a forward reference from `RigidBody` to
`CharacterBody`. `test_docs_api.py` passes; `mkdocs build --strict` passes.
Final read of `materials.py`, `tilemap.py`, `debug_draw.py`:
`tilemap`/`debug_draw` clean; `materials.py`'s docstring claimed "All
materials are frozen dataclass instances" but `PhysicsMaterial` was a plain
`@dataclass` — `Materials.ICE.friction = 0.9` would have rewritten ice
game-wide. Frozen now (nothing mutates a material), as a separate `fix:`
commit. The `docs/guides/*` physics references (onboarding, style guide,
zero-to-hero) have drifted pre-`CharacterMover` and one calls a nonexistent
`get_body` — out of scope for a single-subsystem slice, filed as **issue
#30** for a `docs/guides` pass.

**Tests (+36).** New `tests/integration/test_physics_queries.py` (26, one
class per query, built from moving and multi-shape bodies rather than the
suite's usual single body at rest — the fifth/sixth instance of that trap);
sleeping coverage in `test_physics_backend.py`; two validator cases in
`test_config.py`.

**Left for the next physics slice (its own PR, blocks nothing):** the
top-down kinematic character controller. `surface_velocity`, slope handling,
variable jump height and corner correction stay parked as low priority for
the genre.

### `pyguara/physics` triggers & joints — CLOSED 2026-09-08 (PR #27, branch `refactor/physics-triggers-joints-audit`)

The systematic pass the earlier physics work deferred: `collision_system.py`,
`trigger_volume.py`, `trigger_system.py`, `joints.py`. Both remaining feature
areas turned out to be inert end to end -- full API, docstrings and unit
tests, connected to nothing. Every defect was reproduced with a probe against
the real pymunk backend before being touched.

**Verification:** 1608 tests pass (up from 1591); `ruff check .` clean;
`mypy pyguara` clean across 224 files. Each finding below was confirmed by a
probe, and each fix by watching a new test fail when reverted.

**F1 -- the entire `Joint` ECS layer did nothing.** `Joint` plus all five
`create_*_joint()` factories plus `create_rope_chain()` produced components
that no system consumed: there was no `JointSystem`, and `PhysicsSystem` only
ever looks at `Transform`+`RigidBody`. `engine.create_joint()` was called
only by tests. Probe: a pin-jointed body free-fell 1846px in 2s;
`len(space.constraints) == 0`. `joints.py`'s module and class docstrings both
stated "The joint is created by the PhysicsSystem when both entities have
RigidBody components" -- untrue since the sentence was written.

New `pyguara/physics/joint_system.py`. `JointSystem` reads `Joint`
components, calls `engine.create_joint()` once both entities have a body in
the engine (retrying on later ticks until then, so it is order-independent
w.r.t. `PhysicsSystem`), stores the handle on `Joint._joint_handle` and
mirrors it in an owner-keyed table. It tears the constraint down on
`EntityDestroyed` for either endpoint, and on `Joint` component removal
(reconciled each `update()`). Opt-in and ticked by the game after
`PhysicsSystem.update()`, exactly like `PhysicsSystem` itself -- no
bootstrap/scene auto-registration, matching the existing convention.
`PymunkEngine.destroy_body()` now also removes a body's attached constraints
first, so tearing down a jointed body is self-consistent regardless of which
system gets there first.

**F2 -- trigger volumes fired with the roles swapped, so `TriggerSystem`
dropped every event.** `CollisionSystem.on_collision_begin/persist/end` took
`is_sensor: bool` and unconditionally treated `entity_a` as the trigger and
`entity_b` as the other body. Chipmunk's `arbiter.shapes` order is arbitrary;
the probe showed the dynamic body landing as `entity_a` in *both* entity
creation orders, so `OnTriggerEnter` came out `trigger_entity=<the ball>,
other_entity=<the zone>`. `TriggerSystem._on_trigger_enter` then looked up the
ball, found no `TriggerVolume`, and returned -- `entities_inside` never
populated, `contains_entity()` / `one_shot` / tag filtering all dead. The
callback contract is now `sensor_entity_id: str | None`: the backend resolves
which shape is the sensor (it is the only thing that can) and
`CollisionSystem._order_trigger_pair()` puts it first.

**F3 -- a trigger built the documented way never entered the simulation.**
`trigger_volume.py`'s own usage example adds `Transform` + `TriggerVolume`
and nothing else. `TriggerSystem.update()` added a sensor `Collider`, but
`PhysicsSystem` only registers shapes for entities that also have a
`RigidBody`, so the sensor shape never reached the space and no event ever
fired. `TriggerSystem` now also adds a static `RigidBody` when the entity has
none (a game that needs a moving trigger still supplies its own KINEMATIC
body). This is why `guara_falcao` never used `TriggerVolume` at all -- its
`CheckpointSystem` is a hand-rolled `distance < 40px` check over a bespoke
`ZoneTrigger` component, the workaround you write when the engine's triggers
don't work.

**Pattern, extended.** "Declared and wired to nothing" -- already flagged in
the last physics entry for `fixed_rotation`, `gravity_scale` and the
`return False` collision contract -- now has its two largest instances:
`Joint` (whole ECS layer) and `TriggerVolume` (end-to-end). Both had unit
tests that passed because each built its subject in isolation: joints tested
only via `engine.create_joint()` directly, trigger callbacks tested only with
the sensor hand-passed as `entity_a`. Uniform setup, fifth and sixth
instances.

**Tests (+17 net; ~50 changed).** `test_collision_events.py` rewritten for
the `sensor_entity_id` contract, with a new `TestTriggerRoleOrdering` class
that passes the sensor as `entity_b` and asserts the event still comes out
sensor-first. New `tests/integration/test_trigger_volumes_backend.py` drives
`PymunkEngine`+`CollisionSystem`+`PhysicsSystem`+`TriggerSystem` together --
parametrised on entity creation order (the thing that used to decide whether
triggers worked), plus the no-RigidBody case, tag filtering and one-shot. New
`tests/test_joint_system.py`: pin joint holds, deferred creation, teardown on
either entity's destruction and on component removal, self-target and missing
target tolerated, rope chain holds together, `cleanup()`.

**Docs (Phase C, partial).** `docs/physics/simulation.md` gains a Joints
section and a Trigger-volumes section (the three-system requirement, the
auto-added bodies); the collision section now states the sensor-ordering
guarantee. `test_docs_api.py` passes. Full-subsystem Phase C -- a dedicated
page, and reconciling the scattered `RigidBody` examples -- is still open.

**Deliberately not done:** no demo added (triggers/joints are covered by the
new integration tests and `guara_falcao` has no natural place for a
pendulum); `guara_falcao`'s checkpoints left on their hand-rolled path;
`create_joint`'s GEAR/MOTOR still structural-only (`ratio=1`, `rate=0` -- a
MOTOR joint would need new `Joint` fields to be useful); `set_collision_system`
still absent from the `IPhysicsEngine` protocol (works because bootstrap holds
the concrete `PymunkEngine`).

**Still open for subsystem close:** `physics.substeps` default (4 vs 2, from
the last entry); `point_query`/`bb_query`/`shape_query`/multi-hit segment
queries still unexposed; `surface_velocity`, slope handling, variable jump
height, corner correction, body sleeping still absent (all from the last
entry's reference comparison).

### `pyguara/physics` — IN PROGRESS (PRs #24 and #25, branch `fix/physics-collision-tunnelling`, merged)

Driven by a report that collision "works really poorly", with a brief to
judge the layer as **game** physics: Chipmunk simulates rigid bodies and
knows nothing about characters, ground or jumping, so everything that makes
a platformer feel right is PyGuara's own and is what was audited.

Every defect below was reproduced before being touched, and each fix was
checked by reverting it and watching the new test fail.

**Defects found and fixed**

1. **Tunnelling from 600 px/s** through a 10px wall — one solver step moves a
   body `velocity/60` px in a straight jump. Fixed by substepping
   (`physics.substeps`, default 4). Same cause as the reported *sinking on
   landing*: 11.2px deep for 24 frames before, 0.9px and no visible frames
   after.

2. **No render interpolation reachable from a custom renderer.** The engine
   had `render_alpha`, `previous_position` snapshotting and a lerp in
   `scene/base.py`, but only on the Sprite/RenderSystem path. Drawn raw at
   75Hz a body moves 0–5px per frame where every frame should be 4.
   `Transform.render_position(alpha)`, plus automatic opt-in by
   `PhysicsSystem` — a blanket default is wrong, since interpolating a
   variable-rate-moved transform *adds* judder (measured). `Transform.teleport()`
   covers respawns and screen wraps, which would otherwise streak.

3. **Every character detected itself as ground.** The ground ray starts 1px
   below the collider, but a Chipmunk segment query is a swept circle whose
   radius reaches back inside. `is_grounded` was True in mid-air and with no
   ground in the world at all, so coyote time never started, jump buffering
   had nothing to buffer, and the landing reset never fired — a character
   could jump twice and then never again until it died. `raycast()` gained
   `ignore_entity_id`.

4. **`fixed_rotation` and `gravity_scale` were inert** — declared on
   RigidBody, documented, read by nothing.

5. **pymunk 7 ignores a collision callback's return value**, so every
   `return False` in the backend did nothing — including `CollisionSystem`
   returning False to mean "report but do not resolve physically", which is
   how a non-sensor trigger is meant to work. Now expressed through
   `arbiter.process_collision`.

6. **Walking sank the character 8px permanently.** A floor of separate tile
   colliders has interior faces; a character rests `collision_slop` (0.1px)
   deep, so its leading bottom corner strikes the vertical faces of the tiles
   ahead. Traced: at a tile boundary it was flung upward at 47 px/s, hopped,
   landed 8.4px deep and stayed. `pyguara/physics/tilemap.py` merges solid
   tiles into as few rectangles as a greedy pass finds; sprites stay per-tile.
   Walking then holds 0.10px throughout. Pre-existing — main measures the same.

**Features added** (all absent, all genre staples Chipmunk cannot provide)

- **One-way platforms** (`Collider.one_way`, `one_way_normal`) — decided on
  the contact normal, not velocity (velocity is zero at a jump's apex, which
  flips the surface solid mid-overlap and ejects the character), and
  re-decided every step, not latched at first contact.
- **Collider debug draw** (`physics/debug_draw.py`, F1 in `guara_falcao`) —
  outlines every collider and the platformer's probe rays. Defect 3 would
  have been obvious in one frame of it.
- **`overlap_box`** — the first of pymunk's spatial queries beyond `raycast`
  that this engine exposes.
- **`CharacterMover`** (`physics/character_mover.py`) — swept
  collide-and-slide. **Built and tested, deliberately not wired in at the
  time.** Wired in below.

**Moving platforms already worked.** Measured before building: a kinematic
platform moving 200px carried its rider 187.6px, the rest being friction
slip. Undocumented gotcha: a kinematic body is position-synced *from* its
Transform, so a game moves one by advancing the Transform, not its velocity.
Superseded below: character riding no longer goes through Chipmunk friction
at all.

**The open decision — see `docs/physics/character-movement.md`.** Assigning
velocity to a dynamic body and letting the solver sort out the overlap is
the root of this whole family of bugs: sinking, seam catching, wall creep,
tunnelling. `CharacterMover` removes it by construction, but the character
stops being a physics body, so knockback, platform carrying and crate
pushing all need re-expressing. That document records the cost and the
recommendation; it needs a decision on what a character should still be able
to do physically before the conversion starts.

**Resolved — full parity built, on Celeste's model.** Checked against the
actual code before deciding: none of the three (knockback, riding, pushing)
existed as working features — `Hazard.knockback_force` was declared and read
by nothing, crates weren't implemented in `guara_falcao` at all, moving
platforms had no system driving them. Decision made: build full parity
anyway, using Celeste's integer-position-plus-remainder model (Maddy
Thorson's "Celeste and TowerFall Physics") rather than Chipmunk friction or
a continuous bisection sweep.

What shipped: `CharacterMover` rewritten to whole-pixel stepping with a
remainder accumulator (no more `MAX_STEP`/bisection — the last free whole
pixel is the answer directly), plus a `probe()` primitive that replaced
ground detection's raycast with a one-pixel overlap test (Celeste's
`OnGround()`). `CharacterBody` replaces `RigidBody` for a character —
literally no shape registered with the engine, which makes the ground-ray
self-detection bug class (defect 3, above) structurally impossible rather
than guarded against. `SolidMover`/`SolidSystem` (new) carry and push actors
for `MovingSolid` entities, built on `Solid.MoveHExact`/`MoveVExact` — a
direct placement plus a squish check, not a swept move, which is what a
first attempt using a swept carry got wrong for a platform closing in on a
resting rider (the platform's already-synced destination shape reads as
overlapping the rider mid-sweep, before it catches up). `Pushable` marks a
crate; `PlatformerSystem` asks `SolidMover.try_move()` to shove one when
blocked by it, excluding the pushing character from the reactive
carry/push pass — without that exclusion a pushed crate immediately shoves
back at whoever pushed it. `apply_knockback()` overrides velocity and
suppresses input control for a short window, decaying underneath continuing
gravity; `guara_falcao`'s `HazardSystem` now calls it.
`PhysicsSystem.sync_kinematic_transforms()` was split out of `update()` so
`SolidSystem`/`PlatformerSystem` can query a solid's current-tick position
before the simulation step runs. `guara_falcao` gets a demo patrolling
platform and a pushable crate for manual verification.

**Patterns, now four and five instances deep**

- **Uniform test setup, not missing coverage.** Every viewport test used a
  fullscreen viewport, every collision test a slow body, every platformer
  test a character already resting on the floor. Each defect lived in the
  case no test set up.
- **Declared and wired to nothing.** `fixed_rotation`, `gravity_scale`, the
  `return False` collision contract, interpolation reachable from one render
  path only. A game sets them, nothing happens, and there is no signal
  distinguishing an inert option from a wrong value. Worth a deliberate sweep
  of other subsystems for this shape.

**Reference comparison — mechanisms still missing.** Of pymunk's six spatial
queries the engine now exposes two (`raycast`, `overlap_box`); `point_query`,
`bb_query`, `shape_query` and multi-hit `segment_query` are unexposed, which
rules out click-picking, explosion radii, melee hitboxes and "can I fit here".
Also absent: `surface_velocity` (conveyors), slope handling (no max-slope
angle; a ramp will launch a character), variable jump height (releasing early
does not cut the jump), corner correction, and body sleeping (every idle body
is simulated forever).

**Still not audited:** `collision_system.py`, `trigger_volume.py`,
`trigger_system.py`, `joints.py`; Phase B (test assessment) and Phase C
(docs) for the subsystem as a whole. Given finding 5, the trigger files are
the most suspicious place to resume.

**Also left open:** whether `physics.substeps` should default to 4 or 2 —
4 costs about half a 60Hz frame at 200 dynamic bodies.


### `pyguara/ecs` — CLOSED 2026-09-06 (PR #1, branch `refactor/ecs-audit`)

**Verification:** 1161/1161 tests pass (68 in the two ECS files, up from 55);
`ruff check .` clean; `mypy pyguara` clean across 218 files.

**Correctness fixes (both reproduced by probe before fixing):**
- `EntityManager.add_entity()` indexed pre-attached components straight into
  `_component_index`, bypassing `QueryCache`. Entities entering the world via
  `clone()`, prefabs or deserialisation were invisible to every *cached* query
  while remaining visible to the uncached equivalent. Now routed through
  `_on_entity_component_added()`.
- `EntityManager.add_entity()` accepted a soft-dead entity, contradicting the
  documented terminal-removal invariant and producing a zombie: reachable via
  `get_entity()`, dropped from all queries at the next flush, raising on any
  mutation. Now raises `RuntimeError`.

**Other changes:**
- `StrictComponent.__init_subclass__` swallowed class keyword arguments
  (`object.__init_subclass__()`); now chains via `super(BaseComponent, cls)`.
- Removed a dead branch in `_get_logic_methods()` (both arms `continue`) and
  an unused module logger in `component.py`.
- Extracted `EntityManager._matching_entity_ids()`; the index-intersection
  logic was triplicated across three query methods.
- `QueryCache` now indexes registered queries by component type, so a
  component change visits only the queries it can affect instead of all of them.
- `QueryCache.clear_cache()` -> `rebuild_all()` (it rebuilt, never cleared).
  No callers outside the module.
- `ALLOWED_METHODS` is now a `frozenset` — **minor breaking change** for any
  caller that mutated it. Intentional: it is a module constant.
- Modern typing throughout (`dict`/`list`/`X | None`), Google-style docstrings,
  "what" comments purged, "why" comments kept.

**Docs:** new `docs/core/ecs.md` (full reference, added to mkdocs nav);
`docs/core/architecture.md` ECS section condensed to a summary + link, DI and
Event sections left untouched for their own iterations.

**Follow-up landed in the same pass (CC-5, removal hook):** at the user's
request, `EntityManager._on_entity_removed` — a private single-callback slot
assigned from `pyguara/scene/base.py` — was promoted to a public
`subscribe_entity_removed()` / `unsubscribe_entity_removed()` pair. Made it a
subscriber list rather than a slot: the old design let whichever consumer wired
itself last silently displace the scene's `EntityDestroyed` dispatch, which is
the same class of silent-clobbering bug as the two fixed above. `Scene` and both
test modules migrated; 7 further tests added (1168 total, from 1161).

**Deferred out of this subsystem:** CC-1 through CC-4, CC-6, and the remaining
half of CC-5 (`Entity._components` reached into by `persistence`/`prefabs`).


### `pyguara/common` — CLOSED 2026-09-06 (PR #2, branch `refactor/common-audit`)

**Verification:** 1236/1236 tests pass (up from 1168); ruff clean; mypy clean
across 217 files (one fewer: `constants.py` deleted).

**Correctness fixes (all three reproduced by probe before fixing):**
- `Transform.up` returned `(0, +1)` — the exact opposite of `Vector2.up()`'s
  `(0, -1)`, and pointing *down* on screen. Gravity defaults positive
  (`gravity_y = 900.0` in the shipped games), so the engine is unambiguously
  Y-down; `Transform.up` was wrong. Both now agree, and the convention is
  stated in both module docstrings and the new doc page.
- `Transform.set_parent()` had no cycle guard. `t.set_parent(t)`, or any
  loop, made every later `world_*` read recurse until the stack blew.
  Now raises `ValueError`; `is_ancestor_of()` exposes the check.
- `Transform.__init__` used `scale or Vector2(1, 1)`. `Vector2(0, 0)` is falsy,
  so an explicitly requested zero scale silently became unit scale. Now
  `is None`. Found by a test written against the documented behaviour, not by
  reading the code — see CC-7.

**API changes:**
- `Vector2.rotate(degrees)` → `Vector2.rotate_degrees(degrees)`. It sat one
  letter from `rotated(radians)`, and `Transform.rotate()` also takes radians;
  a one-letter difference deciding the angle unit is unreadable at a call site.
  All three call sites migrated (`camera.py` ×2, `particles.py`); all were
  correct beforehand, so this closes a latent trap rather than a live bug.
- `Color` now coerces channels to `int` and clamps to 0-255. It lost pygame
  .Color's own validation in the ticket-31 migration and gained no replacement,
  so `Color.from_hsv(0, 5, 5)` produced `Color(1275, -5100, -5100)`. Clamping
  rather than raising: colour arithmetic overshoots legitimately, and a crash
  mid-render is worse than saturation.
- Added `Vector2.down()`/`left()` and `Transform.left`/`down` — `up`/`right`
  existed without their opposites.
- Added `Color.to_hex()` and `Rect.size`.
- `Tag` and `ResourceLink` are now `@dataclass(slots=True)`, as the ECS docs
  require. This required replacing `super().__init__()` with an explicit
  `BaseComponent.__init__(self)`: `slots=True` returns a *new* class, so a
  zero-arg `super()` resolves against the discarded original and raises on
  every instantiation. Caught by 10 failing tests, not by review.
- `Rect.inflate()` now truncates the offset towards zero instead of flooring,
  matching `pygame.Rect` for odd negative deltas (was off by one pixel).

**Cleanup:** deleted `pyguara/common/constants.py` (a file containing only a
docstring, imported nowhere). `palette.BasicColors` now re-exports the `Color`
constants instead of redefining all nine.

**Tests:** 52 in `test_common_types.py` (from 24) plus a new
`test_transform.py` with 36. `Vector2` and `Transform` previously had **zero**
direct tests — Transform appeared in ten other modules only as an incidental
fixture, so the most intricate logic in the package was exercised by accident.

**Docs:** new `docs/core/common-types.md`, added to the mkdocs nav.

**Deferred:** CC-1 through CC-4, CC-6, CC-7, and the remaining half of CC-5.


### `pyguara/events` — CLOSED 2026-09-06 (PR #3, branch `refactor/events-audit`)

**Verification:** 1262/1262 tests pass (up from 1236); ruff clean; mypy clean.

**Correctness fixes (all reproduced by probe before fixing):**
- Every event dataclass in `input.py`, `lifecycle.py` and `window.py` used
  `timestamp: float = 0.0` plus a `__post_init__` overwriting zero with
  `time.time()`. A genuine timestamp of 0.0 was therefore impossible to
  express, and the idiom was duplicated five times. Replaced with
  `field(default_factory=time.time)`, which `ecs/events.py` already used --
  the engine had two idioms for the same thing and the more common one was
  the broken one.
- `filter_func` exceptions bypassed `error_strategy` entirely: a raising
  filter propagated even under IGNORE, because only the handler call was
  wrapped. A filter is user code too, and now follows the same policy.
- **Latent `log` <-> `events` import cycle.** `pyguara.log.events` inherits the
  `Event` protocol at runtime, so `log` depends on `events`; but
  `events.dispatcher` imported `pyguara.log` at module scope. The cycle was
  masked only by `events/__init__.py` being empty, and detonated the moment
  re-exports were added. `events` is the more foundational package, so the
  fix is on its side: `EngineLogger` is a type-only import and the default
  logger resolves lazily inside `__init__`. Both import orders are now
  covered by a subprocess regression test.

**API changes:**
- `dispatch()` returns `bool` instead of `None` -- True if every handler ran,
  False if one consumed the event by returning False. The short-circuit
  already worked but was invisible to callers, which is precisely what
  UI-over-game input handling needs. No in-repo caller used the return value,
  so this is additive. `IEventDispatcher` updated to match.
- `max_history_size` is now a constructor parameter; it was hardcoded at 1000
  while `enable_history` was configurable.
- `IEventDispatcher.subscribe` gained the `filter_func` parameter the
  implementation always had.
- `events/__init__.py` re-exports the public surface with an `__all__`.

**Performance:** `dispatch()` rebuilt and re-sorted the merged MRO handler
list on every single call -- in the engine's hottest path. Now memoised per
concrete event type and invalidated when the subscription set changes.
Measured on 20 000 dispatches with 50 handlers: 5.7 us -> 3.1 us per dispatch.

**Tests:** 23 -> 49. The dispatcher's existing tests were genuinely good; the
gaps were the event dataclasses (untested, and where the timestamp bug lived),
filter error handling, `clear_subscribers`, history filtering and sizing,
cache invalidation, snapshot-during-dispatch semantics, and real multi-thread
`queue_event` contention.

**Note:** one existing test caught a regression I introduced -- dropping the
exception text from the handler error message. Restored.

**Docs:** new `docs/core/events.md`; `architecture.md`'s Event section
condensed to a summary and link.

**Deferred:** CC-1 through CC-4, CC-6, CC-7, CC-8, and the rest of CC-5.


### `pyguara/di` — CLOSED 2026-09-06 (PR #4, branch `refactor/di-audit`)

**Verification:** 1286/1286 tests pass (up from 1262); ruff clean; mypy clean.

**Correctness fixes (all reproduced by probe before fixing):**
- **`DIScope.get()` resolved without taking the container lock**, so parallel
  resolutions through scopes shared one mutable cycle-detection stack and saw
  each other's partial chains. With constructors that take a couple of
  milliseconds this reported **140 spurious CircularDependencyExceptions out
  of 160 resolutions**. It hid because every constructor in the test suite is
  instant. Fixed twice over, deliberately: the scope now takes the lock like
  the container does, and the resolution stack is thread-local, so the
  invariant holds structurally rather than by remembering to lock -- which is
  exactly the discipline that failed here.
- **Captive dependency.** A singleton resolved inside a scope captured the
  scoped instance; the scope disposed it and the singleton kept handing out
  the dead object forever. Singletons are now built with `scope=None`, so the
  attempt raises with a message explaining why.
- **A disposed scope still resolved**, tracking new disposables in a list it
  had already emptied -- they would never be cleaned up. Now raises.
- **Re-registering an already-resolved singleton silently did nothing.** The
  registration was replaced but the cached instance was not, so `get()` kept
  returning the old implementation. The cached instance is now evicted.
- **`*args`/`**kwargs` were treated as injection points.** `*args: int` was
  read as a dependency named "args" of type `int`, making any class that
  declares varargs unresolvable. Only POSITIONAL_OR_KEYWORD and KEYWORD_ONLY
  parameters are considered now.
- **`DIScope.dispose()` swallowed every exception** with a bare
  `except Exception: pass`. Failures are logged, and the remaining services
  are still disposed.

**API additions:** `DIContainer.is_registered()` and `DIScope.disposed`, both
needed to write the tests above without reaching into privates.

**Also:** `_create_instance` could fall off the end and return None for a
malformed registration; it now raises. Modern typing, Google-style docstrings,
P2-003 ticket references removed from public docstrings (CC-3).

**Tests:** 26 -> 40. The existing tests were reasonable but entirely
single-threaded and single-scope, which is why the lock bug survived. Added
lifetime-capture rules, disposal semantics, re-registration, signature edge
cases, and three genuine concurrency tests.

**Docs:** new `docs/core/dependency-injection.md`; `architecture.md`'s DI
section condensed to a summary and link. That file's three original sections
(ECS, DI, Events) are now all summaries pointing at dedicated pages.

**Deferred:** CC-1 through CC-4, CC-6 through CC-9, and the rest of CC-5.


### `pyguara/log` — CLOSED 2026-09-06 (PR #5, branch `refactor/log-audit`)

**Verification:** 1303/1303 tests pass (up from 1286); ruff clean; mypy clean.

**Correctness fixes (all reproduced by probe before fixing):**
- **Every log record in the engine reported `logger.py:138` as its source.**
  `EngineLogger._log()` called `self._logger.log()` without a `stacklevel`, so
  the two wrapper frames were never skipped and every record attributed itself
  to the same line inside the wrapper. The file formatter's `%(lineno)d`, and
  the `module`/`line` fields carried into `OnLogEvent`, were that same constant
  for every message ever logged. A caller-supplied `stacklevel` is now offset
  rather than ignored.
- **`reconfigure()` cleared the whole handler list of a process-global stdlib
  logger**, silently tearing down handlers installed by the application, by a
  test, or by a second `LogManager` using the same name. Each logger now tracks
  and removes only the handlers it installed.
- **`shutdown()` closed handlers but left them attached**, and a closed
  `FileHandler` silently reopens its file on the next record -- so shutdown
  did not actually stop logging. It detaches now, and a test asserts nothing
  is written afterwards. (My first probe of this claimed data loss; checking
  the file showed the opposite. The defect is that shutdown is a no-op, not
  that it drops records.)
- **`configure(dispatcher=None)` could not detach a dispatcher**, because
  `if dispatcher:` cannot tell None from unspecified. A sentinel default now
  distinguishes them.

**Also:**
- `EventIntegratedHandler.emit()` built a throwaway `LogRecord` on **every**
  record, purely to compute a constant set of key names. Hoisted to a
  module-level frozenset.
- `propagate` is now configurable. Engine loggers install their own handlers
  *and* propagate, so an application that also configures root logging sees
  every record twice. Default left at True -- propagation is what lets an app
  capture engine output, and the duplication only occurs when the app prints
  too -- but the choice is now explicit and documented rather than implicit.
- Removed a leftover `# FIX:` comment; documented `LogCategory` as orthogonal
  to `LogLevel`. Modern typing, Google-style docstrings.

**Tests:** 9 -> 26. Source attribution, handler ownership, shutdown semantics,
`configure()` dispatcher handling, propagation, and the path from structured
keyword arguments through to `OnLogEvent.context`.

**Docs:** `docs/core/logging.md` **rewritten from scratch** -- see CC-10. It
documented `pyguara.log.config.setup_logging()`, a module and function that
have never existed in this tree; every code sample on the page raised
`ModuleNotFoundError`.

**Tier 1 is now complete:** `common`, `log`, `events`, `di`.

**Deferred:** CC-1 through CC-4, CC-6 through CC-10, and the rest of CC-5.


### Cross-cutting pass — 2026-09-06 (branch `chore/lint-modernization`)

Taken between subsystem iterations, at the user's direction, to clear the two
concerns that were compounding across every audit.

**CC-1 / CC-2 — lint modernisation.** `target-version` bumped `py39` -> `py312`
and `UP`, `B`, `I`, `SIM` enabled. 1455 findings fixed mechanically; the
remainder by hand. 273 files changed.
- One real defect found by `B`: `WorldPass(clear_color=Color(0,0,0,255))`
  shared a single mutable `Color` across every instance.
- Twelve B008 reports were false positives -- `Vector2` is a NamedTuple
  subclass, hence immutable -- handled with
  `flake8-bugbear.extend-immutable-calls` rather than scattered noqa comments.
- `di/decorators.py` needed a rewrite: ruff's B010 fix removed `setattr()`
  calls that existed to dodge mypy, so the errors came straight back. Now uses
  a typed `_DIMarked` protocol, which also collapsed three identical decorator
  bodies into one helper.
- **The pydocstyle pre-commit hook was mis-scoped.** It used a `match:` key
  pre-commit does not recognise -- warning "Unexpected key(s) present" on every
  run for who knows how long -- so it linted the entire repository, not
  `pyguara/`. Fixed to `files:`. This surfaced undocumented public methods in
  `persistence/serializer.py` that the broken scoping had hidden.

**CC-9 — shared `ErrorHandlingStrategy`.** Hoisted to a new top-level
`pyguara/errors.py`. Both `di` and `events` re-export it, so no import path
breaks, and the two enums are now genuinely the same class.

**CC-10 — documentation smoke test.** `tests/test_docs_api.py` checks every
`pyguara...` import and dotted reference in `docs/`. It found two more
fictional APIs on its first run (see CC-10 above).

**Verification:** 1343/1343 tests pass; ruff clean; mypy clean across 218 files.

**Not done:** the filename `docs/guides/Archictecture & Style Guide.md` is
misspelled. Renaming it means touching the mkdocs nav and any inbound links, so
it is left for whoever next edits that file.


### `pyguara/config` — CLOSED 2026-09-06 (PR #7, branch `refactor/config-audit`)

**Verification:** 1371/1371 tests pass (up from 1343); ruff clean; mypy clean.

**Correctness fixes (all ten reproduced by probe before fixing):**
- **`Color` did not survive a save/load round trip.** `asdict()` flattens it to
  `{"r": ..., "g": ...}` and `from_dict` passed that straight back to
  `WindowConfig`, so `display.default_color` came back as a `dict`. Both window
  backends read it as `self._default_color` and pass it to `clear()`, so
  `fill_color.r` raised AttributeError. Reachable on the *ordinary* path: run 1
  finds no config file and writes defaults, run 2 reads them back and breaks.
  `from_dict` is now field-driven and coerces by declared type, which also
  removed five near-identical per-section blocks.
- **`OnConfigurationLoaded` and `OnConfigurationSaved` were permanently stamped
  `timestamp=0.0`.** Unlike the input/lifecycle events fixed in the `events`
  pass, these had no `__post_init__` at all, and the manager never passed a
  timestamp. Now `field(default_factory=time.time)`.
- **`PhysicsConfig.fixed_dt` divided by zero** with nothing validating
  `fixed_timestep_hz`. `Application.run()` reads it on every startup, so a zero
  in a config file crashed the engine with a bare ZeroDivisionError naming
  neither the setting nor the file. Now raises a named ValueError, and the
  validator reports it as CRITICAL.
- **`update_setting()` warned about a type mismatch and then assigned anyway**,
  so `screen_width` could end up holding `"not a number"`. It now refuses, and
  is stricter than `isinstance` where that matters: a `bool` is not an `int`
  here, though `isinstance(True, int)` says otherwise.
- **`update_setting()` bypassed validation entirely**, so it could put the
  config into a state `load()` would have rejected (`master_volume = 99.0`). It
  now reverts and refuses on an ERROR/CRITICAL issue; WARNING passes, since a
  warning is advice.
- **`from_dict` mutated the caller's dict** (the debug section was not copied).
- **Unknown keys were dropped in silence** -- a typo'd setting simply never
  took effect. Now ignored *and* logged, so a config from a newer engine still
  loads but a typo is visible.
- **Invalid env overrides failed silently** (`except ValueError: pass`), so a
  typo in a launch script did nothing at all. Now reported, and the message
  lists the valid values.
- **Every validation issue was logged as a warning**, hiding ERROR and CRITICAL
  among the merely suboptimal. Each is now logged at its own level.
- **`ConfigManager._file_path` was hardcoded**; now a constructor argument,
  which the tests needed anyway.

**Validator coverage** went from 3 rules to 10: screen height, all three
volumes rather than just master, gamepad deadzone, mouse sensitivity, fps
target, fixed timestep and max frame time. `ValidationIssue` is now frozen and
its `suggestion` field is actually populated.

**Tests:** 5 -> 33. The existing five covered defaults, a mocked load, a mocked
missing file and two `update_setting` cases -- all with mocks rather than real
files, which is exactly why no round-trip bug could surface. The new ones use
`tmp_path` and assert on real files, including a whole-config round trip that
will catch the next field that fails to survive one.

**Docs:** new `docs/core/configuration.md`, added to the nav;
`application.md`'s config paragraph now links to it.

**Deferred:** CC-3 through CC-8 (CC-1, CC-2, CC-9, CC-10 resolved).


### `pyguara/application` — CLOSED 2026-09-06 (PR #8, branch `refactor/application-audit`)

**Verification:** 1384/1384 tests pass (up from 1373); ruff clean; mypy clean.

**Correctness fixes (all reproduced by probe before fixing):**
- **The event-queue time budget was spent per fixed step, not per frame.**
  `_fixed_update()` drained the queue, and it runs once per accumulated step,
  so a frame lagging by the full `max_frame_time` called `process_queue(
  max_time_ms=5)` **15 times** -- up to 75ms in one frame. The budget exists
  specifically to stop an event death spiral, and it was multiplied by the step
  count at exactly the moment a spiral begins. Drained once per frame now.
- **`shutdown()` was neither idempotent nor exception-safe.** A raising
  `scene_manager.cleanup()` meant the window was never closed and the log
  manager never shut down -- on the crash path, where releasing them matters
  most. Steps are isolated and logged now, and a second call is a no-op.
- **The ModernGL render path hardcoded `Color(0, 0, 0, 255)`**, so
  `display.default_color` silently did nothing under that backend while the
  pygame path honoured it via `window.clear()`.
- **Three lifecycle events had no publisher.** `ApplicationStartEvent` and
  `QuitEvent` are now dispatched; `pyguara/tools/event_monitor.py` subscribes
  to `QuitEvent`, so its handler had been unreachable. `WindowResizeEvent`
  still has none -- see CC-11.
- **`ServiceNotFoundException` was imported inside the `try` block whose
  `except` names it**, so an ImportError there would have raised NameError
  instead of being handled.
- `raise e` in the loop's handler appended a frame to the traceback; now a bare
  `raise`.

**Tests:** 2 -> 13 in `test_app_flow.py`. The existing two covered a single
frame and a scene switch; nothing covered shutdown, lifecycle events, the event
budget, or the failure paths.

**Docs:** `docs/core/application.md` rewritten. Its "Main Loop" section listed
`Time.tick()`, `Input.process()`, `Update()`, `Render()` -- none of which are
real method names -- so it described the loop's shape without matching the
code. Now documents the actual sequence, why frame time is clamped, and why the
event queue is drained outside the accumulator loop.

**Parked:** CC-11 (pygame in the backend-agnostic core). `bootstrap.py` and
`sandbox.py` were scanned and are otherwise clean; their `# type: ignore[
type-abstract]` markers are the known mypy limitation around Protocol
registration, not defects.

**Deferred:** CC-3 through CC-8, CC-11.


### `pyguara/scene` — CLOSED 2026-09-06 (PR #10, branch `refactor/scene-audit`)

**Verification:** 1399/1399 tests pass (up from 1384); ruff clean; mypy clean.

This module was visibly more careful than earlier ones -- dense "why" comments
from prior wayfinder work, and `cleanup()` written specifically to avoid a
leak. The defects are all at its seams rather than in its core logic.

**Correctness fixes (all five reproduced by probe before fixing):**
- **`switch_to()` abandoned every stacked scene.** It ended in a bare
  `self._stack.clear()`, so a scene pushed under an overlay was never exited
  and its SystemManager never cleaned -- it stayed live holding its
  EntityManager, systems and physics bodies. `cleanup()`'s own docstring warns
  against "leaking whatever's still on the stack past a bare `.clear()`", and
  `switch_to()` did exactly that on every scene change. Now unwinds LIFO:
  current scene first, then the stack top-down.
- **A second stack change during a transition replaced the pending scene.**
  `switch_to("b", fade)` then `switch_to("c", fade)` left 'b' skipped entirely
  -- never entered -- while its predecessor had already been exited. All three
  stack operations now refuse while a transition runs, and log it.
- **`pop_scene()` with a transition stranded the scene it was returning to.**
  The stack entry was removed up front, so between the call and completion the
  previous scene was both off the stack and not yet current: a `cleanup()` in
  that window never exited it. The entry is now held until completion.
- **`cleanup()` missed a scene mid-transition.** A scene a transition had
  started entering but not yet made current was invisible to it. Now included,
  with an identity set so nothing is exited twice.
- **`register()` before `set_container()` silently skipped wiring**, leaving a
  live scene with no camera or render system -- surfacing much later as an
  assertion inside `render()`. `set_container()` now wires any scenes already
  registered.
- **`register()` silently replaced a same-named scene.** Still replaces, since
  that is occasionally intended, but logs that the displaced scene is now
  unreachable.

**Tests:** 18 -> 33 in `test_scene_stack.py`. The existing suite covered the
stack shapes well (pause menu, dialog, inventory, nested pause flags) but
nothing covered what happens to stacked scenes on a *switch*, or any
re-entrancy during a transition -- which is where all five defects lived.

**Note:** my first fix got the unwind order wrong, exiting the stack before
the current scene. A test written for LIFO ordering caught it.

**Docs:** new `docs/core/scenes.md`, added to the nav. The subsystem had no
dedicated page; `pause_below` semantics, the switch-versus-push lifetime
difference and the one-transition-at-a-time rule were undocumented.

**Deferred:** CC-3 through CC-8, CC-11 (now GitHub issue #9).


### `pyguara/systems` — CLOSED 2026-09-06 (PR #11, branch `refactor/systems-audit`)

**Verification:** 1414/1414 tests pass (up from 1401); ruff clean; mypy clean.

The smallest subsystem so far (165 lines of manager, 63 of protocols) with the
best existing test ratio. Three real defects nonetheless.

**Correctness fixes (all reproduced by probe before fixing):**
- **A system registered after `initialize()` was never initialised.**
  `initialize()` sets a flag and returns early on every later call, and
  `Scene.resolve_dependencies()` calls it *before* `on_enter()` -- which is
  precisely where a game is documented to register its own systems (priority
  >=500). Every game system therefore started up uninitialised. A late
  registration now initialises immediately.
- **`unregister()` tested truthiness, not `None`.** A system defining
  `__len__` or `__bool__` falsily was dropped from the lookup table but left
  in the update list: still ticking every frame, never cleaned up, and
  returned as though removed.
- **Duplicate registration keys were silent.** Several systems can share a key
  -- they all update -- but the lookup table holds one entry per key, so the
  earlier ones become unreachable by `get_system()` and survive
  `unregister()`. Now logged, with the fix (`system_type=`) named in the
  message.

**A design choice I reversed mid-iteration.** My first fix made duplicate
registration *evict* the earlier system, on the reasoning that an unreachable
system still consuming a frame budget is a leak. Three existing tests failed:
they register several `MockSystem`/`OrderedSystem` instances under one class
and expect all of them to update. That is a legitimate pattern -- multiple
instances of one generic system -- and eviction destroyed it. The update list
is the source of truth; the type map is a convenience index that simply cannot
represent duplicates. So the fix became surfacing the ambiguity rather than
resolving it by force.

**Also:** `get_system()` was typed `-> Any | None` and now returns the
requested type, so callers stop losing type information at every lookup.

**Tests:** 21 -> 34. The existing suite was genuinely good on the happy paths
and the pause/resume gate; the gaps were registration *after* initialize, key
collisions, and `unregister` edge cases.

**Docs:** `docs/core/scenes.md` gains a Systems section -- a scene's
`SystemManager` is where these are encountered. It records the priority band
convention, that late registration is safe, and that the priority direction is
the opposite of `EventDispatcher`'s (ascending here, descending there), which
was written down nowhere.

**Deferred:** CC-3 through CC-8, CC-11 (GitHub issue #9).

**Tier 2 complete:** `config`, `application`, `scene`, `systems`.

### `pyguara/graphics` iteration 1 — the window boundary — awaiting approval (2026-09-06)

`pyguara/graphics` is ~8,000 lines across five distinct areas, so it is being
audited in slices rather than as one iteration. This is the first: `window.py`
and the `IWindowBackend` contract.

**Verification:** 1427/1427 tests pass; ruff clean; mypy clean.

**Correctness fixes:**
- **`Window.width`/`height` reported the *requested* size, never the granted
  one.** Both returned `WindowConfig` values unconditionally, so a window the
  OS sized differently -- a fullscreen window is routinely handed the desktop
  resolution instead -- reported whatever had been asked for.
  `Application.__init__` feeds these straight into
  `SceneManager.set_screen_size()`, and from there they reach transitions and
  viewport calculations. They now come from the backend once the window
  exists, falling back to config before `create()`.
- **The `IWindowBackend` contract was split three ways.** The protocol declared
  no size accessors, yet the ModernGL window and headless renderer both
  implemented them and the pygame window did not. Nothing checked, because
  nothing asked. `width`/`height` are now on the protocol and implemented by
  all three -- mypy caught the missing headless implementation the moment the
  protocol declared them, which is the protocol finally doing its job.
- Corrected `Window.clear()`'s docstring, which claimed to use the configured
  default colour while actually forwarding `None` for the backend to resolve.

**Tests:** new `tests/test_window_boundary.py`, 13 tests. `Window` had no
dedicated tests at all -- it was exercised only incidentally through
`MagicMock` window fixtures in the application suite, which is why a size
accessor that ignored the backend entirely went unnoticed. Includes protocol
conformance checks for both real backends.

**Issue #9 updated.** Mapping every non-backend pygame import turned up nine
files across five subsystems, not the two originally recorded. Two matter:
`input/manager.py` interprets SDL events directly (`pygame.KEYDOWN`,
`pygame.key.get_mods()`, `KMOD_*`), so event translation is an input change as
much as a graphics one; and `graphics/components/geometry.py` is an ECS
component importing pygame, the clearest single violation and the cheapest to
fix alone. The issue now carries a four-step sequence, each step independently
shippable.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9).


### `pyguara/graphics` iteration 2 — components — awaiting approval (2026-09-06)

**Verification:** 1449/1449 tests pass; ruff clean; mypy clean.

**Correctness fixes:**
- **`components/geometry.py` was hard-wired to pygame** -- it imported pygame,
  drew onto a `pygame.Surface` and constructed a `PygameTexture` directly. So
  `Box` and `Circle` silently produced the wrong texture type under ModernGL:
  an ECS-facing component that only worked on one backend. This was the
  clearest single instance of issue #9, and the one the issue named as
  cheapest to fix alone.

  The abstraction already existed and was already used by `SpriteSheet` in the
  same package: `TextureFactory.create_from_bytes()`. Shapes now rasterise to
  plain RGBA bytes in pure Python and hand them to an injected factory, so they
  work on pygame, ModernGL and headless alike. The module imports no backend at
  all. Circle rasterisation fills by row spans -- each row's half-width follows
  from the circle equation -- so it is O(diameter) rather than O(diameter^2).

  `Box` and `Circle` gain a required `texture_factory` argument. Nothing in
  `pyguara/` or `games/` constructs them, so no production caller breaks; the
  precedent for how to obtain one is `SpriteSheet.from_container()`.

- **`Camera2D.zoom` accepted zero and negative values**, and three code paths
  then disagreed about what that meant: `world_to_screen` collapsed every point
  onto the screen centre, `screen_to_world` substituted `0.001` and returned
  coordinates six orders of magnitude out (`Vec2d(-390000, -290000)` for a
  point at `(10, 10)`), and `get_view_bounds` raised `ZeroDivisionError`. A
  negative zoom silently mirrored the world. `zoom` is now a validated property
  and `zoom_to()` checks its target, so the invariant holds at assignment
  rather than being papered over in one consumer and crashing in another. The
  `safe_zoom = 0.001` fudge is gone.

**Tests:** `test_graphics_geometry.py` rewritten, 6 -> 30. The originals
asserted against `PygameTexture` and read pixels off a `pygame.Surface`, which
is exactly the coupling being removed. Rasterisation is now checked against raw
bytes (backend-free) *and* through the real pygame factory, so both the maths
and the backend path are covered -- plus symmetry, span width, lazy generation
and cache invalidation, which nothing checked before.

**Surveyed and clean:** `animation.py` handles an unknown clip name correctly
(logs and declines); `sprite.py` is a plain data component; `particles.py` uses
a fixed pool with documented degree units. `animation.py` carries
`_allow_methods = True` in two places -- playback and FSM logic on components
-- which belongs to CC-6 rather than this slice.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9, now partly addressed).


### `pyguara/graphics` iteration 3 — backends — awaiting approval (2026-09-06)

**Verification:** 1464/1464 tests pass; ruff clean; mypy clean.

**Correctness fixes:**
- **The pygame compatibility stubs had drifted from the classes they stand in
  for.** `graphics/backends/pygame/stubs.py` exists so game code using
  framebuffers, lighting or post-processing runs unchanged on pygame; its
  entire value is interface parity. Comparing each stub's public surface
  against its real counterpart found two holes:
  `PygameLightingSystem` was missing `collect_lights_screen_space` (called by
  `pipeline/passes/light_pass.py`) and `PygameRenderGraph` was missing `ctx`
  (read by `application.py`). Either is an `AttributeError` that appears only
  after switching backend -- precisely the failure the stubs exist to prevent.
  The file had **no test references at all**.

**Tests:** new `tests/test_pygame_stubs.py`, 15 tests. Two are parametrised
parity checks comparing every stub against its counterpart, by member name and
by argument list, so the next divergence fails in CI rather than in a game.
Verified they bite: removing `collect_lights_screen_space` again reproduces the
failure with a message naming it. The rest cover the no-op behaviour itself --
that the lighting stub reports *full* ambient rather than darkness, that the
post-process stack passes frames through untouched, and that the lifecycle
calls are harmless.

**Surveyed and clean:** all six shipped implementations satisfy their protocols
structurally (`IWindowBackend`, `IRenderer`, `UIRenderer`, `TextureFactory`),
with no missing members and no signature drift; `conversions.py` is two
one-line adapters. One inconsistency noted but not changed: `IFramebuffer` and
`IRenderPass` are the only graphics protocols not marked `@runtime_checkable`,
while the other four are. Nothing currently needs to `isinstance` them, so
changing it now would be speculative -- it belongs with slice 4, which is where
those two protocols are actually implemented.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9).


### `pyguara/graphics` iteration 4 — pipeline — awaiting approval (2026-09-06)

**Verification:** 1485/1485 tests pass; ruff clean; mypy clean.

**Correctness fixes:**
- **`Viewport.create_best_fit()` fabricated a viewport for a zero-area
  window.** The guard `window_ratio = w / h if h != 0 else 0` substituted a
  ratio of zero, which is not greater than any positive target, so it fell
  through to the letterbox branch:
  `create_best_fit(800, 0, 16/9)` returned `Viewport(x=0, y=-225, width=800,
  height=450)` -- a 450-pixel-tall viewport at a negative offset for a window
  with no height. A minimised or mid-resize window is an ordinary transient
  state, so it now yields a zero viewport. Negative dimensions do the same.
  This is the third instance of the same shape in this audit, after the camera's
  `safe_zoom = 0.001` and the DI container's swallowed errors: a zero guard
  that returns a wrong answer instead of signalling.
- **`create_best_fit()` divided by `target_aspect_ratio` with no check**, so
  zero raised `ZeroDivisionError` from inside the letterbox branch and a
  negative silently produced an inverted viewport. Unlike a minimised window
  that is a caller error, so it raises `ValueError` naming the argument.
- **`RenderGraph.passes` returned the live list.** `graph.passes.clear()`
  emptied the pipeline without releasing a single pass. It is a snapshot now,
  matching `SceneManager.children`.
- **Duplicate pass names were silent.** Both passes execute -- the list is the
  source of truth -- but `get_pass()` returns only the first and
  `remove_pass()` removes only the first, so the second is unreachable by name.
  Now logged, the same treatment `SystemManager` duplicate keys got.

**Tests:** new `tests/test_graphics_pipeline.py`, 21 tests. Neither the
viewport nor the graph had dedicated coverage. The viewport is pure arithmetic
needing no GL context, so its edge cases are cheap to pin down; the graph's
bookkeeping runs against a mocked context. Includes property-style checks that
a fitted viewport keeps its target ratio and never exceeds the window, across
four window shapes.

**Surveyed:** `framebuffer.py`, `batch.py`, `queue.py`, `render_system.py` and
the five passes need a live GL context to exercise meaningfully, so they are
covered only by the existing ModernGL integration tests. No defects found by
reading, but that is a weaker guarantee than the rest of this audit and worth
saying plainly.

**Related:** issue #16 records the `IFramebuffer`/`IRenderPass`
`runtime_checkable` inconsistency found in slice 3. Not fixed here: it turns on
whether `IRenderPass` or `BaseRenderPass(ABC)` is the real contract, which is a
design decision rather than a defect.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9), issue #16.


### `pyguara/graphics` iteration 5 — assets & effects — awaiting approval (2026-09-06)

**Verification:** 1503/1503 tests pass; ruff clean; mypy clean.
**This completes the graphics subsystem.**

**Correctness fixes:**
- **`NinePatchSprite.get_patch_rects()` produced negative source rectangles.**
  Edges wider than the texture leave the centre with negative extent, and five
  of the nine source rects came back malformed --
  `Rect(x=40, y=0, width=-32, height=40)` for `uniform(40)` on a 48px texture --
  which reach the renderer as geometry rather than as an error. The asymmetry
  is the tell: `get_dest_rects()` clamps its own input with
  `max(width, min_size)`, three lines the source side never had. Now raises,
  naming both the edges and the texture size.
- **`NinePatchMetrics` accepted negative edges.** `uniform(-5)` was fine, and
  every rect derived from it was malformed. Rejected at construction.
- **`PostProcessStack.effects` returned the live list**, so
  `stack.effects.clear()` emptied the stack without releasing a single effect.
- **Duplicate effect names were silent**, leaving the second unreachable
  through `get_effect()` and surviving `remove_effect()`.

The last two are the *same pair* fixed in `RenderGraph` one slice earlier.
`PostProcessStack` and `RenderGraph` are siblings -- an ordered list plus a
name lookup -- and carried identical defects. Fixed identically, and the
docstrings now cross-reference so the parallel is visible.

**Tests:** +18. `test_ninepatch.py` gains metrics validation, the source/
destination asymmetry, and a check that valid source rects tile the texture
exactly. New `test_post_process_stack.py` covers the stack's bookkeeping.

**Surveyed, not deeply verified:** `materials/`, `vfx/effects/` (bloom,
vignette) and the shader loading in `post_process.py` need a live GL context,
so they remain covered only by the ModernGL integration tests -- the same
caveat as slice 4. `spritesheet.py`, `atlas.py` and `animation_system.py` were
read and probed and behaved correctly on degenerate input.

### `pyguara/graphics` — SUMMARY of all five slices

| Slice | Headline defect |
| --- | --- |
| 1. Boundary | `Window` reported the requested size, not the granted one |
| 2. Components | `Box`/`Circle` hard-wired to pygame; camera zoom accepted 0 |
| 3. Backends | pygame compatibility stubs had drifted from their counterparts |
| 4. Pipeline | a zero-height window produced a 450px viewport at negative y |
| 5. Assets | nine-patch produced negative source rects |

**A pattern worth recording.** Four of the five slices turned up the same
shape: a guard that avoids a crash by returning a wrong answer.
`safe_zoom = 0.001`, `window_ratio ... else 0`, the nine-patch's missing
clamp, and the DI container's swallowed disposal errors from an earlier tier.
In every case the crash would have been easier to diagnose than the
plausible-looking garbage substituted for it.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9), issue #16.
