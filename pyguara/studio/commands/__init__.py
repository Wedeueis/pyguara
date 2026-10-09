"""Reversible edits, and the stack that remembers them.

Every mutation Studio performs is an `EditCommand` on a `CommandStack` --
whether it came from a panel, the command palette, or an agent over MCP.
"""

from pyguara.studio.commands.base import (
    CompositeCommand,
    EditCommand,
    EditError,
)
from pyguara.studio.commands.entity import (
    AddComponent,
    CreateEntity,
    DestroyEntity,
    EntitySnapshot,
    RemoveComponent,
    SetEnabled,
    SetField,
    SetParent,
    SetTags,
    restore_subtree,
    snapshot_subtree,
)
from pyguara.studio.commands.stack import DEFAULT_LIMIT, CommandStack

__all__ = [
    "DEFAULT_LIMIT",
    "AddComponent",
    "CommandStack",
    "CompositeCommand",
    "CreateEntity",
    "DestroyEntity",
    "EditCommand",
    "EditError",
    "EntitySnapshot",
    "RemoveComponent",
    "SetEnabled",
    "SetField",
    "SetParent",
    "SetTags",
    "restore_subtree",
    "snapshot_subtree",
]
