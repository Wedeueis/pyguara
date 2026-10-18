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
| **Hierarchy** | The entity tree, with a filter and same-prefix grouping |
| **Inspector** | The selected entity's components, edited by reflection |
| **Play** | Pause, resume, single-step and slow the running game |
| **History** | Every edit, oldest first. Clicking a row rewinds to it |
| **Journal** | What was done and who asked, plus the approval queue |
| **Components** | Every registered component, its fields and its enum members |
| **Commands** | A person calling the operations an agent calls |

Panels open docked -- hierarchy left, inspector and components right,
viewport centre, play on top, history/journal/commands tabbed below.

### Finding an entity

An ECS scene has none of the pressure a Godot scene has to hang a level's
tiles off a parent, so a generated level arrives as hundreds of flat
siblings. The demo this was reported from put 252 rows in the Hierarchy
panel, 232 of them tiles.

Two answers, both from Godot's Scene dock:

- **A filter box.** Typing narrows the list to what is being worked on.
- **Grouping.** Runs of siblings sharing a name prefix -- everything up to
  the first numeric segment, so `tile_0_0` through `tile_19_11` are all
  `tile` -- fold into one row once there are four or more of them. 252
  rows become twelve.

The grouping is **display only**: no entity is named `tile`, nothing is
reparented, and the row says so on hover. A row that looked like a parent
and was not would be a worse lie than the long list it replaced.

Selecting an entity anywhere else -- clicking in the viewport, an agent's
operation -- scrolls the panel to it and opens the group holding it.

The panel reads and selects; it does not edit. Every change goes through
an operation, so it lands on one history and in one journal.

### The view is yours, and selection reaches what is behind

**Panning takes the camera.** Studio shows the game's own framebuffer, so
there is exactly one camera and panning has to move it -- and a game whose
follow system writes it every tick wins. Measured: a pan put the camera at
(-97, 178) and forty frames later the follow system had it at (204, 387),
so the click that followed landed on whatever had moved under the cursor.
That is what "the middle button broke selection" was.

So the viewport *takes* the view, as Godot's and Unity's editor views are
separate from the game's camera. The game keeps writing where it wants the
camera; those writes are recorded and not displayed. The toolbar says
which it is -- *Following the game*, or *Free view* with a **Follow game**
button that hands it back, resuming wherever the game had got to rather
than where the view was left.

**Clicking again reaches what is behind.** Picking returns everything
under the point, front-most first, and clicking the same spot walks back
through the stack -- the only way to select a background tile under a
platform, and how Godot's editor reaches a node behind another one.
Clicking somewhere else starts at the front again.

Physics still contributes candidates, because a collider is a deliberate
statement about an entity's extent where a sprite box is inferred from an
image. It no longer *decides*: `point_query` orders by how deeply the
point is enclosed, which has nothing to do with what is on top, and
clicking the player used to hand back the platform it was standing on.

**The HUD is not entities.** It is `UIManager` widgets with their own
tree, their own layers and their own hit testing, drawn over the frame; no
amount of entity picking reaches it. A click that lands on one now says
so, rather than silently clearing the selection, which is indistinguishable
from a click that missed. Editing the game's runtime UI is not something
Studio does.

## Edit, then play

The lifecycle every editor has, and the one Studio did not. **Studio
attaches in edit mode: the scene is loaded and nothing simulates.**

| | Edit | Play |
| --- | --- | --- |
| The game | stopped | running |
| Edits | everything | refused, naming Stop |
| The scene | is what you see | is a copy, restored on Stop |

Press **Play** and Studio copies the whole world and lets the game run.
Press **Stop** and that copy goes back, exactly as it was when Play was
pressed. Pause and Step are about watching a running game, not editing
one, and live inside Play.

Three engines, one agreement: Godot runs the game in its own process,
Unreal in its own world, Unity in the same world and discards the changes
on Stop. **The scene you edit and the game you run are not the same thing
at the same time.** Studio used to attach to a running game and edit it
live -- Unity's case without the discard -- and that is where every
confusing symptom came from: a gizmo drag overwritten by the controller on
the next tick, a pan reclaimed by the follow system, an edit outlived
before it could be seen.

