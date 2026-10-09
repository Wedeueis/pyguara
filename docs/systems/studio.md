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

Panels open docked — hierarchy left, inspector and components right,
viewport centre, play on top, history/journal/commands tabbed below — and
the arrangement is applied once, so dragging a panel elsewhere keeps it
there.

### Viewport

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
| Editing | `create_entity`, `destroy_entity`, `add_component`, `remove_component`, `set_field`, `set_parent`, `set_enabled`, `set_tags` |
| Running | `run_frames`, `capture_frame` |
| Session | `history`, `journal`, `approvals` |

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
