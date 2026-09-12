"""Shared-blackboard coordination vocabulary for a pack of AI agents.

Genre-specific to squad/pack-tactics games, not any one animal or demo:
role tagging, group commands, threat/retreat bookkeeping, and per-member
flanking-vector assignment, all read/write helpers over a shared
`pyguara.ai.blackboard.Blackboard`. `games/vinagre_matilha` is this kit's
first consumer.
"""

from pyguara.kits.pack.pack import (
    PackCommand,
    PackMember,
    PackRole,
    assign_flanker_vector,
    clear_reinforcements,
    current_command,
    flanker_vector_for,
    issue_command,
    reinforcements_requested,
    request_reinforcements,
    retreat_threshold,
    set_retreat_threshold,
    set_threat,
    threat_position,
)

__all__ = [
    "PackCommand",
    "PackMember",
    "PackRole",
    "assign_flanker_vector",
    "clear_reinforcements",
    "current_command",
    "flanker_vector_for",
    "issue_command",
    "reinforcements_requested",
    "request_reinforcements",
    "retreat_threshold",
    "set_retreat_threshold",
    "set_threat",
    "threat_position",
]
