"""Shared-blackboard coordination vocabulary for a pack of AI agents.

Genre-specific to squad/pack-tactics games (a wolf pack, a Cannon Fodder
squad, a hive of minions taking one player's orders), not just a bush-dog
pack: nothing here names a dog. Built on `pyguara.ai.blackboard.Blackboard`,
which is already safe to share across every pack member's `AIComponent` --
only a `BehaviorTree` *instance* must stay per-entity (ticking one tree for
several entities corrupts its composite/decorator node state). This kit
supplies the read/write vocabulary a shared blackboard needs; the actual
behavior-tree leaves that call these functions are demo-owned, the same way
`games/protocolo_bandeira/ai_behaviors.py` owns its own leaf closures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import cast

from pyguara.ai.blackboard import Blackboard
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent

_KEY_COMMAND = "pack_command"
_KEY_THREAT_POSITION = "pack_threat_position"
_KEY_RETREAT_THRESHOLD = "pack_retreat_threshold"
_KEY_REINFORCEMENTS_REQUESTED = "pack_reinforcements_requested"
_KEY_FLANKER_VECTORS = "pack_flanker_vectors"


class PackRole(Enum):
    """A pack member's assigned role, for player control routing and visuals."""

    VANGUARD = auto()
    FLANKER = auto()


class PackCommand(Enum):
    """A group order issued to the pack, read by every member's behavior tree."""

    NONE = auto()
    SCATTER = auto()
    PINCER = auto()
    DISTRACT = auto()


@dataclass(slots=True)
class PackMember(StrictComponent):
    """Marks an entity as belonging to a pack, with its role and identity.

    Attributes:
        role: Whether this member is directly steered (`VANGUARD`) or
            coordinated via group commands (`FLANKER`).
        dog_id: Stable identifier used as this member's key in
            `assign_flanker_vector`/`flanker_vector_for`.
    """

    role: PackRole
    dog_id: str

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


def issue_command(blackboard: Blackboard, command: PackCommand) -> None:
    """Set the pack's current group order."""
    blackboard.set(_KEY_COMMAND, command)


def current_command(blackboard: Blackboard) -> PackCommand:
    """Return the pack's current group order, defaulting to `NONE`."""
    return cast(PackCommand, blackboard.get(_KEY_COMMAND, PackCommand.NONE))


def set_threat(blackboard: Blackboard, position: Vector2) -> None:
    """Record the current threat's (e.g. the jaguar's) world position."""
    blackboard.set(_KEY_THREAT_POSITION, position)


def threat_position(blackboard: Blackboard) -> Vector2 | None:
    """Return the last recorded threat position, or `None` if never set."""
    return cast("Vector2 | None", blackboard.get(_KEY_THREAT_POSITION))


def set_retreat_threshold(blackboard: Blackboard, value: float) -> None:
    """Set the health/exposure fraction at which pack members should retreat."""
    blackboard.set(_KEY_RETREAT_THRESHOLD, value)


def retreat_threshold(blackboard: Blackboard) -> float:
    """Return the retreat threshold, defaulting to 0.0 (never retreat)."""
    return cast(float, blackboard.get(_KEY_RETREAT_THRESHOLD, 0.0))


def request_reinforcements(blackboard: Blackboard) -> None:
    """Flag that the pack should call in reinforcements."""
    blackboard.set(_KEY_REINFORCEMENTS_REQUESTED, True)


def reinforcements_requested(blackboard: Blackboard) -> bool:
    """Whether reinforcements have been requested since the last clear."""
    return cast(bool, blackboard.get(_KEY_REINFORCEMENTS_REQUESTED, False))


def clear_reinforcements(blackboard: Blackboard) -> None:
    """Clear the reinforcements-requested flag."""
    blackboard.set(_KEY_REINFORCEMENTS_REQUESTED, False)


def assign_flanker_vector(blackboard: Blackboard, dog_id: str, vector: Vector2) -> None:
    """Assign `dog_id`'s current approach vector for flanking/encircling."""
    vectors: dict[str, Vector2] = blackboard.get(_KEY_FLANKER_VECTORS, {})
    vectors[dog_id] = vector
    blackboard.set(_KEY_FLANKER_VECTORS, vectors)


def flanker_vector_for(blackboard: Blackboard, dog_id: str) -> Vector2 | None:
    """Return `dog_id`'s assigned approach vector, or `None` if unassigned."""
    vectors: dict[str, Vector2] = blackboard.get(_KEY_FLANKER_VECTORS, {})
    return vectors.get(dog_id)
