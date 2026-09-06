# Decide whether to move PlatformerController/TriggerVolume logic into Systems now

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
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

## Resolution

Stands alone, resolved now — doesn't wait for the broader Component contract fog
patch. Verified via caller grep first: `PlatformerController`'s mutators are already
only called from Systems (`PlatformerSystem` internally, `games/guara_falcao/
systems.py`'s `PlayerControlSystem` externally), and `TriggerVolume`'s query methods
are only called from `TriggerSystem` internally — so the audit's complaint isn't
uncontrolled access, it's that the mutating code *text* lives on the component instead
of the System that already exclusively drives it.

**Governing principle** (for future components, not just these two): mutating logic
moves into a System when a System exists to own it; a trivial single-field wrapper
mutation with no natural System destination gets deleted and inlined at the call site
instead of relocated. Pure, side-effect-free predicate methods stay on the component
either way — read-only means there's no ownership question to resolve, so deleting
them (forcing callers to re-derive the boolean expression by hand) is a readability
regression for zero encapsulation gained. `_allow_methods: bool = True` stays on both
components — they still carry methods, just none that mutate without a System's
involvement.

**`PlatformerController`:**
- `move_left()`/`move_right()`/`stop_move()`/`jump()` — deleted. New `pending_input:
  PlatformerInput` field (a small value type: `move: float`, `jump: bool`) replaces
  them; `PlayerControlSystem` writes it directly (`controller.pending_input =
  PlatformerInput(move=-1.0, jump=True)`), `PlatformerSystem` reads it off each entity
  in its existing per-entity loop. Rejected: a `PlatformerSystem`-owned
  `dict[EntityId, PlatformerInput]` populated via `set_input()` (real state was already
  being handed to the component this way in effect — decided that's fine, ain't broke)
  and a `Mapping` parameter threaded through `update()` (invents an orchestration
  contract this pre-alpha engine's single caller doesn't need yet).
- `reset_jump_state()` — moves to `PlatformerSystem.reset_jump_state(controller)`.
  Called both internally (`_update_ground_detection`) and externally (the scene's
  respawn handler, `games/guara_falcao/scenes.py:317`, which already writes
  `controller.is_grounded = False` as a plain field on the very next line). Not
  inlined at both call sites like `EntityTags.add_tag()` was, because it resets 5
  coordinated fields (`_jump_requested`, `jump_buffer_timer`, `coyote_timer`,
  `_can_double_jump`, `_jump_used`) — duplicating that list risks silent drift if a
  future field joins the group and only one site gets updated.
- `can_jump()`, `can_wall_jump()`, `is_wall_sliding()` — kept, pure predicates.

**`TriggerVolume`:**
- `contains_entity()`, `matches_tags()`, `get_entity_count()`, `is_empty()`,
  `has_any_entity()` — kept, pure predicates. `matches_tags()` in particular
  encapsulates real, non-trivial-to-rederive semantics ("empty filter = accept all").
- `clear()` — deleted. Only caller is `TriggerSystem.clear_all_triggers()`, which
  already mutates `entities_inside`/`active` as plain fields elsewhere
  (`_on_trigger_enter`/`_on_trigger_exit`); `clear()` was a single-line wrapper
  (`entities_inside.clear()`) with no coordinated invariant, same shape as
  `EntityTags.add_tag()`. Caller now does `entity.get_component(TriggerVolume)
  .entities_inside.clear()` directly.

**`EntityTags`** (verified zero production callers anywhere — only exercised by
`tests/test_trigger_volumes.py`, not constructed by any game or engine code today):
- `add_tag()`, `remove_tag()` — deleted; no natural System owns tag mutation (tagging
  isn't a per-frame process), and neither wraps more than one `set` call. Callers
  mutate `.tags` (a plain `Set[str]`) directly.
- `has_tag()`, `has_any_tag()`, `has_all_tags()` — kept, pure predicates.

Lands as an execution ticket, not fixed here (this map's tickets are decisions, not
deliverables) — see [Execute the PlatformerController/TriggerVolume logic
move](40-execute-platformer-trigger-logic-move.md).
