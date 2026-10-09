"""`studio.model.snapshot`: reading a scene, and comparing two readings.

The diff is the load-bearing part. An agent's loop is edit, run, check,
and "check" is almost always "what changed, and was it only what I meant
to change?". These tests pin that a diff answers exactly that -- including
the case that matters most, where the answer is "nothing".
"""

from __future__ import annotations

from pyguara.common.components import Tag, Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.sprite import Sprite
from pyguara.studio.commands.entity import (
    AddComponent,
    CreateEntity,
    DestroyEntity,
    SetEnabled,
    SetField,
    SetParent,
    SetTags,
)
from pyguara.studio.model.snapshot import (
    diff_snapshots,
    read_component,
    snapshot_scene,
)
from pyguara.studio.model.values import UNENCODABLE_KEY


class TestReadComponent:
    """One component's fields, encoded."""

    def test_reads_a_dataclass(self) -> None:
        values = read_component(Tag("Hero"))
        assert values == {"name": "Hero"}

    def test_reads_a_property_component(self) -> None:
        """`Transform` is not a dataclass."""
        values = read_component(Transform(position=Vector2(3, 4)))
        assert values["position"] == {"x": 3.0, "y": 4.0}
        assert values["rotation"] == 0.0

    def test_reads_an_attribute_with_no_class_annotation(self) -> None:
        transform = Transform()
        transform.interpolate = True
        assert read_component(transform)["interpolate"] is True

    def test_an_unencodable_field_is_marked_not_dropped(self) -> None:
        """So the reader knows the field is there and why it is opaque."""
        from tests.test_scene_serializer import FakeTexture

        values = read_component(Sprite(texture=FakeTexture("x.png")))
        assert values["material"] is None
        assert "texture" in values


class TestSnapshot:
    """Reading a world."""

    def test_captures_every_entity(self, populated: EntityManager) -> None:
        snapshot = snapshot_scene(populated)
        assert set(snapshot.entity_ids) == {
            "root",
            "child_a",
            "child_b",
            "grandchild",
            "loose",
        }

    def test_captures_the_hierarchy_both_ways(self, populated: EntityManager) -> None:
        snapshot = snapshot_scene(populated)
        assert snapshot.entities["child_b"].parent_id == "root"
        assert snapshot.entities["root"].children == ("child_a", "child_b")

    def test_captures_tags_sorted(self, populated: EntityManager) -> None:
        """`entity.tags` is a set, whose iteration order is not stable
        across processes -- two reads of the same state must compare
        equal."""
        snapshot = snapshot_scene(populated)
        assert snapshot.entities["child_b"].tags == ("enemy", "spawned")

    def test_captures_enabled_state(self, populated: EntityManager) -> None:
        snapshot = snapshot_scene(populated)
        assert snapshot.entities["loose"].enabled is False
        assert snapshot.entities["root"].enabled is True

    def test_captures_component_field_values(self, populated: EntityManager) -> None:
        snapshot = snapshot_scene(populated)
        transform = snapshot.entities["root"].components["Transform"]
        assert transform["position"] == {"x": 10.0, "y": 20.0}

    def test_records_the_scene_name(self, populated: EntityManager) -> None:
        assert snapshot_scene(populated, scene_name="level_1").scene_name == "level_1"

    def test_roots_are_the_unparented(self, populated: EntityManager) -> None:
        assert snapshot_scene(populated).roots == ("loose", "root")

    def test_length_is_the_entity_count(self, populated: EntityManager) -> None:
        assert len(snapshot_scene(populated)) == 5

    def test_structure_only_skips_field_values(self, populated: EntityManager) -> None:
        """Much cheaper, and all a structural diff needs."""
        snapshot = snapshot_scene(populated, include_components=False)
        assert snapshot.entities["root"].components["Transform"] == {}
        assert "Transform" in snapshot.entities["root"].components

    def test_an_empty_world_snapshots_cleanly(self, world: EntityManager) -> None:
        snapshot = snapshot_scene(world)
        assert len(snapshot) == 0
        assert snapshot.roots == ()


