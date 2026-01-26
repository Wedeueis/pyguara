"""Protocolo Bandeira - AI Behaviors.

Behavior tree implementations for enemy AI.
"""

import math
import random

from pyguara.ai.behavior_tree import (
    BehaviorTree,
    NodeStatus,
    ActionNode,
    ConditionNode,
    SequenceNode,
    SelectorNode,
)
from pyguara.common.types import Vector2

from games.protocolo_bandeira.components import AIContext, EnemyType


# ============ Condition Functions ============


def is_player_detected(context: AIContext) -> bool:
    """Check if player is within detection range."""
    return context.player_position is not None and context.distance_to_player < 300


def is_in_attack_range(context: AIContext) -> bool:
    """Check if player is within attack range."""
    return context.player_position is not None and context.distance_to_player < 150


def is_alerted(context: AIContext) -> bool:
    """Check if enemy is alerted to player."""
    return context.is_alerted


# ============ Action Functions ============


def chase_player(context: AIContext) -> NodeStatus:
    """Move towards the player."""
    if context.player_position is None:
        return NodeStatus.FAILURE

    # Calculate direction to player
    direction = context.player_position - context.position
    if direction.magnitude > 0:
        direction = direction.normalize()

    # Store movement intent in context
    context.move_direction = direction
    return NodeStatus.SUCCESS


def attack_player(context: AIContext) -> NodeStatus:
    """Perform attack action."""
    if context.player_position is None:
        return NodeStatus.FAILURE

    # Mark attack intent
    context.should_attack = True
    return NodeStatus.SUCCESS


def patrol_wander(context: AIContext) -> NodeStatus:
    """Wander randomly."""
    # Random direction change occasionally
    if random.random() < 0.02:  # 2% chance per frame
        angle = random.uniform(0, math.pi * 2)
        context.move_direction = Vector2(math.cos(angle), math.sin(angle))
    elif not hasattr(context, "move_direction") or context.move_direction is None:
        angle = random.uniform(0, math.pi * 2)
        context.move_direction = Vector2(math.cos(angle), math.sin(angle))

    return NodeStatus.SUCCESS


def face_player(context: AIContext) -> NodeStatus:
    """Turn to face the player."""
    if context.player_position is None:
        return NodeStatus.FAILURE

    direction = context.player_position - context.position
    context.facing_angle = math.atan2(direction.y, direction.x)
    return NodeStatus.SUCCESS


def maintain_distance(context: AIContext) -> NodeStatus:
    """Keep distance from player (for shooters)."""
    if context.player_position is None:
        return NodeStatus.FAILURE

    ideal_distance = 200.0
    direction = context.position - context.player_position

    if context.distance_to_player < ideal_distance - 30:
        # Too close, back away
        if direction.magnitude > 0:
            context.move_direction = direction.normalize()
    elif context.distance_to_player > ideal_distance + 30:
        # Too far, get closer
        if direction.magnitude > 0:
            context.move_direction = -direction.normalize()
    else:
        # Good distance, strafe
        if direction.magnitude > 0:
            perpendicular = Vector2(-direction.y, direction.x).normalize()
            context.move_direction = perpendicular * (
                1 if random.random() > 0.5 else -1
            )

    return NodeStatus.SUCCESS


# ============ Behavior Tree Builders ============


def create_chaser_behavior() -> BehaviorTree:
    """Create behavior tree for chaser enemies.

    Behavior:
        1. If player detected: chase and attack when close
        2. Otherwise: wander randomly
    """
    tree = BehaviorTree(
        root=SelectorNode(
            [
                # Attack sequence: detect -> chase -> attack
                SequenceNode(
                    [
                        ConditionNode(is_player_detected, name="PlayerDetected"),
                        ActionNode(chase_player, name="Chase"),
                        ConditionNode(is_in_attack_range, name="InRange"),
                        ActionNode(attack_player, name="Attack"),
                    ],
                    name="AttackSequence",
                ),
                # Chase sequence (no attack)
                SequenceNode(
                    [
                        ConditionNode(is_player_detected, name="PlayerDetected"),
                        ActionNode(chase_player, name="Chase"),
                    ],
                    name="ChaseSequence",
                ),
                # Patrol
                ActionNode(patrol_wander, name="Patrol"),
            ],
            name="ChaserRoot",
        ),
        name="ChaserBehavior",
    )
    return tree


def create_shooter_behavior() -> BehaviorTree:
    """Create behavior tree for shooter enemies.

    Behavior:
        1. If player detected and in attack range: face player, maintain distance, attack
        2. If player detected: chase to get in range
        3. Otherwise: patrol
    """
    tree = BehaviorTree(
        root=SelectorNode(
            [
                # Attack sequence: maintain distance and shoot
                SequenceNode(
                    [
                        ConditionNode(is_player_detected, name="PlayerDetected"),
                        ConditionNode(is_in_attack_range, name="InRange"),
                        ActionNode(face_player, name="FacePlayer"),
                        ActionNode(maintain_distance, name="MaintainDist"),
                        ActionNode(attack_player, name="Attack"),
                    ],
                    name="AttackSequence",
                ),
                # Chase to get in range
                SequenceNode(
                    [
                        ConditionNode(is_player_detected, name="PlayerDetected"),
                        ActionNode(chase_player, name="Chase"),
                    ],
                    name="ChaseSequence",
                ),
                # Patrol
                ActionNode(patrol_wander, name="Patrol"),
            ],
            name="ShooterRoot",
        ),
        name="ShooterBehavior",
    )
    return tree


def create_bomber_behavior() -> BehaviorTree:
    """Create behavior tree for bomber enemies.

    Behavior:
        1. If player detected: rush towards player
        2. If in attack range: explode (attack)
        3. Otherwise: wander
    """
    tree = BehaviorTree(
        root=SelectorNode(
            [
                # Rush and explode
                SequenceNode(
                    [
                        ConditionNode(is_player_detected, name="PlayerDetected"),
                        ActionNode(chase_player, name="Rush"),
                        ConditionNode(is_in_attack_range, name="InRange"),
                        ActionNode(attack_player, name="Explode"),
                    ],
                    name="ExplodeSequence",
                ),
                # Chase
                SequenceNode(
                    [
                        ConditionNode(is_player_detected, name="PlayerDetected"),
                        ActionNode(chase_player, name="Rush"),
                    ],
                    name="RushSequence",
                ),
                # Patrol
                ActionNode(patrol_wander, name="Patrol"),
            ],
            name="BomberRoot",
        ),
        name="BomberBehavior",
    )
    return tree


def get_behavior_for_type(enemy_type: EnemyType) -> BehaviorTree:
    """Get the appropriate behavior tree for an enemy type."""
    if enemy_type == EnemyType.SHOOTER:
        return create_shooter_behavior()
    elif enemy_type == EnemyType.BOMBER:
        return create_bomber_behavior()
    else:  # CHASER
        return create_chaser_behavior()
