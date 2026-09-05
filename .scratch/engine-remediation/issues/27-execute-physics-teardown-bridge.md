# Execute the physics teardown bridge

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: 26
Audit ref: fog graduation, follows from Physics teardown bridge, ticket 15

## Question

Nothing to decide — execute the decisions recorded in [Physics teardown
bridge](15-physics-teardown-bridge.md), once [Execute the ECS lifecycle
contract](26-execute-ecs-lifecycle-contract.md) has landed `EntityDestroyed`.

**`pyguara/physics/physics_system.py`:**
- `PhysicsSystem.__init__`: subscribe `self._dispatcher.subscribe(EntityDestroyed,
  self._on_entity_destroyed)`.
- Add `self._pending_teardown: List[IPhysicsBody] = []`.
- `_on_entity_destroyed(self, event: EntityDestroyed) -> None`: read the entity's `RigidBody`
  component off `event.entity` (components are still intact at dispatch time). If
  `rb._body_handle is None`, return (silent no-op — nothing to tear down). Otherwise append
  `rb._body_handle` to `self._pending_teardown`.
- `update(dt)`: before calling `self._engine.update(dt)`, drain `self._pending_teardown` —
  call `self._engine.destroy_body(handle)` for each, then clear the list.

**`pyguara/physics/backends/pymunk_impl.py`:**
- `PymunkEngine.destroy_body(body_handle)`:
  ```python
  body = body_handle._body
  for shape in list(body.shapes):
      self.space.remove(shape)
  self.space.remove(body)
  self._bodies.pop(body.entity_id, None)
  ```
  Guard on `self.space` being set (mirrors the existing guard pattern in `add_shape`).

## Done when

- Destroying an entity with a `RigidBody` removes its body and shapes from `self.space` and
  from `self._bodies`, verified by a regression test (create entity with `RigidBody` +
  `Collider`, remove it, assert the pymunk space no longer contains the body/shapes and
  `self._bodies` no longer has the entry).
- A body's simulation stops advancing after its entity is removed (no more collision events,
  no more position updates) — a regression test steps physics after removal and asserts no
  further movement/callbacks.
- An entity removed before `PhysicsSystem.update()` ever processed it (`_body_handle is None`)
  produces no error and no phantom teardown call.
- Teardown happens via the pending-queue drain in `update()`, before `self._engine.update(dt)`
  — not synchronously inside the `EntityDestroyed` dispatch.
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

## Resolution

Executed exactly as specified. Commit `552a588`.

`PhysicsSystem.__init__` now subscribes `self._dispatcher.subscribe(EntityDestroyed,
self._on_entity_destroyed)` and adds `self._pending_teardown: List[IPhysicsBody] = []`.
`_on_entity_destroyed` reads `RigidBody` off `event.entity` (guarded with
`has_component` first, since a destroyed entity may not have physics at all),
no-ops silently if `_body_handle is None`, otherwise queues the handle.
`update(dt)` drains `self._pending_teardown` — calling `self._engine.destroy_body(handle)`
for each, then clearing the list — as the very first thing it does, before the
ECS→physics sync pass and before `self._engine.update(dt)` steps the space.
`PymunkEngine.destroy_body()` matches the ticket's snippet verbatim (already
implemented against this ticket in a prior pass of this session), with the
`isinstance(body_handle, PymunkBodyAdapter)` guard mirroring `add_shape()`'s
existing pattern in the same file.

Five new regression tests in `tests/test_physics.py` cover all of "Done when":
mock-engine tests confirm queueing is deferred (not synchronous at dispatch)
and drains before `engine.update()` (call-order assertion), confirm a
never-created body (`_body_handle is None`) produces no phantom
`destroy_body` call, and confirm an entity with no `RigidBody` at all is a
silent no-op. Two more tests exercise the real `PymunkEngine`: one calls
`destroy_body()` directly and asserts the body and its shape are both gone
from `space.bodies`/`space.shapes` and `self._bodies`; the other runs the
full `PhysicsSystem` + real `EntityManager` + real `PymunkEngine` stack
end-to-end — create entity, one `update()` to materialize the body, remove
the entity, one more `update()` to drain teardown, then assert the pymunk
body is gone from the space and a further `update()` neither errors nor
resurrects it.

`ruff check .`, `ruff format --check`, and `mypy pyguara` (216 files) all
clean; full suite green (1083 passed, up from 1078 — the 5 new tests).

No deviations, discoveries, or scope questions surfaced during execution —
the decision ticket's spec mapped onto the current codebase state
(post-ticket-26's `EntityDestroyed` and post-ticket-24's scene-owned
`EntityManager`) without needing adaptation.