Editing is **refused** while playing rather than discarded. Unity allows
it and throws it away, which everyone treats as a footgun; refusing costs
nothing and the message says to press Stop.

`WorldSnapshot` is what makes Stop mean something. It does **not** go
through `SceneSerializer`, which silently skips any component the registry
does not know -- which is every component a game defines unless it
registered them, and the stated reason there was no reset before. It
copies the live components instead, the way the command stack already
captures a subtree, so a component it has never heard of is copied exactly
as well as one it has. Measured on `guara_falcao`: 252 entities, 14 ms
each way, nothing lost.

Two details that are easy to get wrong and are tested:

- **Copied, not referenced.** Holding the live component means the game
  mutates the very object the snapshot is meant to restore, and Stop puts
  back exactly what play left behind.
- **Engine handles are cleared.** A copied `RigidBody._body_handle` points
  at a body the backend removed with the entity. Cleared, the physics
  system builds a fresh one, which is what it already does for an entity
  it has not seen.

`run_frames` is not Play. An agent stepping a stopped game frame by frame
is editing, not playing, and its edits are allowed throughout -- which is
the whole point of the edit/run/check loop.

### Why an edit may not show

Reported as "the controls over an entity's components do not seem to have
any effect". Driving the whole loop and measuring it separates three
things that look identical from the outside:

| What happened | How to tell |
| --- | --- |
| The edit was **refused** | A toast says so, naming the correction. Before, it was a log line nobody saw |
| The edit landed, and **the game overwrote it** | The Viewport says *Running* in amber. Whatever drives the entity -- a controller, a physics body, a follow system -- writes its transform again on the next tick. Pause and the edit stands |
| The edit landed, and **nothing draws from that component** | The world changed and the frame did not. A game that draws by hand from its own data renders the same picture whatever the component says |

The third is not a Studio bug and cannot be fixed from here: a component
is authored state, and only a game that renders from it will show a change
to it. Every demo in `games/` draws by hand, so editing a `Sprite`'s
colour changes the component and nothing else. Entities those demos *do*
draw from their `Transform` -- the player, the tiles -- move when moved.

`the_edit_lifecycle_works` in `tests/studio/_attach_scenarios.py` drives
the whole loop against a real demo with the game paused, and asserts the
frame actually changed. Paused, because a running game changes the frame
every tick and a pixel comparison would say nothing.

### Everything goes through an operation, including the Inspector

`attach_editor` installs an `InspectorPanel` with no attachment, and one
with no attachment writes straight onto the component -- right for a layer
with no session behind it. In Studio that was a second way to change the
world: a field typed into it reached no history, appeared in no journal,
and applied even in `plan` mode, which is supposed to change nothing.

So `attach_studio` installs an `InspectorPanel` that *has* the attachment,
and that one sends every accepted field through `set_field` -- the same
operation an agent calls. One seam, one history, one record, which is the
premise the whole design rests on, and it had a hole in it exactly where
most editing happens.

This was a `StudioInspectorPanel` subclass while the editor layer was a
separate package: a class whose entire body overrode one method across a
package boundary. The boundary is gone and so is the subclass. It is now
one class, and where an edit goes is a constructor argument -- which is
the honest shape, because a direct write is not a lesser version of the
operation path, it is what an editor with no history can do.

### The camera the gizmo trusts

`Scene.camera` is **the camera the scene renders with**, and everything
that turns a world position into a screen one from outside the frame reads
it: the Viewport panel, picking, and the transform gizmo.

A scene that overrides `render()` and draws with a camera of its own has
to assign it there. Nothing fails if it does not -- the frame looks right,
because the scene is using the camera it meant to. Only the editor is
wrong, and quietly: `guara_falcao` drew the gizmo hundreds of pixels from
the entity it belonged to, over the game's own pause button.
`tests/test_demo_bootstrap_conventions.py` now refuses a demo that builds
a camera and never assigns it.

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
