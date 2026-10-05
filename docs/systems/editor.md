# Developer Tools

PyGuara ships an in-game **developer overlay** (`pyguara.tools`) drawn on the
engine's own backend-agnostic `UIRenderer` -- no external GUI toolkit. It is a
*debug and inspection* surface. A full scene-authoring application (level
editor, animation editor, agentic authoring harness) is tracked separately as
[#53](https://github.com/Wedeueis/pyguara/issues/53).

> An earlier Dear ImGui editor (`pyguara/editor`) was removed: its pygame
> integration hard-imports `OpenGL.GL`, PyOpenGL was never a dependency, so it
> had never executed. Its useful parts were rebuilt as the tools below.
>
> A **second**, working ImGui layer now exists beside them --
> [the ImGui editor layer](#the-imgui-editor-layer) -- drawing through the
> engine's own `moderngl` context instead of PyOpenGL. The two are
> independent: attaching the editor changes nothing about the overlay, and
> the overlay remains the only dev surface on the Pygame backend.

## Enabling the overlay

`SandboxApplication` wires the overlay in automatically:

```python
from pyguara.application.bootstrap import create_sandbox_application

app = create_sandbox_application()
app.run(MyScene("main", app._event_dispatcher))
```

Press **F12** to toggle the whole overlay, then a function key per tool.

| Key | Tool | Purpose |
| --- | --- | --- |
| F1 | `PerformanceMonitor` | FPS, frame timing, counts |
| F2 | `EntityInspector` | Inspect + live-edit the selected entity's components |
| F3 | `EventMonitor` | Rolling log of recent engine events |
| F4 | `PhysicsDebugger` | Collision shape wireframes |
| F5 | `HierarchyTool` | List scene entities, click to select |
| F6 | `ConfigInspector` | Live-edit `GameConfig`, `S` to save |
| F7 | `AssetsTool` | Browse resources, spawn entities from data |
| F8 | `ShortcutsPanel` | This table, in-game (read live from the `ToolManager`) |
| F9 | `TransformGizmo` | Position/rotation/scale handles on the selected entity; `Q`/`W`/`E` switch mode |

`ShortcutsPanel` builds its table from `ToolManager.iter_shortcuts()` at
render time, so it stays in step with whatever `SandboxApplication`
registered rather than a hand-kept copy.

> **Screen-space only.** `TransformGizmo` and `PhysicsDebugger` currently
> draw and hit-test using `Transform.position` as a *screen* coordinate --
> no camera transform. They line up only with the camera at the origin at
> zoom 1. The world-to-screen unification (issue #23) is the fix.

## Hierarchy + Inspector

`HierarchyTool` lists every entity in the active scene and publishes the
clicked one as `hierarchy.selected_entity`. `EntityInspector` takes a
`selection_provider` and follows it:

```python
hierarchy = HierarchyTool(container)
inspector = EntityInspector(
    container, selection_provider=lambda: hierarchy.selected_entity
)
```

With no `selection_provider`, `EntityInspector` runs standalone and **TAB**
cycles through entities instead.

The inspector reflects each component's fields. Fields of an editable type --
`bool`, `int`/`float`, `Enum`, `Vector2`, `Color`, or a nested dataclass of
those -- render as click-to-edit rows that write straight back onto the live
component (a number row steps down on its left half, up on its right;
`bool` toggles; `Enum` cycles). Other field types show read-only. The
dispatch lives in `pyguara.tools.tweakable` and is shared with
`ConfigInspector`.

## Assets browser

`AssetsTool` lists what `ResourceManager.index_directory()` has mapped and
what is currently loaded. Select a `DataResource` (a `.json` data file) to
get a read-only preview and two actions:

* **Spawn into Scene** -- creates an entity, attaches a `ResourceLink`, and
  for every `{"ComponentName": {...}}` entry whose name is in the shared
  `ComponentRegistry`, builds that component via `registry.create(...)` --
  the same path `SceneSerializer` uses when loading a scene. Unregistered
  keys and components that fail to build are skipped with a warning.
* **Reload** -- `ResourceManager.reload(path)`, re-reading the file and its
  `.meta` sidecar.

Scene save/load is available programmatically through `SceneSerializer`
(`save_scene` / `load_scene`); the overlay no longer exposes it as a menu --
that belongs to #53. `EntityManager.clear()` is the supported way to empty a
world before reloading (it fires `subscribe_entity_removed` callbacks and
flushes cached queries).

## Writing a custom tool

Subclass `Tool` and register it. Draw with the `UIRenderer` primitives
(`draw_rect`, `draw_line`, `draw_circle`, `draw_polygon`, `draw_text`,
`draw_texture`) -- never a GUI library.

```python
from pyguara.tools.base import Tool
from pyguara.graphics.protocols import UIRenderer
from pyguara.common.types import Color, Rect, Vector2


class SpawnCounter(Tool):
    def __init__(self, container):
        super().__init__("spawn_counter", container)
        self._rect = Rect(20, 20, 200, 40)

    def update(self, dt: float) -> None:
        pass

    def render(self, renderer: UIRenderer) -> None:
        count = sum(1 for _ in self._entity_manager.get_all_entities())
        renderer.draw_rect(self._rect, Color(0, 0, 0, 200), 0)
        renderer.draw_text(
            f"Entities: {count}",
            Vector2(self._rect.x + 8, self._rect.y + 10),
            Color(255, 255, 255),
            16,
        )
```

```python
import pygame

app = create_sandbox_application()
app._tool_manager.register_tool(SpawnCounter(app._container), pygame.K_F10)
```

Registering a name that is already taken **replaces** the old tool (its
render-order slot and shortcut are dropped first). `ToolManager.unregister_tool(name)`
removes a tool and calls its `Tool.on_removed()` hook -- override that to
undo anything `__init__` acquired, such as an `EventDispatcher` subscription
(`EventMonitor` does). `SandboxApplication.shutdown()` clears every tool this
way before the engine tears down.

`Tool._entity_manager` resolves the active scene's `EntityManager` on every
access. **Before the first scene switch there is no world**, so it returns a
single throwaway empty manager -- fine to read, but a tool that *mutates* the
world in that window is writing into an orphan no scene will ever see. Return
`True` from `process_event` to stop an event reaching the game.


## The ImGui editor layer

A second dev surface, `pyguara.editor`: Dear ImGui panels drawn as a render
pass over the finished frame. It is **ModernGL-only** and **opt-in**.

```python
from pyguara.application.bootstrap import create_application
from pyguara.editor import attach_editor

app = create_application()
attach_editor(app.container)
app.run(MyScene("game", app._event_dispatcher))
```

`attach_editor` returns the `EditorLayer`, and registers it in the container
so game code can reach it. It returns `None` -- logging why -- when the
editor cannot run: ImGui is not installed, or the backend has no GL render
graph. It does not half-install.

!!! warning "Use `create_application()`, not `create_sandbox_application()`"

    The editor draws as a render-graph pass, and
    `SandboxApplication._render` does not execute graph passes -- it draws
    the scene and the `pyguara.tools` overlay straight to the window. So
    under the sandbox app `attach_editor()` succeeds, installs its pass,
    and the editor is then **never drawn**. (The same bypass means the
    sandbox skips every other pass too -- lighting, compositing,
    post-processing -- on the ModernGL backend; that divergence predates
    the editor.)

    Attach the editor to a plain `create_application()`, which renders
    through the graph. The `pyguara.tools` overlay is the dev surface for
    the sandbox app.

### Why ModernGL-only

The editor rasterises ImGui's draw data through the `moderngl.Context` the
`RenderGraph` owns. The Pygame backend has none: its `PygameRenderGraph` is a
stub whose `ctx` is `None`, and the window it opens is a software surface
(`pygame_window.py` actively strips `pygame.OPENGL` to keep it one). On that
backend `attach_editor` declines and the `pyguara.tools` overlay above stays
the dev surface.

### Why not `imgui_bundle.python_backends`

Those backends import `OpenGL.GL`. An undeclared PyOpenGL dependency is
exactly what made the *first* editor dead code, so the renderer here
(`pyguara.editor.renderer.ModernGLImGuiRenderer`) is written against
`moderngl` -- already a hard dependency of the engine -- and shares the
context the renderer is already using rather than standing up a second GL
stack. `pyguara.editor.availability.IMGUI_AVAILABLE` records whether ImGui
imported, and a test asserts it is `True`, so the editor cannot quietly
switch itself off again.

### Panels

| Panel | Shows |
| --- | --- |
| `HierarchyPanel` | The entity tree, over the ECS parent/child relation; click to select |
| `InspectorPanel` | The selected entity's components, with editable fields |

Both read `PanelContext`, which carries the active scene's `EntityManager`
(or `None` when no scene is active yet) and the shared `Selection`. The
inspector edits `bool`, `int`, `float`, `str`, `Vector2` and `Color` fields
and draws anything else read-only. A `frozen=True` component is drawn
read-only rather than assigned to, and every accepted edit ends with
`EntityManager.notify_component_changed()` so anything mirroring the
component -- physics bodies, render batches, the spatial index -- is told.

### Custom panels

```python
from pyguara.editor import EditorPanel, PanelContext


class EntityCount(EditorPanel):
    def __init__(self) -> None:
        super().__init__("Entity Count")

    def draw(self, context: PanelContext) -> None:
        from imgui_bundle import imgui

        imgui.begin(self.title)
        if context.entity_manager is None:
            imgui.text_disabled("No active scene.")
        else:
            total = sum(1 for _ in context.entity_manager.get_all_entities())
            imgui.text(f"Entities: {total}")
        imgui.end()
```

```python
layer = attach_editor(app.container, panels=[EntityCount()])
```

`draw()` runs between `new_frame()` and `render()`, and only while the panel
is visible. Pair every `begin()` with an `end()` unconditionally -- Dear
ImGui owes an `End` even for a collapsed window.

### Input

`EditorLayer.process_event()` takes the engine's own events -- the editor
never imports pygame -- and returns `True` when ImGui is using that kind of
input, so the caller can stop the event reaching the game. Scroll and typing
arrive as `MouseWheelEvent` and `TextInputEvent`, which the window backends
translate from SDL alongside the existing key and mouse events.
