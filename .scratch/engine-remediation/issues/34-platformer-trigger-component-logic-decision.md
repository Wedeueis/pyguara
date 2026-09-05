# Decide whether to move PlatformerController/TriggerVolume logic into Systems now

Type: grilling
Status: open
Blocked by: —
Audit ref: external code review, verified against the codebase 2026-09-05

## Question

An external code review flagged `PlatformerController` (`pyguara/physics/
platformer_controller.py`) and `TriggerVolume`/`EntityTags`
(`pyguara/physics/trigger_volume.py`) for carrying logic methods (`move_left()`,
`jump()`, `can_jump()`, `reset_jump_state()`; `contains_entity()`, `matches_tags()`,
`add_tag()`, etc.) instead of being pure data, each bypassing `BaseComponent`'s
data-only warning via `_allow_methods: bool = True`. Verified true, but not a hidden
bug: both classes' own docstrings already say "this is legacy, ideally logic would be
in a System," and `_allow_methods` is a real, documented escape hatch already built
into `BaseComponent` for exactly this case.

This overlaps the map's existing **Component contract** fog patch (`Not yet
specified`): "Whether `StrictComponent` gets adopted, `_allow_methods` gets removed,
and `slots=True` gets applied across the 109 dataclasses..." That fog patch is broader
(engine-wide, all 109 dataclasses) and still un-graduated. This ticket is narrower and
already precise enough to state: specifically for these two components, should their
logic move into `PlatformerSystem`/`TriggerSystem` now, independent of when (or
whether) the broader Component contract question resolves?

- Does moving this logic now stand alone, or does it need the broader Component
  contract answer first (e.g., if `StrictComponent` adoption changes how systems are
  expected to mutate component state, doing this migration twice would be wasted work)?
- If it stands alone: `PlatformerController` methods currently read/write internal
  jump-timer state (`coyote_timer`, `jump_buffer_timer`, `_jump_used`, etc.) that
  `PlatformerSystem` already manages per the class's own "Internal state (managed by
  PlatformerSystem)" comment — is the intent that callers stop calling
  `controller.jump()` directly and instead route through some input-to-system path
  (queuing a jump request the system consumes), or something else?
- `TriggerVolume.matches_tags()`/`contains_entity()` are pure queries with no side
  effects (unlike `PlatformerController`'s state-mutating methods) — does the same
  disposition apply to both, or do side-effect-free query methods get a different
  answer than state-mutating ones?
- Is this worth doing at all for a pre-alpha engine given both components already
  self-document as legacy and work correctly today, or does it wait until the broader
  Component contract ticket makes it moot either way?
