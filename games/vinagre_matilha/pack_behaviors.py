"""Vinagre: Matilha - Pack AI Behaviors.

Behavior tree leaves and the tree factory for one dog. Every dog gets its
own `BehaviorTree` instance (built by `build_pack_tree()`) sharing one
`pyguara.ai.blackboard.Blackboard` -- ticking the *same* tree instance for
several entities would corrupt `SequenceNode`/`WaitNode` state, exactly the
trap `games/protocolo_bandeira/systems.py`'s `EnemyAISystem` avoids by
caching one tree per entity.
"""

from __future__ import annotations

from pyguara.ai.behavior_tree import (
    ActionNode,
    BehaviorTree,
    ConditionNode,
    NodeStatus,
    SelectorNode,
    SequenceNode,
)
from pyguara.ai.context import AIContext
from pyguara.ai.flocking_system import FlockingAgent
from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.kits.pack import (
    PackCommand,
    current_command,
    flanker_vector_for,
    request_reinforcements,
    threat_position,
)

# A dog with fewer than this many packmates within its own neighbor radius
# counts as "isolated" for CallReinforcements -- FlankerAssignmentSystem
# writes the live count onto the blackboard each tick (see systems.py).
_ISOLATION_THRESHOLD = 2
_REINFORCE_THREAT_DISTANCE = 250.0

NEIGHBOR_COUNT_KEY = "pack_neighbor_count"
"""Blackboard key: each flanker's live neighbour count, by dog id.

Written by `FlankerAssignmentSystem` every tick and read by
`CallReinforcements` below. Shared from here rather than spelled out at both
ends, the way the plate keys below already are -- the two copies of the
literal were free to drift apart."""

# Written each tick by FlankerAssignmentSystem when a stage has an unopened
# PressurePlate: the world position to press it, and which dog ids are this
# tick's designated plate-runners. Not part of `pyguara.kits.pack` -- the
# plate/log mechanic itself is demo-specific (games/vinagre_matilha/
# components.py), so its blackboard vocabulary lives here alongside it,
# the same way PressurePlate/LogGate aren't in the generic pack kit either.
PLATE_POSITION_KEY = "vinagre_plate_position"
PLATE_ASSIGNEES_KEY = "vinagre_plate_assignees"


def _agent(context: AIContext) -> FlockingAgent:
    return context.entity.get_component(FlockingAgent)


def _position(context: AIContext) -> Vector2:
    return context.entity.get_component(Transform).position


# ========== Conditions ==========


def is_pincer_command(context: AIContext) -> bool:
    """Whether the pack's current order is Pincer Attack."""
    return current_command(context.blackboard) is PackCommand.PINCER


def is_scatter_command(context: AIContext) -> bool:
    """Whether the pack's current order is Scatter."""
    return current_command(context.blackboard) is PackCommand.SCATTER


def is_distract_command(context: AIContext) -> bool:
    """Whether the pack's current order is Distract."""
    return current_command(context.blackboard) is PackCommand.DISTRACT


def is_flanking_target(context: AIContext) -> bool:
    """Whether this dog has an assigned flanking point to move toward."""
    return flanker_vector_for(context.blackboard, context.entity.id) is not None


def is_needed_at_plate(context: AIContext) -> bool:
    """Whether `FlankerAssignmentSystem` picked this dog to press the plate.

    Checked ahead of the player's Scatter/Pincer/Distract command: solving
    the plate puzzle is pack-autonomous (there's no fourth player command
    for it), and takes priority over combat maneuvering until the required
    count opens the gate -- after which `PressurePlateSystem` marks it
    `opened` and no dog is assigned here again.
    """
    assignees = context.blackboard.get(PLATE_ASSIGNEES_KEY, frozenset())
    return context.entity.id in assignees


# ========== Actions ==========