class TestSnapshotSerialization:
    """The dict forms an agent actually receives."""

    def test_entities_come_out_in_id_order(self, populated: EntityManager) -> None:
        data = snapshot_scene(populated).to_dict()
        ids = [entity["id"] for entity in data["entities"]]
        assert ids == sorted(ids)

    def test_empty_collections_are_omitted(self, populated: EntityManager) -> None:
        """`"tags": []` on nine hundred entities is pure cost."""
        data = snapshot_scene(populated).to_dict()
        child_a = next(e for e in data["entities"] if e["id"] == "child_a")
        assert "tags" not in child_a
        assert "children" not in child_a

    def test_enabled_is_only_reported_when_false(
        self, populated: EntityManager
    ) -> None:
        data = snapshot_scene(populated).to_dict()
        by_id = {entity["id"]: entity for entity in data["entities"]}
        assert "enabled" not in by_id["root"]
        assert by_id["loose"]["enabled"] is False

    def test_summary_is_counts_only(self, populated: EntityManager) -> None:
        """The token-cheap first look at an unfamiliar scene."""
        summary = snapshot_scene(populated).summary()
        assert summary["entity_count"] == 5
        assert summary["root_count"] == 2
        assert summary["components"]["Transform"] == 5
        assert "entities" not in summary

    def test_summary_counts_per_component_type(self, populated: EntityManager) -> None:
        summary = snapshot_scene(populated).summary()
        assert summary["components"]["Tag"] == 1
        assert summary["components"]["ChildOf"] == 3


class TestDiffDetectsNothing:
    """The most important answer."""

    def test_two_reads_of_an_unchanged_world_are_equal(
        self, populated: EntityManager
    ) -> None:
        before = snapshot_scene(populated)
        after = snapshot_scene(populated)
        assert diff_snapshots(before, after).is_empty

    def test_an_empty_diff_says_so_explicitly(self, populated: EntityManager) -> None:
        """A reader never has to interpret an empty object."""
        before = snapshot_scene(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert diff.to_dict() == {"changed": False}

    def test_apply_then_revert_leaves_no_diff(self, populated: EntityManager) -> None:
        """The property the whole command layer rests on, checked through
        the same lens an agent would use."""
        before = snapshot_scene(populated)

        command = DestroyEntity("child_b")
        command.apply(populated)
        command.revert(populated)

        assert diff_snapshots(before, snapshot_scene(populated)).is_empty


class TestDiffDetectsChanges:
    """One test per kind of change."""

    def test_detects_an_added_entity(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        CreateEntity("fresh").apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert diff.added == ("fresh",)

    def test_detects_a_removed_entity(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        DestroyEntity("loose").apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert diff.removed == ("loose",)

    def test_detects_a_cascade_as_several_removals(
        self, populated: EntityManager
    ) -> None:
        before = snapshot_scene(populated)
        DestroyEntity("child_b").apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert diff.removed == ("child_b", "grandchild")

    def test_detects_an_added_component(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        AddComponent("child_a", Tag("Named")).apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert diff.components_added == (("child_a", "Tag"),)

    def test_detects_a_field_change_with_both_values(
        self, populated: EntityManager
    ) -> None:
        before = snapshot_scene(populated)
        SetField("root", Transform, "rotation", 1.5).apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))

        assert len(diff.fields) == 1
        change = diff.fields[0]
        assert change.entity_id == "root"
        assert change.component == "Transform"
        assert change.field_name == "rotation"
        assert change.before == 0.0
        assert change.after == 1.5

    def test_detects_a_tag_change(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        SetTags("root", {"boss"}).apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert diff.tags_changed == ("root",)

    def test_detects_an_enabled_change(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        SetEnabled("root", False).apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert diff.enabled_changed == ("root",)

    def test_detects_a_reparenting(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        SetParent("child_a", "child_b").apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert "child_a" in diff.reparented

    def test_a_reparenting_also_shows_in_the_childof_field(
        self, populated: EntityManager
    ) -> None:
        """`set_parent` is implemented as a `ChildOf` swap, so the
        component field changes too. Both are reported, which is honest:
        they are two facts about the same edit."""
        before = snapshot_scene(populated)
        SetParent("child_a", "child_b").apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))

        parent_fields = [
            change for change in diff.fields if change.field_name == "parent_id"
        ]
        assert parent_fields


class TestDiffScoping:
    """What a diff deliberately does not report."""

    def test_a_new_entitys_fields_are_not_listed_individually(
        self, populated: EntityManager
    ) -> None:
        """Already reported as an addition; repeating it per field would
        bury the actual edits."""
        before = snapshot_scene(populated)
        CreateEntity("fresh", components=[Transform(), Tag("X")]).apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))

        assert diff.added == ("fresh",)
        assert all(change.entity_id != "fresh" for change in diff.fields)

    def test_a_removed_entitys_components_are_not_listed(
        self, populated: EntityManager
    ) -> None:
        before = snapshot_scene(populated)
        DestroyEntity("loose").apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))

        assert diff.removed == ("loose",)
        assert diff.components_removed == ()


class TestDiffStability:
    """A diff is read by a machine, so it has to be deterministic."""

    def test_every_list_is_sorted(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        CreateEntity("zeta").apply(populated)
        CreateEntity("alpha").apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))
        assert diff.added == ("alpha", "zeta")

    def test_the_same_change_diffs_identically_twice(
        self, populated: EntityManager
    ) -> None:
        before = snapshot_scene(populated)
        SetField("root", Transform, "rotation", 1.5).apply(populated)
        after = snapshot_scene(populated)

        assert (
            diff_snapshots(before, after).to_dict()
            == diff_snapshots(before, after).to_dict()
        )


