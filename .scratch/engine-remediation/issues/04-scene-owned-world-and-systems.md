# Scene-owned world and SystemManager

Type: grilling
Status: resolved
Blocked by: —
Audit ref: ECS-1 (critical)

## Question

The ownership call was made at charting time: **the Scene owns its world and its
SystemManager**; the container provides a factory, not a global instance. This ticket
specifies what that actually means in code.

Today `Scene.__init__` (`scene/base.py:24`) creates its own `EntityManager`, while bootstrap
creates a *different* one, registers it in DI, and hands it to `SteeringSystem`, `AISystem`,
`AudioSourceSystem` and `AnimationSystem`. Those four run every fixed step against a world no
scene will ever populate:

```
scene EM is container EM:      False
AISystem's EM is container EM: True
entities visible to AISystem:  0
entities in scene:             1
```

`editor/layer.py:52` already routes around this by reaching through
`scene_manager.current_scene.entity_manager`.

## To resolve

- What replaces `container.register_instance(EntityManager, ...)` — a factory, a scoped
  lifetime, or nothing at all?
- How do engine systems get registered into a scene's `SystemManager`? Auto-registered at
  `on_enter` from a declared default set, or opted into by the scene?
- What is the priority contract between engine systems and game systems? Bootstrap currently
  hardcodes 150/200/250/300; a scene adding its own needs to know where it sits.
- Per-scene system state — `SteeringSystem._wander_targets` keyed by entity id, never pruned —
  now has scene lifetime. Does the system get a reset hook on `on_enter`/`on_exit`?
- No demo uses `SystemManager` at all; they hold systems as fields and update them by hand.
  Does the migration make `SystemManager` mandatory, or stay optional?
- What happens on `on_pause` / `on_resume` for a stacked scene — do its systems keep ticking?

## Constraints

Scene isolation is the reason this option was chosen: a pause-menu scene pushed over gameplay
must not see gameplay entities. Any spec that reintroduces a shared world has missed the point.

## Why this is unblocked

The audit is sufficient input for the discussion. Implementing the answer wants a booting
engine (Repair the composition root, Bootstrap smoke test), but deciding it does not — so this
sits on the frontier and can run in parallel with the critical fixes.

## Answer

Grilled live with the dev, one sub-question at a time. Decisions:

1. **EntityManager in DI: nothing.** The `container.register_instance(EntityManager, ...)`
   registration is removed entirely. No global `EntityManager` exists — anything that needs
   one goes through `scene_manager.current_scene.entity_manager` (as `editor/layer.py:52`
   already does), or is itself scene-owned.

2. **Engine systems: auto-registered by the base `Scene`**, but in `resolve_dependencies()`,
   not `__init__`. `__init__` only builds `entity_manager` and an empty `system_manager` —
   `AudioSourceSystem` needs `audio_system`/`res_manager` from the DI container, which isn't
   available until `resolve_dependencies(container)` runs. That method builds and registers
   all four default systems (`SteeringSystem`, `AISystem`, `AudioSourceSystem`,
   `AnimationSystem`) against `self.entity_manager`.

3. **Priority contract: a reserved band.** 100-399 is reserved for engine-registered systems
   (Steering=150, AI=200, Audio=250, Animation=300, unchanged). Game/scene systems default to
   >=500 by convention. Document the band on `Scene`/`SystemManager`.

4. **Per-system state reset: `SystemManager.cleanup()` on scene exit.** `SteeringSystem`
   implements `CleanupSystem.cleanup()` to clear `_wander_targets` wholesale — the system
   dies with the scene, so per-entity tracking becomes moot. The dead, never-called
   `cleanup_entity(entity_id)` method is deleted. `Scene.on_exit()` (or a base hook every
   subclass goes through) calls `self.system_manager.cleanup()`.

5. **SystemManager becomes mandatory, demos migrate.** Every scene's own game systems
   (physics, gameplay logic, camera-follow, etc.) must register onto `self.system_manager`
   too, not just the four engine defaults — no more hand-rolled system fields ticked by hand
   in `fixed_update`/`update` (the pattern `games/guara_falcao/scenes.py` uses today, where a
   `SystemManager` is registered in DI via `guara_falcao/bootstrap.py:71` but never touched).
   This adds a requirement onto the existing **Demo migration** fog item (below) rather than
   opening a new ticket — full scoping still waits on the render architecture.

6. **Pause semantics: both gates.** `SceneManager`'s existing `pause_below` mechanism already
   skips calling `fixed_update()`/`update()` entirely for scenes below the stack top
   (`scene/manager.py:184-246`), so a paused scene's systems already stop ticking for free.
   *Additionally*, `Scene.on_pause()` calls `self.system_manager.set_enabled(False)` and
   `on_resume()` calls `set_enabled(True)` as a second, independent gate.

**Constraint preserved:** no shared world — each scene keeps its own `EntityManager` and
`SystemManager`; nothing here reintroduces a global instance.

Not implemented in this session — this ticket is a decision, not a `task`. Implementation is
future work per the ticket-type rule (planning by default; only `task` tickets execute).
