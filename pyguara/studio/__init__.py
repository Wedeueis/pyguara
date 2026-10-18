"""PyGuara Studio: the companion authoring application.

A separate target from the game, and from the `pyguara/tools` debug
overlay. It runs the engine, opens a project, and lets a developer author
content visually while the code stays the source of truth -- everything
Studio writes is a file a human could have written by hand.

The architecture has one load-bearing idea: **a single mutation seam**.
Every change to authored state, whoever asked for it, becomes an
`EditCommand` on a `CommandStack`:

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

Routing all three through one seam is what makes undo/redo, a reviewable
audit journal, diffable agent edits and a deterministic edit-run-check
loop the same mechanism rather than four parallel ones.

**The Dear ImGui editor layer lives here too**, as `attach_editor` and
the modules under it -- the context, the input routing, the render pass,
the panel contract and the panels. It used to be `pyguara/editor`, a
separate package that Studio imported from across ten call sites and
subclassed a panel of; the split described no boundary anyone defended,
and the one thing it reliably produced was two of everything the two
halves shared. What *is* a boundary is `pyguara/tools`, the runtime debug
overlay drawn through `UIRenderer`: it needs no ImGui and works on the
Pygame backend, which has no GL context for this layer to draw into.

`attach_editor` on its own is still a supported way to attach: the layer
with no session behind it, which is what a game wanting a hierarchy and
an inspector and nothing else should ask for.

**Importing this package does not import Dear ImGui.** The JSON-lines
agent transport (`pyguara studio ops`) reaches the operation registry
through this `__init__`, and it is meant to run on an install with no
ImGui at all -- so what is re-exported here is confined to what loads
without it. The panels and the layer are imported from their own modules,
and `pyguara.studio.availability` says whether that will work.
"""

from pyguara.studio.attach import StudioAttachment, attach_editor, attach_studio
from pyguara.studio.commands import CommandStack, EditCommand, EditError
from pyguara.studio.selection import Selection
from pyguara.studio.session import ApprovalMode, EditOutcome, StudioSession

__all__ = [
    "ApprovalMode",
    "CommandStack",
    "EditCommand",
    "EditError",
    "EditOutcome",
    "Selection",
    "StudioAttachment",
    "StudioSession",
    "attach_editor",
    "attach_studio",
]
