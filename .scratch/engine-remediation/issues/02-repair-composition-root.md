# Repair the composition root

Type: task
Status: resolved
Blocked by: 01
Audit ref: BOOT-1, BOOT-2, BOOT-3 (all critical)

## Question

Nothing to decide — execute. Three defects that together mean the engine's documented entry
point has never run.

**BOOT-1 — the default backend takes the OpenGL render path and crashes on frame one.**
`bootstrap.py:175` registers a no-op `PygameRenderGraph` under the `RenderGraph` key so that
game code using lighting "degrades gracefully" on pygame. But `application.py:80-86` treats
any resolvable `RenderGraph` as proof the GL pipeline exists and routes to
`_render_with_graph()`. The stub's `get_or_create()` returns `None`:

```
RenderGraph resolved as: PygameRenderGraph
AttributeError: 'NoneType' object has no attribute 'bind'   (application.py:262)
```

Branch on backend identity, not on mere resolvability. Note the knock-on: `_render_direct()`
is the only path that calls `window.clear()` and `window.present()` in the right order, and it
is currently unreachable in the shipped wiring.

**BOOT-2 — `python main.py` dies before a window opens.** `main.py:20` calls
`BootScene("level_1", dispatcher)`; `BootScene.__init__` takes only the dispatcher. This is
the exact command documented under "Running the Engine" in CLAUDE.md.

**BOOT-3 — the component registry is registered twice and the empty one wins.**
`bootstrap.py:217` registers the populated global registry (18 core components).
`bootstrap.py:300-301` then constructs a fresh `ComponentRegistry()` and registers it under
the same key. `SceneSerializer` auto-wires to the empty one, so `load_scene()` skips every
component and still returns `True`:

```
save_scene(scene_with_transform) -> True
load_scene(fresh_scene)          -> True
entity 06ef756e components: []
```

A silent data-loss path with a success return code.

## Done when

- All three fixed, each with a regression test.
- `create_application()` returns an `Application` whose `_render()` completes without raising
  on the pygame backend.
- `python main.py` starts.
- `container.get(ComponentRegistry)` returns a registry containing all 18 core components.

## Answer

**BOOT-1** (`pyguara/application/application.py`): `Application.__init__` now checks
`isinstance(candidate, RenderGraph)` before assigning `self._render_graph` — branching on
backend identity instead of mere resolvability, per the ticket's direction. The
`PygameRenderGraph` stub resolves under the same DI key but is not a `RenderGraph` instance,
so on the default Pygame backend `self._render_graph` stays `None` and `_render()` correctly
falls through to `_render_direct()` (which is the only path that calls `window.clear()` /
`window.present()` in the right order).

**BOOT-2** (`main.py`): every demo scene's `__init__` (including `BootScene`) takes only
`event_dispatcher` — no `name` parameter exists on that constructor. Fixed the call site:
`BootScene(dispatcher)` instead of `BootScene("level_1", dispatcher)`.

**BOOT-3** (`pyguara/application/bootstrap.py`): deleted the second `ComponentRegistry()`
construction + registration (was lines 300-301) that clobbered the populated registry
registered earlier in the same `_setup_container()` call with an empty one.

Regression tests added in `tests/integration/test_bootstrap.py` (6 tests, `@pytest.mark.integration`,
run under `SDL_VIDEODRIVER=dummy`): registry has all 18 components, the Pygame backend
doesn't resolve a real `RenderGraph`, `_render()` completes without raising, `BootScene`
constructs with the dispatcher-only signature, a full `create_application()` + `BootScene` +
`app.run()` loop ticks successfully, and `python main.py` boots as a subprocess without
exiting early. Verified each of the BOOT-1/BOOT-3 tests (and the new `main.py` subprocess
test) fails against the pre-fix code via `git stash`. Full suite: 1033 passed, `ruff check`
and `mypy pyguara` clean.
