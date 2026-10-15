# PyGuara Studio

The companion authoring surface: a dockable editor over a running game,
and the same operations exposed to a coding agent.

Studio is **opt-in**. A shipped game never attaches it and pays nothing
for it.

```python
from pyguara.application.bootstrap import create_application
from pyguara.studio import attach_studio

app = create_application()
attach_studio(app.container)
app.run(MyScene("game", dispatcher))
```

## Trying it

Six demos already use the ModernGL backend, and `tools/studio_demo.py`
opens any of them with Studio attached:

```bash
uv run python tools/studio_demo.py                       # guara_falcao
uv run python tools/studio_demo.py tamandua_murundus
uv run python tools/studio_demo.py guara_falcao --mode ask
uv run python tools/studio_demo.py guara_falcao --borderless
```

`main.py` and the remaining demos run on the Pygame backend, where Studio
declines rather than half-installing.

`attach_studio` builds on `attach_editor`, so it is ModernGL-only for the
same reason: it draws through the GL context the render graph owns, and
the Pygame backend's window is a software surface with none. On that
backend it declines and logs why, and `pyguara/tools` remains the dev
surface there. See [Editor Tools](editor.md).

## The one idea

Every change to authored state becomes an `EditCommand` on a
`CommandStack`, whoever asked for it — a panel, the command palette, or an
agent.

```
  human UI      command palette      agent (MCP / JSON-lines)
      |                |                        |
      +----------------+------------------------+
                       |
                  ops registry
                       |
               EditCommand objects
                       |
               CommandStack --> Journal
                       |
                 EntityManager
```

That single seam is why undo/redo, a reviewable audit journal, diffable
agent edits and a deterministic edit-run-check loop are one mechanism
rather than four. See [ADR 0001](../adr/0001-one-mutation-seam-for-studio.md).

## Panels

| Panel | What it is for |
| --- | --- |
| **Viewport** | The rendered frame, with pan, zoom, a grid, selection, marquee and the transform gizmo over it |
| **Hierarchy** | The entity tree, from the ECS parent/child relation |
| **Inspector** | The selected entity's components, edited by reflection |
| **Play** | Pause, resume, single-step and slow the running game |
| **History** | Every edit, oldest first. Clicking a row rewinds to it |
| **Journal** | What was done and who asked, plus the approval queue |
| **Components** | Every registered component, its fields and its enum members |
| **Commands** | A person calling the operations an agent calls |

Panels open docked -- hierarchy left, inspector and components right,
viewport centre, play on top, history/journal/commands tabbed below.

### The arrangement

Applied **once**, not on every resize, and then left to ImGui. Three
consequences, all of them what a docking editor is expected to do:

- A splitter you drag stays dragged.
- Widening the window widens the **viewport**, not the side docks. They
  keep the width they were given. Rebuilding the tree on each resize --
  which is what this used to do -- forced them back to a percentage
  instead, so on a 21:9 display the hierarchy took a third of the screen
  and clipped its text anyway.
- The arrangement survives a restart. ImGui's own settings file carries
  it, in `<project>/.pyguara/studio-layout.ini` -- a tool's state rather
  than the project's, out of the way and easy to delete. `.gitignore`
  carries it. The bare editor and every test write nothing: persistence is
  opt-in through `EditorLayer.set_settings_file`, and Studio is what opts
  in.

*View > Reset Layout* is the one action that discards both a saved
arrangement and whatever has been dragged since.

## The menus

Studio's menu bar is built over the **operation registry**, not over the
editor's internals. An entry that changes the scene calls the same
operation an agent calls over MCP or JSON lines, so a person choosing
*Entity > Create Empty* and an agent calling `create_entity` take one
path, land in one history, and read the same way in the journal.

| Menu | What is in it |
| --- | --- |
| **Scene** | Save, Open, New, and Quit |
| **Edit** | Undo, Redo, Duplicate, Delete Entity, Deselect |
| **Entity** | Create Empty, Add Component, Enable/Disable |
| **View** | The panels, and Reset Layout |
| **Run** | Pause/Resume, Step, the time-scale presets |
| **Agent** | The approval mode, Approvals, Journal, and the commands that let an agent in |
| **Help** | The documentation link, and About |

The names follow Godot and Unity where they agree -- Scene is Godot's
File, Entity is this engine's word for Godot's Node and Unity's
GameObject -- because a menu bar is not the place to be original. **Agent**
has no equivalent in either, and is the point of Studio.

The same menus are drawn into the editor's own title bar when the window
is borderless, and into ImGui's main menu bar when it is not. One list,
two places, so the two can never disagree about what the editor offers.

