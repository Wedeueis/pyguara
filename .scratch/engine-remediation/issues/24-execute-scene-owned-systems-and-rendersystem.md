# Execute Scene-owned world, SystemManager, and RenderSystem wiring

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: ECS-1 (critical), follows from Scene-owned world and SystemManager (ticket 04) and
RenderSystem wiring (ticket 13)

## Question

Nothing to decide — execute the decisions recorded in [Scene-owned world and
SystemManager](04-scene-owned-world-and-systems.md) (never executed — no task ticket existed
for it until now) and [RenderSystem wiring](13-rendersystem-wiring.md). Combined into one
ticket because both land in `Scene.resolve_dependencies()` as the same per-scene-construction
pattern.

**`pyguara/application/bootstrap.py`:**
- Remove `container.register_instance(EntityManager, ...)` if present, and the
  `system_manager = SystemManager(); container.register_instance(SystemManager, system_manager)`
  block (`bootstrap.py:223-224`). No global `EntityManager`/`SystemManager` in DI.
- `IRenderer` backend stays a DI singleton — only its `RenderSystem` wrapper becomes per-scene.

**`pyguara/scene/base.py`:**
- `Scene.__init__` builds `self.entity_manager` (unchanged) and an empty `self.system_manager`
  (no engine systems yet — those need container-resolved dependencies).
- `Scene.resolve_dependencies(container)` builds and registers, against `self.entity_manager`:
  - The four engine systems at their existing priorities: `SteeringSystem` (150), `AISystem`
    (200), `AudioSourceSystem` (250, needs `audio_system`/`res_manager` from `container`),
    `AnimationSystem` (300).
  - `self.camera = Camera2D(width, height)` (dimensions from the resolved `WindowConfig` /
    backend).
  - `self.render_system = RenderSystem(container.get(IRenderer))`.
  - Document the reserved priority band (100-399 engine, >=500 game/scene) on `Scene` and
    `SystemManager`.
- `Scene.render()` stops being `@abstractmethod`. Default implementation: iterate entities
  with a `Renderable`-compliant component (`Sprite` today), `self.render_system.submit(...)`
  each, then `self.render_system.flush(self.camera)`. Subclasses override only to add manual
  draws, calling `super().render(...)` first.
- A base hook on scene exit (`on_exit()` or equivalent) calls `self.system_manager.cleanup()`.
  `SteeringSystem` implements `CleanupSystem.cleanup()` to clear `_wander_targets` wholesale;
  delete the dead, never-called `cleanup_entity(entity_id)` method.
- `Scene.on_pause()` calls `self.system_manager.set_enabled(False)`; `on_resume()` calls
  `set_enabled(True)`. (`SceneManager`'s existing `pause_below` skip already stops
  `fixed_update()`/`update()` calls for scenes below the stack top — this is the second,
  independent gate per ticket 04's decision.)

**`pyguara/application/application.py`:**
- `_render_direct()` / `_render_with_graph()` keep calling `scene_manager.render(...)`
  unchanged — the change is entirely inside what `Scene.render()` now does by default.

## Done when

- No `EntityManager`/`SystemManager` singleton exists in DI; `bootstrap.py` no longer
  constructs either.
- A scene's engine systems, camera, and render system are all live after
  `resolve_dependencies()` runs, before `on_enter()`.
- `Scene.render()` is concrete; at least one demo relies on the default instead of overriding
  it, to prove the default path actually draws something.
- `SystemManager.cleanup()` runs on scene exit; pause/resume toggles `set_enabled()`.
- Regression tests cover: engine systems see the scene's own entities (not empty/wrong world);
  RenderSystem submission + flush draws a sprite on both backends under test; cleanup empties
  `SteeringSystem._wander_targets`; pause disables system ticking via `set_enabled`.
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

**Out of scope here:** migrating each demo's hand-rolled system fields onto `SystemManager`
(that's the *Demo migration* fog item — demos may keep their manual fields for now, they just
gain the four engine systems'/render system's auto-registration for free); the ModernGL shape
shader work (separate ticket).

## Resolution

Executed as specified, with one deliberate deviation and two necessary consequential fixes.
Commit `a934c8f`.

**Wiring landed as specified.** No global `EntityManager`/`SystemManager` in DI;
`Scene.__init__` builds an empty `system_manager`; `resolve_dependencies()` builds and
registers the four engine systems at their existing priorities (100-399 band, documented on
`Scene`), then `camera`/`render_system`/`prefab_factory` (the last wasn't named by this
ticket but had to move too — see below) — all live before `on_enter()`. `Scene.render()` is
concrete. `SteeringSystem.cleanup()` replaces `cleanup_entity()`. `SceneManager` ticks each
active scene's own `system_manager.update(fixed_dt)` (nothing global left to tick) and
centrally calls `cleanup()`/`set_enabled()` at exit/pause/resume — done in `SceneManager`
itself rather than trusting `on_exit()`/`on_pause()`/`on_resume()` overrides to call
`super()`, since every current demo scene already overrides at least one of those without
doing so; confirmed this doesn't break the real push/pop demo pattern (guara_falcao/
protocolo_bandeira/true_coral all construct a *fresh* scene instance and re-register it on
every `push_scene()`, rather than reusing one that already had its `system_manager` cleaned
up on a prior exit).

