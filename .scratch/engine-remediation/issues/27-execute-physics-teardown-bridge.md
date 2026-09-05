# Execute the physics teardown bridge

Type: task
Status: open
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
