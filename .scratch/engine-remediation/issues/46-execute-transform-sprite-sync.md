# Execute the Transform-Sprite position combination

Type: task
Status: open
Blocked by: —
Audit ref: fog graduation, follows from Decide how Transform position syncs to
Sprite for rendering, ticket 44

## Question

Nothing to decide — execute the decision recorded in [Decide how Transform position
syncs to Sprite for rendering](44-transform-sprite-sync-decision.md).

**`pyguara/graphics/pipeline/render_system.py`:**
- `submit(self, item: Renderable, position: Optional[Vector2] = None) -> None`: use
  `position if position is not None else item.position` when building the
  `RenderCommand`. All other fields (`texture`, `layer`, `z_index`, `rotation`,
  `scale`, `material`) unchanged.

**`pyguara/scene/base.py`** (`Scene.render()`'s default loop):
- For each visible `Sprite`, check `entity.has_component(Transform)`. If present:
  `world_position = entity.get_component(Transform).position + sprite.position`.
  If absent: `world_position = sprite.position` (today's behavior, standalone
  sprite). Pass `world_position` as `submit()`'s new `position` argument. Do not
  write back to `sprite.position`.

## Done when

- A regression test: an entity with both `Transform` (position `P`) and `Sprite`
  (offset `O`) submits at world position `P + O`, verified via the `RenderCommand`
  the (real or headless) backend receives — not by reading `sprite.position` back
  (it must be unchanged after render, proving no mutation happened).
- A second test: an entity with only `Sprite` (no `Transform`) still submits at
  `sprite.position` unchanged — the standalone case keeps working exactly as today.
- A third test: moving `Transform.position` between two frames (e.g. simulating a
  physics step) changes the submitted world position on the next `render()` call,
  without requiring any new system tick — proving the combination happens live at
  submission time, not from stale cached state.
- All 4 games using `get_entities_with(Transform, Sprite)` for hand-rolled rendering
  (`asset_pipeline`, `input_events`, `ecs_mental_model`) are unaffected (they don't go
  through `Scene.render()`'s default path, still out of scope per **Demo migration**).
- `ruff check .` and `mypy pyguara` stay clean; full suite green.
