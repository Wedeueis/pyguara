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
"""

from pyguara.studio.attach import StudioAttachment, attach_studio
from pyguara.studio.commands import CommandStack, EditCommand, EditError
from pyguara.studio.session import ApprovalMode, EditOutcome, StudioSession

__all__ = [
    "ApprovalMode",
    "CommandStack",
    "EditCommand",
    "EditError",
    "EditOutcome",
    "StudioAttachment",
    "StudioSession",
    "attach_studio",
]