def check_and_call_reinforcements(context: AIContext) -> NodeStatus:
    """Flag the pack for reinforcement if this dog is isolated near the threat.

    Always returns FAILURE: this is a side-effect check meant to fall
    through to whatever movement branch follows it in the root selector,
    not a terminal behavior of its own.
    """
    threat = threat_position(context.blackboard)
    if threat is None:
        return NodeStatus.FAILURE

    neighbor_count = context.blackboard.get(NEIGHBOR_COUNT_KEY, {}).get(
        context.entity.id, 0
    )
    distance = (_position(context) - threat).length
    if neighbor_count < _ISOLATION_THRESHOLD and distance < _REINFORCE_THREAT_DISTANCE:
        request_reinforcements(context.blackboard)
    return NodeStatus.FAILURE


def go_to_plate(context: AIContext) -> NodeStatus:
    """Steer toward the pressure plate this dog was assigned to press."""
    target = context.blackboard.get(PLATE_POSITION_KEY)
    if target is None:
        return NodeStatus.FAILURE
    agent = _agent(context)
    agent.seek_target = target
    agent.seek_weight = 1.3
    return NodeStatus.SUCCESS


def circle_prey(context: AIContext) -> NodeStatus:
    """Steer toward this dog's assigned flanking point, at full seek weight."""
    target = flanker_vector_for(context.blackboard, context.entity.id)
    if target is None:
        return NodeStatus.FAILURE
    agent = _agent(context)
    agent.seek_target = target
    agent.seek_weight = 1.5
    return NodeStatus.SUCCESS


def scatter(context: AIContext) -> NodeStatus:
    """Steer away from the threat -- separation does the rest of the spreading."""
    threat = threat_position(context.blackboard)
    agent = _agent(context)
    if threat is None:
        agent.seek_weight = 0.0
        return NodeStatus.SUCCESS
    away = _position(context) - threat
    if away.length > 0.001:
        agent.seek_target = _position(context) + away.normalized() * 100.0
        agent.seek_weight = 1.0
    return NodeStatus.SUCCESS


def distract(context: AIContext) -> NodeStatus:
    """Steer straight at the threat -- bait it while flankers circle around."""
    threat = threat_position(context.blackboard)
    if threat is None:
        return NodeStatus.FAILURE
    agent = _agent(context)
    agent.seek_target = threat
    agent.seek_weight = 1.2
    return NodeStatus.SUCCESS


def roam(context: AIContext) -> NodeStatus:
    """Default movement: follow the shared flow field toward the threat."""
    flow_field: FlowFieldService | None = context.blackboard.get("pack_flow_field")
    cell_size: float = context.blackboard.get("pack_cell_size", 32.0)
    agent = _agent(context)
    if flow_field is None:
        agent.seek_weight = 0.0
        return NodeStatus.SUCCESS

    direction = flow_field.vector_at(_position(context), cell_size)
    if direction.length < 0.001:
        agent.seek_weight = 0.0
        return NodeStatus.SUCCESS
    agent.seek_target = _position(context) + direction * 100.0
    agent.seek_weight = 0.8
    return NodeStatus.SUCCESS


def build_pack_tree() -> BehaviorTree:
    """Build one dog's behavior tree.

    A fresh instance every call -- see the module docstring for why a tree
    can never be shared across dogs.
    """
    return BehaviorTree(
        root=SelectorNode(
            [
                SequenceNode(
                    [
                        ConditionNode(is_needed_at_plate, name="NeededAtPlate"),
                        ActionNode(go_to_plate, name="GoToPlate"),
                    ],
                    name="PlateSequence",
                ),
                ActionNode(check_and_call_reinforcements, name="CheckReinforcements"),
                SequenceNode(
                    [
                        ConditionNode(is_pincer_command, name="IsPincer"),
                        ConditionNode(is_flanking_target, name="IsFlankingTarget"),
                        ActionNode(circle_prey, name="CirclePrey"),
                    ],
                    name="PincerSequence",
                ),
                SequenceNode(
                    [
                        ConditionNode(is_scatter_command, name="IsScatter"),
                        ActionNode(scatter, name="Scatter"),
                    ],
                    name="ScatterSequence",
                ),
                SequenceNode(
                    [
                        ConditionNode(is_distract_command, name="IsDistract"),
                        ActionNode(distract, name="Distract"),
                    ],
                    name="DistractSequence",
                ),
                ActionNode(roam, name="Roam"),
            ],
            name="PackRoot",
        ),
        name="PackBehavior",
    )