**What is greyed out is greyed out for a reason.** *Save* and *Open* need
a session that can reach the serializer, which one built by hand has no
container for; the menu disables them rather than offering an action that
fails. Nothing in the bar reaches around an operation to do its work, so
there is no state a person can reach that an agent cannot.

## The window

Two display flags decide what the operating system gives the editor, and
both default off so a shipped game is unaffected:

| `display.` | What it does |
| --- | --- |
| `resizable` | SDL reports resizes at all. Without it the window manager may still let the frame be maximised -- WSLg does -- while nothing in the engine is told, and the editor carries on drawing at the starting resolution into a corner of a much larger window |
| `borderless` | Removes the OS title bar, so the editor draws its own |

`borderless` is what the grey Windows-classic frame around the editor was.
With it set, `attach_editor` installs a `TitleBar`: the panel menu at the
left, the window title centred, and minimise/maximise/close at the right,
in the editor's own palette -- the arrangement Godot and VS Code use, and
for the same reason. The icons are stroked onto the draw list rather than
written as text, because ImGui's built-in font carries Basic Latin and
nothing else.

Set only where the backend offers window controls. `Window.chrome`
answers that: it hands back the backend when it satisfies `IWindowChrome`
and `None` otherwise, and the editor leaves the OS bar alone in the second
case. A borderless window whose buttons do nothing is worse than the frame
it replaced.

Close goes through the window's event queue rather than destroying the
window: the button is pressed from inside a frame that is still being
drawn, and the application runs the same shutdown it runs for the OS's own
button.

Keep `resizable` on wherever `borderless` is: removing the frame removes
the OS's resize edges with it.

### Who the window belongs to

`ctx.screen.viewport` means **where the game's frame goes**. With
`keep_aspect` the render graph narrows it to the letterbox, so the game
and its HUD land inside their own frame however the window is dragged.

The editor is not the game: it owns the whole window, and its pass sets
the window viewport for its own draw and puts the letterbox back
afterwards -- back, because the game's UI composites after the graph runs
and belongs inside the frame rather than on the bars.

Getting that wrong is not subtle. Inheriting the letterbox squeezed every
panel by the ratio between the two: on a 2000x876 window that is a
horizontal scale of 0.73, which reads as compressed text and a round sun
in the Viewport panel drawn as an ellipse taller than wide. An ultrawide
display makes it worse -- at 21:9 more than a quarter of the window is
bars.

### Viewport

**Studio owns the screen.** On attach it disables the final blit, so the
game is not also drawn full-screen behind the panels, and redirects the
game's UI compositing into the buffer the viewport shows -- so the HUD
appears over the game, inside the viewport, instead of over the editor's
panels. `release_screen()` puts all of it back.

The frame is **letterboxed**, not stretched: a docked panel is almost
never the render target's shape, and a stretched view means a sprite
lined up in the editor is wrong everywhere else. Every coordinate mapping
uses the drawn image's rectangle rather than the panel's, or a click
would be offset by the width of the bars.

Pan with the middle button or space-drag; zoom with the wheel, anchored on
the cursor. Click to select, ctrl-click to add, drag to marquee. `Enclose`
switches the marquee between selecting what it touches and only what it
fully contains.

Picking consults the physics engine first where there is one —
`point_query` is written for exactly this and orders results
most-deeply-enclosing first — and otherwise measures each sprite's real
bounds from its texture, transform scale and offset. An entity with no
sprite and no collider still gets a fixed box, so a spawn point or an
empty used as a parent remains clickable.

### Gizmo

`Q` translate, `W` rotate, `E` scale. Drag an arrow to constrain to an
axis, the centre handle to move freely. `Snap` rounds to the grid step in
absolute world space — snapping the delta would leave an entity that began
off-grid off it forever. Rotation snaps in degrees, since a grid is a
distance and means nothing to an angle. Escape cancels a drag, leaving
neither a change nor a history entry.

**One drag is one undo entry, spanning the whole drag.** Components are
written directly while dragging, for live feedback with no history churn;
on release the starting values are restored and a single command is
applied. The restore is not redundant: a command captures its inverse when
applied, so one applied against a world already holding the final values
would record "from final to final" and undo nothing.

## The operation surface

Around twenty operations, reachable three ways. The registry is shared, so
an operation cannot be available to one caller and missing from another.

```bash
# JSON lines on stdio -- no extra dependency.
pyguara studio ops

# Model Context Protocol -- needs the `studio` extra.
pyguara studio mcp
```