class TestDiffSerialization:
    """The dict form."""

    def test_omits_empty_sections(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        SetEnabled("root", False).apply(populated)
        data = diff_snapshots(before, snapshot_scene(populated)).to_dict()

        assert data["changed"] is True
        assert data["enabled_changed"] == ["root"]
        assert "added" not in data
        assert "fields" not in data

    def test_component_pairs_become_objects(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        AddComponent("child_a", Tag("Named")).apply(populated)
        data = diff_snapshots(before, snapshot_scene(populated)).to_dict()

        assert data["components_added"] == [{"entity": "child_a", "component": "Tag"}]

    def test_a_field_change_carries_both_values(self, populated: EntityManager) -> None:
        before = snapshot_scene(populated)
        SetField("root", Transform, "rotation", 1.5).apply(populated)
        data = diff_snapshots(before, snapshot_scene(populated)).to_dict()

        assert data["fields"][0]["before"] == 0.0
        assert data["fields"][0]["after"] == 1.5


class TestUnencodableMarkerInSnapshots:
    """An opaque field must not read as an edit on every snapshot."""

    def test_an_opaque_field_is_stable_across_reads(self, world: EntityManager) -> None:
        """A marker holding a `repr` with a memory address in it would
        differ on every read and make every diff non-empty."""
        from tests.test_scene_serializer import FakeTexture

        entity = world.create_entity("visible")
        entity.add_component(Sprite(texture=FakeTexture("x.png")))

        before = snapshot_scene(world)
        after = snapshot_scene(world)
        assert diff_snapshots(before, after).is_empty

    def test_a_resource_reads_as_its_path(self, world: EntityManager) -> None:
        """Which is why it is stable: the path does not move."""
        from tests.test_scene_serializer import FakeTexture

        entity = world.create_entity("visible")
        entity.add_component(Sprite(texture=FakeTexture("art/hero.png")))

        snapshot = snapshot_scene(world)
        texture = snapshot.entities["visible"].components["Sprite"]["texture"]
        assert texture == {"__resource__": "art/hero.png"}
        assert UNENCODABLE_KEY not in texture


class TestDerivedFields:
    """Derived views are shown in a schema and skipped by a snapshot."""

    def test_one_edit_reads_as_one_change(self, populated: EntityManager) -> None:
        """Setting `Transform.rotation` also moves `rotation_degrees` and
        `world_rotation`. A diff that says so three times buries the edits
        that matter."""
        before = snapshot_scene(populated)
        SetField("root", Transform, "rotation", 1.5).apply(populated)
        diff = diff_snapshots(before, snapshot_scene(populated))

        assert [change.field_name for change in diff.fields] == ["rotation"]

    def test_a_snapshot_omits_them(self, populated: EntityManager) -> None:
        snapshot = snapshot_scene(populated)
        transform = snapshot.entities["root"].components["Transform"]

        assert "rotation" in transform
        for name in ("rotation_degrees", "world_rotation", "world_position"):
            assert name not in transform, name

    def test_previous_position_is_omitted(self, populated: EntityManager) -> None:
        """`SceneManager.fixed_update()` rewrites it every tick, so
        including it would make every snapshot taken across a frame
        differ."""
        snapshot = snapshot_scene(populated)
        assert (
            "previous_position"
            not in (snapshot.entities["root"].components["Transform"])
        )

    def test_a_frame_boundary_does_not_look_like_an_edit(
        self, populated: EntityManager
    ) -> None:
        """What omitting `previous_position` buys: an agent that steps the
        loop and re-reads the scene sees no spurious change."""
        from pyguara.common.components import Transform as T

        entity = populated.get_entity("root")
        assert entity is not None
        transform = entity.get_component(T)
        transform.interpolate = True

        before = snapshot_scene(populated)
        # What `SceneManager._snapshot_interpolated` does each fixed tick.
        transform.previous_position = transform.position

        assert diff_snapshots(before, snapshot_scene(populated)).is_empty

    def test_the_schema_still_reports_them(self) -> None:
        """An inspector showing `world_position` beside `position` is
        useful; it is only a *snapshot* that must not record it."""
        from pyguara.studio.model.schema import describe_component

        schema = describe_component(Transform)
        world_position = schema.field("world_position")
        assert world_position is not None
        assert world_position.derived is True

    def test_stateful_fields_excludes_them(self) -> None:
        from pyguara.studio.model.schema import describe_component

        schema = describe_component(Transform)
        names = {field.name for field in schema.stateful_fields}
        assert "position" in names
        assert "world_position" not in names
