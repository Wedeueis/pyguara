"""PyGuara Studio: the companion authoring application.

Studio runs the engine, opens a project, and lets a developer author
content visually. Everything it writes is a file a person could have
written by hand. Every change to authored state becomes an
`EditCommand` on a `CommandStack`, whoever asked for it; see ADR 0001.

Importing this package does not import Dear ImGui, so the JSON-lines
transport (`pyguara studio ops`) runs without it. The panels and the
editor layer are imported from their own modules.
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
