# Execute the PlatformerController/TriggerVolume logic move

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: fog graduation, follows from Decide whether to move PlatformerController/
TriggerVolume logic into Systems now, ticket 34

## Question

Nothing to decide — execute the decision recorded in [Decide whether to move
PlatformerController/TriggerVolume logic into Systems now
](34-platformer-trigger-component-logic-decision.md).

**`pyguara/physics/platformer_controller.py`:**
- Delete `move_left()`, `move_right()`, `stop_move()`, `jump()`.
- Add a `PlatformerInput` value type (`move: float = 0.0`, `jump: bool = False`) and a
  `pending_input: PlatformerInput` field on `PlatformerController` (`field(default_factory=
  PlatformerInput, init=False)`), replacing the individual `move_input`/`_jump_requested`
  write paths those methods used.
- Delete `reset_jump_state()`.
- Keep `can_jump()`, `can_wall_jump()`, `is_wall_sliding()` unchanged.

**`pyguara/physics/platformer_system.py`:**
- Add `reset_jump_state(self, controller: PlatformerController) -> None`, moving the
  method body verbatim from the component. Update `_update_ground_detection()`'s
  internal call site.
- `update()`'s per-entity loop reads `controller.pending_input` instead of calling
  `controller.move_input`/`_jump_requested` setters (the fields those methods used
  become reads off `pending_input.move`/`pending_input.jump`); clear/reset
  `pending_input` at the end of each entity's iteration the same way `move_input` is
  reset today (`controller.move_input = 0.0` at the loop's end becomes resetting
  `pending_input` to a fresh `PlatformerInput()`).

**`games/guara_falcao/systems.py`** (`PlayerControlSystem.update()`):
- Replace `controller.move_left()`/`move_right()`/`stop_move()` with
  `controller.pending_input = PlatformerInput(move=move_input, jump=jump_pressed)`
  (one assignment covers all three branches).
- `controller.is_wall_sliding()` call stays (predicate, unchanged).

**`games/guara_falcao/scenes.py`** (respawn handler, ~line 317):
- Replace `controller.reset_jump_state()` with
  `self._platformer_system.reset_jump_state(controller)`.

**`pyguara/physics/trigger_volume.py`:**
- Delete `TriggerVolume.clear()`.
- Delete `EntityTags.add_tag()`, `EntityTags.remove_tag()`.
- Keep `contains_entity()`, `matches_tags()`, `get_entity_count()`, `is_empty()`,
  `has_any_entity()`, `has_tag()`, `has_any_tag()`, `has_all_tags()` unchanged.

**`pyguara/physics/trigger_system.py`** (`clear_all_triggers()`):
- Replace `trigger_volume.clear()` with `trigger_volume.entities_inside.clear()`.

**`tests/test_trigger_volumes.py`:**
- Delete or rewrite the tests exercising `EntityTags.add_tag()`/`remove_tag()` and
  `TriggerVolume.clear()` onto direct field mutation (`.tags.add(...)`,
  `.entities_inside.clear()`), keeping equivalent coverage of the behavior, not the
  deleted method names.

**Docstrings:** update both files' module/class docstrings — they currently say "this
is legacy, ideally logic would be in a System" / "ideally these would be simple set
operations"; that's now done, so the note should reflect the current state rather than
describing it as an aspirational TODO.

## Done when

- `PlatformerController`, `TriggerVolume`, `EntityTags` carry no mutating methods —
  only the named-kept predicates.
- `games/guara_falcao` (the only game using `PlatformerController`) still plays
  correctly: movement, jump, coyote time, wall slide/jump, and the respawn reset all
  behave identically to before, verified via `games/validate_demos.py` plus the
  existing platformer/trigger test suites (updated per above, not deleted wholesale).
- New regression test: `pending_input` round-trips correctly through
  `PlatformerSystem.update()` for at least one move+jump case (there was no test
  before covering `move_left()`/`jump()`'s effect through to `PlatformerSystem`
  end-to-end; add one alongside the rewrite rather than only testing the deleted
  method's replacement in isolation).
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

## Resolution

Executed as specified, no deviations found.

`PlatformerController` gained `PlatformerInput` (a plain dataclass, `move: float`/
`jump: bool`) and a `pending_input` field; lost `move_left()`/`move_right()`/
`stop_move()`/`jump()`/`reset_jump_state()`. `PlatformerSystem.update()`'s per-entity
loop now translates `pending_input` into the existing internal fields
(`move_input`/`facing_right`/`_jump_requested`/`jump_buffer_timer`) at the top of
each iteration, then resets `pending_input` to a fresh `PlatformerInput()` at the
end -- same place `move_input = 0.0` used to reset. `reset_jump_state()` moved onto
`PlatformerSystem` unchanged, called from both its internal ground-detection call
site and `games/guara_falcao/scenes.py`'s respawn handler (now
`self._platformer_system.reset_jump_state(controller)`).

`PlayerControlSystem.update()` (`games/guara_falcao/systems.py`) collapsed its
three-branch `move_left()`/`move_right()`/`stop_move()` dispatch into one
`controller.pending_input = PlatformerInput(move=move_input, jump=jump_pressed)`
assignment. One thing preserved deliberately, not fixed: the original code's
`if controller._jump_requested:` guard around firing `PlayerJumpedEvent` was
already dead -- `jump()` set `_jump_requested = True` unconditionally, so the guard
was always true whenever `jump_pressed` was true. Replaced with `if jump_pressed:`
directly, identical observable behavior (including the pre-existing quirk that a
jump event fires even when `PlatformerSystem` will go on to reject the jump
attempt) -- not this ticket's job to fix, per the map's "don't widen scope"
standing preference.

`TriggerVolume.clear()` and `EntityTags.add_tag()`/`remove_tag()` deleted;
`TriggerSystem.clear_all_triggers()` now does `trigger_volume.entities_inside
.clear()` directly. Both components' docstrings updated to describe their current
data-plus-predicates shape rather than the old "ideally this would move" language.

Test suites rewritten onto the new shape (not deleted): `test_platformer_controller
.py` gained `test_pending_input_default`/`test_pending_input_can_be_set` (component-
level), `test_pending_input_reset`/`test_reset_jump_state`/
`test_jump_intent_translates_to_buffer` (system-level, the first end-to-end coverage
of intent flowing through to buffered jump state -- didn't exist before);
`test_trigger_volumes.py`'s `test_clear`/`test_add_tag`/`test_remove_tag` now assert
against direct field mutation. Full suite green (1122 passed), all 4 demos verified
via `games/validate_demos.py`, `ruff check .` and `mypy pyguara` (217 files) clean.
Commit `75e41be`.