| Group | Operations |
| --- | --- |
| Discovery | `list_operations`, `project_overview`, `list_components`, `component_schema` |
| Reading | `scene_summary`, `scene_tree`, `get_entity`, `find_entities` |
| Editing | `create_entity`, `destroy_entity`, `duplicate_entity`, `add_component`, `remove_component`, `set_field`, `set_parent`, `set_enabled`, `set_tags` |
| Running | `run_frames`, `capture_frame` |
| Session | `history`, `journal`, `approvals`, `scene` |

`scene` carries four verbs behind an "operation" argument -- save, open,
new and list -- as `history` does. The flat surface is budgeted, because
a client's tool limit is spent on the verbs used every minute, and saving
is not one of them.

Two of those four clear the undo history, and say so: opening, because
every command on the stack describes a world that no longer exists, and
saving, because undoing past a save leaves the file and the world
disagreeing with nothing on screen to show it. Emptying the scene does
not -- it is a destroy of every root inside one transaction, so it stays
a single undoable entry.

Each declares a **risk class** — `read`, `edit`, `run` or `write_disk` —
so a caller can express "read anything, ask before writing" without
enumerating operations.

Rarer work sits behind `history` and `approvals`, which take an
`operation` argument, rather than becoming another dozen entries. A client
has a limit on how many tools it will present, and an agent's accuracy
falls as the list grows.

### Approval modes

| Mode | Behaviour |
| --- | --- |
| `auto` | Apply the edit. The default for a person at the keyboard |
| `ask` | Queue it with the diff it *would* make, for someone to approve |
| `plan` | Describe it and change nothing |

`plan` is not a prediction: the edit is applied, the diff captured, and
the edit reverted, so the reported consequence is the real one. Destroying
an entity names every id the ownership cascade would take with it.

```bash
pyguara studio ops --mode ask --journal .studio/journal.jsonl
```

## The harness

A closed loop for an agent with no window: open a scene, edit it, run it,
look at the frames, check what moved.

```python
from pyguara.studio.agent.harness import open_headless
from games.guara_falcao.bootstrap import configure_game_container
from games.guara_falcao.scenes import GameScene

harness = open_headless(
    GameScene,
    container_factory=configure_game_container,
    gl=True,
)
harness.step(30)
capture = harness.capture("frame")
print(capture.blank, capture.world_flat)
```

**"Headless" means no window, not the headless backend.**
`create_headless_application()` registers no texture loader, so any scene
that loads an image dies before it finishes entering — and a real demo is
almost entirely images. The harness boots the normal bootstrap under an
SDL driver that needs no display. `gl=True` selects `offscreen`, which
provides a real GL context; `dummy` has no OpenGL at all.

Runs are deterministic: the harness installs `FixedClock` and seeds
`RandomService` itself, so the same script twice produces the same frames.
That is what makes "run it again and diff" an answer.

A capture reports whether the composed frame **and the world buffer behind
it** are a single flat colour. They are separate because a composed frame
carries the UI, so a dead world render path still leaves a HUD on screen
and the frame is never flat.

!!! warning "What a capture proves"
    It reads the buffer the renderer drew into, which proves the render
    *path* works. It does **not** prove a window appears on screen. Those
    have already diverged in this engine, when vsync silently promoted the
    display to an OpenGL surface that never presented software blits — the
    captures looked perfect and the real window was blank. See
    [Visual Inspection](../guides/agent-visual-inspection.md).

## Instruction files

Studio generates the files coding agents read, from the project itself.

```bash
pyguara studio instructions          # write them
pyguara studio instructions --check  # fail if stale, for CI
```

It writes a canonical `AGENTS.md` and thin shims that import it:
`CLAUDE.md`, `GEMINI.md` and `.cursor/rules/pyguara.mdc`. **Generated
regions are fenced, and nothing outside them is touched** — an instruction
file is mostly hand-written knowledge, and a generator that overwrites it
is one nobody runs twice.

See the [agent integration guide](../guides/agent-integration.md).

## What is deliberately absent

- **Reset-to-where-play-began.** It would mean restoring the whole world,
  and `SceneSerializer` skips any component the registry does not know —
  which is every component a game defines unless it registered them. A
  reset that quietly dropped the player's controller is worse than none.
  Save before playing and load afterwards instead.
- **Generated argument forms in the palette.** A form would be nicer for
  scalars and hopeless for a nested dataclass. Arguments are JSON, which
  is the shape the schema browser shows and the scene files use.
- **Prefab override editing and the animation timeline.** Issues #51 and
  #37 respectively; Studio consumes their data models rather than
  defining them.
