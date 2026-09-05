# Execute Scene-owned world, SystemManager, and RenderSystem wiring

Type: task
Status: open
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
