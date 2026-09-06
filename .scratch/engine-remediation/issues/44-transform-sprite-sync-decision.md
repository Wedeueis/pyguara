# Decide how Transform position syncs to Sprite for rendering

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: found during Decide how fixed-timestep render interpolation should work,
ticket 37 — a missing prerequisite, not that ticket's question

## Question

`RenderSystem.submit(item: Renderable)` reads `item.position`. `Scene.render()`'s
default submission path (per *RenderSystem wiring*, ticket 13) submits every visible
`Sprite` component directly — so rendering reads `Sprite.position`, a field the
component owns separately from `Transform.position` (per its own docstring: "Absolute
world position for standalone sprites... Relative offset when attached to an entity
with Transform... Combined with entity Transform for final rendering position").

Verified no code anywhere actually performs that combination today: the only match
for a `sprite.position = transform.position`-shaped sync is a comment inside a
docstring example in `EntityManager.get_components()`, never executed. None of the
four engine systems `Scene.resolve_dependencies()` auto-registers (Steering, AI,
AudioSource, Animation) touch it. The one demo drawing from `transform.position`
directly (`ecs_mental_model`) bypasses `RenderSystem`/`Sprite` via hand-rolled
rendering predating the `create_application()` migration — not evidence this is
solved for the real path.

So today, any `Transform`-driven entity (physics, steering, the platformer
controller) submitted through `Scene.render()`'s default path renders at whatever
`Sprite.position` last happened to be — which nothing currently updates. This is a
gap in the already-executed *RenderSystem wiring*/*Scene-owned world and
SystemManager* work, not something either of those tickets' Answers actually
addressed.

- Is `Sprite.position` meant to be hand-set by game code every frame (making the
  docstring's "combined with Transform" language aspirational/stale, not a real
  requirement), or does the engine need to own this sync?
- If the engine owns it: a new `TransformSyncSystem` (engine system, likely in the
  100-399 priority band alongside Steering/AI/AudioSource/Animation, running after
  whatever moves `Transform.position` each fixed step but before `Scene.render()`
  reads `Sprite.position`)? Or does `RenderSystem.submit()` take an entity and read
  `Transform.position` directly when present, falling back to `Sprite.position` only
  for standalone sprites with no `Transform`?
- Does this sync run at fixed-update rate (once per physics step, matching when
  `Transform.position` actually changes) or variable rate (once per rendered frame)?
  This is the same question *Decide how fixed-timestep render interpolation should
  work* (ticket 37) needs answered first — that ticket is blocked on this one's
  Answer, not the reverse, since interpolation only makes sense once there's a real
  sync point to interpolate within.
- Scope check: does this affect any of the map's already-executed tickets (*Scene-
  owned world and SystemManager*, *RenderSystem wiring*) enough to reopen them, or is
  it purely additive (a new system to register, no existing decision was wrong)?

## Resolution

Re-reading `Sprite`'s own docstring changed the shape of the fix: `Sprite.position`
is documented as a **relative offset when attached to an entity with Transform** —
"combined with entity Transform for final rendering position" — not something that
should simply become `Transform.position`. A naive sync that overwrote
`sprite.position` every frame would silently destroy any offset a game set, every
tick — the same class of bug as the Checkbox ticket (mutating stored component data
as an incidental side effect of an operation that should be a pure read).

**No `TransformSyncSystem`.** Checked the actual tick order:
`SceneManager.fixed_update()` runs `scene.system_manager.update(fixed_dt)` (the four
engine systems, priorities 150-300) *before* `scene.fixed_update(fixed_dt)` — and
physics/the platformer controller currently run inside that latter, per-demo
override, not through `SystemManager` at all (per the still-open **Demo migration**
fog). A sync system living in `SystemManager` would run before physics finalizes
`Transform.position` for the tick — a guaranteed one-frame lag — and would need a
priority number that only becomes correct once Demo migration eventually moves
physics onto `SystemManager` too. Rejected as fragile: it couples this decision to
fog that hasn't resolved yet.

**Decided: compute the combination at submission time**, inside `Scene.render()`'s
already-decided default loop (ticket 13), which runs once per rendered frame, always
after all of that tick's fixed-update work has completed — correct order by
construction, no priority number to get right, regardless of where physics/platformer
currently live. `RenderSystem.submit()` gains an optional
`position: Optional[Vector2] = None` parameter (defaults to `item.position`, so every
existing caller is unaffected). `Scene.render()`'s loop computes
`transform.position + sprite.position if entity.has_component(Transform) else
sprite.position` and passes it through — `sprite.position` itself is never written
back to, preserving offset semantics.

**Purely additive, doesn't reopen *Scene-owned world and SystemManager* or
*RenderSystem wiring*** — `RenderSystem.submit()`'s new parameter defaults to
today's exact behavior, and `Scene.render()`'s loop is extended, not restructured;
both tickets' actual decisions stand unchanged.

This also resolves the blocker on [Decide how fixed-timestep render interpolation
should work](37-fixed-timestep-interpolation-decision.md) — the submission-time
combination formula is exactly the hook point interpolation needs (an
alpha-lerped position substitutes for `transform.position` in the same formula).
Graduated that fog patch back into a fresh ticket: [Decide how fixed-timestep render
interpolation should work, now that Transform-Sprite sync exists
](45-fixed-timestep-interpolation-decision-v2.md).

Lands as [Execute the Transform-Sprite position combination
](46-execute-transform-sprite-sync.md).
