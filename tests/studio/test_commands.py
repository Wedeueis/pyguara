"""The concrete edit commands, and what each one restores.

The property every test here is really checking: apply then revert leaves
the world indistinguishable from before. That is the whole contract the
rest of Studio -- undo, the journal, an agent's "try it and back it out"
loop -- is built on.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.sprite import Sprite
from pyguara.studio.commands.base import (
    CompositeCommand,
    EditCommand,
    EditError,
)
from pyguara.studio.commands.entity import (
    AddComponent,
    CreateEntity,
    DestroyEntity,
    RemoveComponent,
    SetEnabled,
    SetField,
    SetParent,
    SetTags,
    snapshot_subtree,
)


def world_digest(world: EntityManager) -> dict[str, object]:
    """Summarise a world, for before/after comparison.

    Everything an edit could change and an undo must put back: ids,
    component types *and their field values*, tags, enabled state and the
    parent links.

    Field values via `repr`, because the component types here are a mix of
    dataclasses and `StrictComponent`s built from properties -- `Transform`
    is not a dataclass, so `dataclasses.fields` would skip it entirely and
    a field write on it would be invisible to this digest. Both kinds have
    a field-sensitive `repr`.

    Args:
        world: The world to summarise.

    Returns:
        A comparable, order-independent digest.
    """
    return {
        entity.id: (
            sorted(repr(component) for component in entity.get_all_components()),
            sorted(entity.tags),
            world.is_entity_enabled(entity.id),
            world.parent_of(entity.id),
        )
        for entity in world.get_all_entities()
    }


class TestApplyRevertIsIdentity:
    """Every command, round-tripped against the same world."""

    @pytest.fixture
    def commands(self, populated: EntityManager) -> list[EditCommand]:
        """One of each command, all valid against the populated world."""
        return [
            CreateEntity("fresh", components=[Transform()], tags={"new"}),
            CreateEntity("fresh_child", parent_id="root"),
            DestroyEntity("child_a"),
            DestroyEntity("child_b"),
            AddComponent("child_a", Tag("Named")),
            RemoveComponent("root", Tag),
            SetField("root", Transform, "rotation", 1.5),
            SetParent("child_a", "child_b"),
            SetParent("child_a", None),
            SetEnabled("root", False),
            SetTags("root", {"replaced"}),
        ]

    def test_each_command_restores_the_world(
        self, populated: EntityManager, commands: list[EditCommand]
    ) -> None:
        """Apply, revert, and the digest must match exactly."""
        for command in commands:
            before = world_digest(populated)
            command.apply(populated)
            command.revert(populated)
            assert world_digest(populated) == before, command.label

    def test_each_command_actually_changes_something(
        self, populated: EntityManager, commands: list[EditCommand]
    ) -> None:
        """Guards the test above from passing on a no-op command.

        An `apply()` that did nothing would round-trip perfectly.
        """
        for command in commands:
            before = world_digest(populated)
            command.apply(populated)
            assert world_digest(populated) != before, command.label
            command.revert(populated)


class TestCreateEntity:
    """Adding entities."""

    def test_creates_with_components_and_tags(self, world: EntityManager) -> None:
        CreateEntity(
            "hero", components=[Transform(), Tag("Hero")], tags={"player"}
        ).apply(world)

        entity = world.get_entity("hero")
        assert entity is not None
        assert entity.has_component(Transform)
        assert entity.tags == {"player"}

    def test_creates_parented(self, populated: EntityManager) -> None:
        CreateEntity("hat", parent_id="root").apply(populated)
        assert populated.parent_of("hat") == "root"
        assert "hat" in populated.children_of("root")

    def test_rejects_a_taken_id(self, populated: EntityManager) -> None:
        """`add_entity` overwrites silently, so this must be caught first.

        Creating onto an existing id would replace an entity the undo
        could not bring back -- the command never captured it.
        """
        with pytest.raises(EditError, match="already exists"):
            CreateEntity("root").apply(populated)

    def test_a_rejected_create_changes_nothing(self, populated: EntityManager) -> None:
        before = world_digest(populated)
        with pytest.raises(EditError):
            CreateEntity("root").apply(populated)
        assert world_digest(populated) == before

    def test_rejects_a_missing_parent(self, world: EntityManager) -> None:
        with pytest.raises(EditError, match="No parent entity"):
            CreateEntity("hat", parent_id="nobody").apply(world)

    def test_the_id_is_stable_across_undo_and_redo(self, world: EntityManager) -> None:
        """So a selection or a parent link still resolves afterwards."""
        command = CreateEntity("hero")
        command.apply(world)
        command.revert(world)
        command.apply(world)
        assert world.get_entity("hero") is not None


class TestDestroyEntity:
    """Removing entities, and the cascade."""

    def test_removes_the_entity(self, populated: EntityManager) -> None:
        DestroyEntity("loose").apply(populated)
        assert populated.get_entity("loose") is None

    def test_cascades_through_childof(self, populated: EntityManager) -> None:
        """`remove_entity` deletes the subtree; the command must know."""
        DestroyEntity("child_b").apply(populated)
        assert populated.get_entity("child_b") is None
        assert populated.get_entity("grandchild") is None

    def test_undo_rebuilds_the_whole_subtree(self, populated: EntityManager) -> None:
        command = DestroyEntity("child_b")
        command.apply(populated)
        command.revert(populated)

        assert populated.get_entity("child_b") is not None
        assert populated.get_entity("grandchild") is not None
        assert populated.parent_of("grandchild") == "child_b"
        assert populated.parent_of("child_b") == "root"

    def test_undo_restores_components_tags_and_enabled(
        self, populated: EntityManager
    ) -> None:
        populated.set_entity_enabled("grandchild", False)
        command = DestroyEntity("child_b")
        command.apply(populated)
        command.revert(populated)

        child_b = populated.get_entity("child_b")
        assert child_b is not None
        assert child_b.tags == {"enemy", "spawned"}
        assert child_b.get_component(Transform).position == Vector2(3, 4)
        assert populated.is_entity_enabled("grandchild") is False

    def test_undo_restores_a_queryable_entity(self, populated: EntityManager) -> None:
        """Not just reachable by id -- it has to be indexed again.

        `remove_entity` queues index cleanup keyed by id. If the undo
        recreated the id before that cleanup ran, the new entity's index
        entries would be discarded and it would be invisible to every
        query while still answering `get_entity`.
        """
        command = DestroyEntity("child_b")
        command.apply(command_world := populated)
        command.revert(command_world)

        found = {entity.id for entity in command_world.get_entities_with(Transform)}
        assert "child_b" in found
        assert "grandchild" in found

    def test_the_label_names_the_cascade_size(self, populated: EntityManager) -> None:
        command = DestroyEntity("child_b")
        command.apply(populated)
        assert command.label == "Destroy child_b (+1)"

    def test_rejects_a_missing_entity(self, world: EntityManager) -> None:
        with pytest.raises(EditError, match="No entity"):
            DestroyEntity("nobody").apply(world)


class TestComponentCommands:
    """Attaching and detaching."""

    def test_add_attaches(self, populated: EntityManager) -> None:
        AddComponent("child_a", Tag("Named")).apply(populated)
        entity = populated.get_entity("child_a")
        assert entity is not None
        assert entity.get_component(Tag).name == "Named"

    def test_add_rejects_a_duplicate_type(self, populated: EntityManager) -> None:
        """An entity holds at most one of each type."""
        with pytest.raises(EditError, match="already has a Tag"):
            AddComponent("root", Tag("Another")).apply(populated)

    def test_add_rejects_a_missing_entity(self, world: EntityManager) -> None:
        with pytest.raises(EditError, match="No entity"):
            AddComponent("nobody", Tag()).apply(world)

    def test_remove_detaches(self, populated: EntityManager) -> None:
        RemoveComponent("root", Tag).apply(populated)
        entity = populated.get_entity("root")
        assert entity is not None
        assert not entity.has_component(Tag)

    def test_remove_undo_restores_the_same_instance(
        self, populated: EntityManager
    ) -> None:
        """The detached instance is what the undo puts back, field values
        and all -- not a default-constructed stand-in."""
        entity = populated.get_entity("root")
        assert entity is not None
        original = entity.get_component(Tag)

        command = RemoveComponent("root", Tag)
        command.apply(populated)
        command.revert(populated)

        assert entity.get_component(Tag) is original

    def test_remove_rejects_an_absent_component(self, populated: EntityManager) -> None:
        with pytest.raises(EditError, match="has no Tag"):
            RemoveComponent("child_a", Tag).apply(populated)


class TestSetField:
    """The workhorse."""

    def test_writes_the_field(self, populated: EntityManager) -> None:
        SetField("root", Transform, "rotation", 2.0).apply(populated)
        entity = populated.get_entity("root")
        assert entity is not None
        assert entity.get_component(Transform).rotation == 2.0

    def test_notifies_the_manager(self, populated: EntityManager) -> None:
        """Without this, physics bodies and the spatial index go stale."""
        seen: list[object] = []
        populated.subscribe_component_changed(
            Transform, lambda entity, component: seen.append(entity.id)
        )

        SetField("root", Transform, "rotation", 2.0).apply(populated)
        assert seen == ["root"]

    def test_undo_notifies_too(self, populated: EntityManager) -> None:
        seen: list[object] = []
        command = SetField("root", Transform, "rotation", 2.0)
        command.apply(populated)
        populated.subscribe_component_changed(
            Transform, lambda entity, component: seen.append(entity.id)
        )
        command.revert(populated)
        assert seen == ["root"]

    def test_rejects_an_unknown_field(self, populated: EntityManager) -> None:
        with pytest.raises(EditError, match="has no field 'nonsense'"):
            SetField("root", Transform, "nonsense", 1).apply(populated)

    def test_rejects_an_absent_component(self, populated: EntityManager) -> None:
        with pytest.raises(EditError, match="has no Tag"):
            SetField("child_a", Tag, "name", "x").apply(populated)

    def test_a_mutable_captured_value_is_copied(self, world: EntityManager) -> None:
        """`Color` is a mutable dataclass.

        Holding the live object would let a later in-place edit change
        what the undo restores.
        """
        from tests.test_scene_serializer import FakeTexture

        entity = world.create_entity("visible")
        sprite = Sprite(texture=FakeTexture("x.png"), color=Color(1, 2, 3, 4))
        entity.add_component(sprite)

        command = SetField("visible", Sprite, "color", Color(9, 9, 9, 9))
        command.apply(world)
        command.revert(world)

        assert sprite.color == Color(1, 2, 3, 4)


class TestCoalescing:
    """Folding a gesture into one undo entry."""

    def test_two_writes_to_the_same_field_merge(self, populated: EntityManager) -> None:
        first = SetField("root", Transform, "rotation", 1.0)
        second = SetField("root", Transform, "rotation", 2.0)
        first.apply(populated)
        second.apply(populated)

        merged = second.coalesce_with(first)
        assert merged is not None

    def test_the_merged_command_undoes_to_the_start_of_the_gesture(
        self, populated: EntityManager
    ) -> None:
        """The point of coalescing: one drag, one undo, back to the start.

        Not back to the previous frame of the drag.
        """
        entity = populated.get_entity("root")
        assert entity is not None
        assert entity.get_component(Transform).rotation == 0.0

        first = SetField("root", Transform, "rotation", 1.0)
        first.apply(populated)
        second = SetField("root", Transform, "rotation", 2.0)
        second.apply(populated)

        merged = second.coalesce_with(first)
        assert merged is not None
        merged.revert(populated)

        assert entity.get_component(Transform).rotation == 0.0

    def test_a_different_field_does_not_merge(self, populated: EntityManager) -> None:
        first = SetField("root", Transform, "rotation", 1.0)
        second = SetField("root", Transform, "scale", Vector2(2, 2))
        assert second.coalesce_with(first) is None

    def test_a_different_entity_does_not_merge(self, populated: EntityManager) -> None:
        first = SetField("root", Transform, "rotation", 1.0)
        second = SetField("child_a", Transform, "rotation", 1.0)
        assert second.coalesce_with(first) is None

    def test_a_different_command_type_does_not_merge(
        self, populated: EntityManager
    ) -> None:
        first = SetEnabled("root", False)
        second = SetField("root", Transform, "rotation", 1.0)
        assert second.coalesce_with(first) is None

    def test_commands_decline_to_merge_by_default(
        self, populated: EntityManager
    ) -> None:
        """Declining is the safe answer, so it is the base behaviour."""
        first = SetEnabled("root", False)
        second = SetEnabled("root", True)
        assert second.coalesce_with(first) is None


class TestSetParent:
    """Re-parenting."""

    def test_moves_a_child(self, populated: EntityManager) -> None:
        SetParent("child_a", "child_b").apply(populated)
        assert populated.parent_of("child_a") == "child_b"
        assert "child_a" not in populated.children_of("root")

    def test_detaches_with_none(self, populated: EntityManager) -> None:
        SetParent("child_a", None).apply(populated)
        assert populated.parent_of("child_a") is None

    def test_a_cycle_is_an_edit_error(self, populated: EntityManager) -> None:
        """`EntityManager` raises `ValueError`; callers see one error type."""
        with pytest.raises(EditError):
            SetParent("root", "grandchild").apply(populated)

    def test_a_missing_parent_is_an_edit_error(self, populated: EntityManager) -> None:
        with pytest.raises(EditError):
            SetParent("child_a", "nobody").apply(populated)

    def test_a_missing_child_is_an_edit_error(self, populated: EntityManager) -> None:
        with pytest.raises(EditError, match="No entity"):
            SetParent("nobody", "root").apply(populated)


class TestSetEnabledAndTags:
    """The two pieces of state that live outside components."""

    def test_disables(self, populated: EntityManager) -> None:
        SetEnabled("root", False).apply(populated)
        assert populated.is_entity_enabled("root") is False

    def test_rejects_a_missing_entity(self, world: EntityManager) -> None:
        """`set_entity_enabled` discards an unknown id silently.

        Letting that through would make the command undoable but
        ineffective -- a history entry for a change that never happened.
        """
        with pytest.raises(EditError, match="No entity"):
            SetEnabled("nobody", False).apply(world)

    def test_replaces_the_tag_set(self, populated: EntityManager) -> None:
        SetTags("child_b", {"boss"}).apply(populated)
        entity = populated.get_entity("child_b")
        assert entity is not None
        assert entity.tags == {"boss"}

    def test_tags_undo_restores_the_whole_previous_set(
        self, populated: EntityManager
    ) -> None:
        command = SetTags("child_b", {"boss"})
        command.apply(populated)
        command.revert(populated)
        entity = populated.get_entity("child_b")
        assert entity is not None
        assert entity.tags == {"enemy", "spawned"}


class TestApplyTwiceIsRefused:
    """A command is a record of one application."""

    def test_apply_twice_raises(self, populated: EntityManager) -> None:
        """The second apply would overwrite the captured inverse.

        It would capture the state the *first* apply produced, so the undo
        would restore the new value rather than the original.
        """
        command = SetField("root", Transform, "rotation", 1.0)
        command.apply(populated)
        with pytest.raises(EditError, match="already applied"):
            command.apply(populated)

    def test_revert_before_apply_raises(self, populated: EntityManager) -> None:
        command = SetField("root", Transform, "rotation", 1.0)
        with pytest.raises(EditError, match="not applied"):
            command.revert(populated)

    def test_apply_revert_apply_is_allowed(self, populated: EntityManager) -> None:
        """Which is what a redo is."""
        command = SetField("root", Transform, "rotation", 1.0)
        command.apply(populated)
        command.revert(populated)
        command.apply(populated)
        entity = populated.get_entity("root")
        assert entity is not None
        assert entity.get_component(Transform).rotation == 1.0


class TestCompositeCommand:
    """Grouping."""

    def test_applies_every_member(self, populated: EntityManager) -> None:
        group = CompositeCommand(
            "Move both",
            [
                SetField("child_a", Transform, "rotation", 1.0),
                SetField("child_b", Transform, "rotation", 1.0),
            ],
        )
        group.apply(populated)

        for entity_id in ("child_a", "child_b"):
            entity = populated.get_entity(entity_id)
            assert entity is not None
            assert entity.get_component(Transform).rotation == 1.0

    def test_reverts_in_reverse_order(self, populated: EntityManager) -> None:
        """Order matters when members interact.

        Creating a parent then a child must undo child-first, or the
        parent's removal cascades the child away and the child's own
        revert finds nothing.
        """
        group = CompositeCommand(
            "Build",
            [
                CreateEntity("new_parent"),
                CreateEntity("new_child", parent_id="new_parent"),
            ],
        )
        group.apply(populated)
        group.revert(populated)

        assert populated.get_entity("new_parent") is None
        assert populated.get_entity("new_child") is None

    def test_a_failing_member_rolls_the_group_back(
        self, populated: EntityManager
    ) -> None:
        """A half-applied group is not a state anything should observe."""
        before = world_digest(populated)
        group = CompositeCommand(
            "Partly impossible",
            [
                SetField("child_a", Transform, "rotation", 1.0),
                AddComponent("root", Tag("Duplicate")),  # root already has a Tag
            ],
        )

        with pytest.raises(EditError):
            group.apply(populated)

        assert world_digest(populated) == before

    def test_a_rolled_back_group_is_not_marked_applied(
        self, populated: EntityManager
    ) -> None:
        """So the stack never offers it for undo."""
        group = CompositeCommand(
            "Partly impossible",
            [AddComponent("root", Tag("Duplicate"))],
        )
        with pytest.raises(EditError):
            group.apply(populated)
        assert group.applied is False

    def test_describe_includes_the_children(self, populated: EntityManager) -> None:
        group = CompositeCommand("Move both", [SetEnabled("root", False)])
        description = group.describe()
        assert description["label"] == "Move both"
        assert len(description["children"]) == 1


class TestDescribe:
    """What the journal and an agent's reply carry."""

    def test_setfield_reports_both_values(self, populated: EntityManager) -> None:
        command = SetField("root", Transform, "rotation", 2.0)
        command.apply(populated)
        description = command.describe()

        assert description["entity_id"] == "root"
        assert description["component"] == "Transform"
        assert description["field"] == "rotation"
        assert description["from"] == repr(0.0)
        assert description["to"] == repr(2.0)

    def test_destroy_reports_what_cascaded(self, populated: EntityManager) -> None:
        command = DestroyEntity("child_b")
        command.apply(populated)
        assert command.describe()["cascaded"] == ["grandchild"]

    def test_every_description_names_its_command(
        self, populated: EntityManager
    ) -> None:
        command = SetEnabled("root", False)
        assert command.describe()["command"] == "SetEnabled"


class TestSnapshotSubtree:
    """The capture `DestroyEntity` relies on."""

    def test_is_ordered_parents_first(self, populated: EntityManager) -> None:
        """So restoring never names a parent that does not exist yet."""
        snapshots = snapshot_subtree(populated, "root")
        order = [snapshot.entity_id for snapshot in snapshots]

        assert order.index("root") < order.index("child_b")
        assert order.index("child_b") < order.index("grandchild")

    def test_excludes_childof(self, populated: EntityManager) -> None:
        """The link is restored through `set_parent`, which maintains the
        parent -> children index; re-attaching the component would set the
        field and leave that index empty."""
        snapshots = snapshot_subtree(populated, "child_b")
        names = [
            type(component).__name__
            for snapshot in snapshots
            for component in snapshot.components
        ]
        assert "ChildOf" not in names

    def test_records_the_parent_separately(self, populated: EntityManager) -> None:
        snapshots = snapshot_subtree(populated, "child_b")
        assert snapshots[0].parent_id == "root"

    def test_captures_only_the_subtree(self, populated: EntityManager) -> None:
        snapshots = snapshot_subtree(populated, "child_b")
        assert {snapshot.entity_id for snapshot in snapshots} == {
            "child_b",
            "grandchild",
        }