**Deviation from "Done when": no demo was migrated onto the default `render()` path.**
Instead, `tests/integration/test_scene_owned_systems.py` proves it with a purpose-built test
scene against the real `create_application()`/`create_headless_application()` bootstrap.
Investigating turned up why no real demo could stand in for this without also being a demo
migration (explicitly out of scope): none of the 9 demos use the engine's own `Sprite`
component at all — each has its own demo-specific sprite class — and, per the next finding,
the engine's `Sprite` couldn't have been added to a real entity anyway.

**Found and fixed, necessary for the default `render()` path to be real, not just
type-check:** `pyguara.graphics.components.sprite.Sprite` — the "Renderable-compliant
component (Sprite today)" this ticket's design is built on — didn't conform to the
`Component` protocol (no `entity`/`on_attach`/`on_detach`). `entity.add_component(Sprite(...))`
would have raised `AttributeError` at the `on_attach` call inside `Entity.add_component()`,
and `entity_manager.get_entities_with(Sprite)` didn't even type-check (mypy caught this
immediately). Nothing currently adds it as a real ECS component, so this was silently
unexercised until this ticket tried to build the first real consumer. Fixed by making
`Sprite` inherit `BaseComponent` with a `__post_init__`, the same pattern every other
dataclass component in the engine already uses.

**Found and fixed, a second global-service consumer the ticket's text didn't name:** three
sandbox dev tools (`EntityInspector`, `PhysicsDebugger`, `TransformGizmo`) resolved a global
`EntityManager` from the container at construction time — exactly the singleton this ticket
removes. `create_sandbox_application()` would have raised `ServiceNotFoundException` the
moment tools were constructed. Fixed with a shared `_entity_manager` property on the `Tool`
base class, reaching through `SceneManager.current_scene.entity_manager` on every access
instead of caching once — the same pattern `editor/layer.py` already used for exactly this
reason, per ticket 04's own text ("anything that needs one goes through
`scene_manager.current_scene.entity_manager`").

**Found and fixed, the same category of gap ticket 21 hit:** moving `AudioSourceSystem`'s
and `PrefabFactory`'s construction into `Scene.resolve_dependencies()` means every scene
now needs `IAudioSystem`, `ComponentRegistry`, and `PrefabCache` resolvable from whatever
container built it — the shared engine bootstrap has these, but none of the 9
`games/*/bootstrap.py` copy-paste files did. Confirmed empirically that all 9 would raise
`ServiceNotFoundException` the instant their first scene tried to register. Patched all 9
the same minimal way (register the three services before their `SceneManager` registration)
and `tests/integration/test_app_flow.py`'s hand-rolled container fixture, which had the
identical gap. Not otherwise touched — the same ~650 LOC **Bootstrap collapse** already
tracks for replacement.

Full suite green (1064 passed), `ruff check .` and `mypy pyguara` clean.
