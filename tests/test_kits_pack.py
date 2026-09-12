"""Tests for `pyguara/kits/pack/` (blackboard coordination vocabulary)."""

from __future__ import annotations

from pyguara.ai.blackboard import Blackboard
from pyguara.common.types import Vector2
from pyguara.kits.pack import (
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

# ========== PackMember ==========


def test_pack_member_carries_role_and_id() -> None:
    member = PackMember(role=PackRole.FLANKER, dog_id="dog-3")
    assert member.role is PackRole.FLANKER
    assert member.dog_id == "dog-3"


# ========== command ==========


def test_current_command_defaults_to_none() -> None:
    blackboard = Blackboard()
    assert current_command(blackboard) is PackCommand.NONE


def test_issue_command_is_read_back() -> None:
    blackboard = Blackboard()
    issue_command(blackboard, PackCommand.PINCER)
    assert current_command(blackboard) is PackCommand.PINCER


def test_issuing_a_new_command_replaces_the_old_one() -> None:
    blackboard = Blackboard()
    issue_command(blackboard, PackCommand.SCATTER)
    issue_command(blackboard, PackCommand.DISTRACT)
    assert current_command(blackboard) is PackCommand.DISTRACT


# ========== threat ==========


def test_threat_position_defaults_to_none() -> None:
    blackboard = Blackboard()
    assert threat_position(blackboard) is None


def test_set_threat_is_read_back() -> None:
    blackboard = Blackboard()
    set_threat(blackboard, Vector2(100, 50))
    assert threat_position(blackboard) == Vector2(100, 50)


# ========== retreat threshold ==========


def test_retreat_threshold_defaults_to_zero() -> None:
    blackboard = Blackboard()
    assert retreat_threshold(blackboard) == 0.0


def test_set_retreat_threshold_is_read_back() -> None:
    blackboard = Blackboard()
    set_retreat_threshold(blackboard, 0.25)
    assert retreat_threshold(blackboard) == 0.25


# ========== reinforcements ==========


def test_reinforcements_not_requested_by_default() -> None:
    blackboard = Blackboard()
    assert reinforcements_requested(blackboard) is False


def test_request_reinforcements_sets_the_flag() -> None:
    blackboard = Blackboard()
    request_reinforcements(blackboard)
    assert reinforcements_requested(blackboard) is True


def test_clear_reinforcements_resets_the_flag() -> None:
    blackboard = Blackboard()
    request_reinforcements(blackboard)
    clear_reinforcements(blackboard)
    assert reinforcements_requested(blackboard) is False


# ========== flanker vectors ==========


def test_flanker_vector_defaults_to_none() -> None:
    blackboard = Blackboard()
    assert flanker_vector_for(blackboard, "dog-1") is None


def test_assign_flanker_vector_is_read_back_by_id() -> None:
    blackboard = Blackboard()
    assign_flanker_vector(blackboard, "dog-1", Vector2(1, 0))
    assign_flanker_vector(blackboard, "dog-2", Vector2(0, 1))

    assert flanker_vector_for(blackboard, "dog-1") == Vector2(1, 0)
    assert flanker_vector_for(blackboard, "dog-2") == Vector2(0, 1)


def test_reassigning_a_dogs_vector_overwrites_the_old_one() -> None:
    blackboard = Blackboard()
    assign_flanker_vector(blackboard, "dog-1", Vector2(1, 0))
    assign_flanker_vector(blackboard, "dog-1", Vector2(-1, 0))

    assert flanker_vector_for(blackboard, "dog-1") == Vector2(-1, 0)


# ========== shared-blackboard scenario ==========


def test_one_blackboard_coordinates_multiple_pack_members() -> None:
    """The exact pattern the demo relies on: one Blackboard, many dogs."""
    shared = Blackboard()
    issue_command(shared, PackCommand.PINCER)
    set_threat(shared, Vector2(200, 200))
    assign_flanker_vector(shared, "dog-a", Vector2(1, 0))
    assign_flanker_vector(shared, "dog-b", Vector2(-1, 0))

    # Every "member" reads the same shared state.
    assert current_command(shared) is PackCommand.PINCER
    assert threat_position(shared) == Vector2(200, 200)
    assert flanker_vector_for(shared, "dog-a") == Vector2(1, 0)
    assert flanker_vector_for(shared, "dog-b") == Vector2(-1, 0)
