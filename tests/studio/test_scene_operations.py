"""Saving, opening, emptying, and duplicating.

These are the four an editor is expected to have and Studio did not. They
go through the operation registry like everything else, so the menu's
Save and an agent's `scene` call are the same action -- which is also why
they are tested here rather than against the menu.

`scene` carries all four whole-scene verbs behind one `operation`
argument, as `history` does: the flat surface is budgeted, and a client's
tool limit is better spent on the verbs used every minute.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.studio.commands.entity import DuplicateEntity
from pyguara.studio.ops.registry import OperationRegistry
from pyguara.studio.session import StudioSession


class FakeSerializer:
    """A serializer backed by a dict instead of a disk."""

    def __init__(self) -> None:
        self.saves: dict[str, list[str]] = {}
        self.persistence = self

    def save_scene(self, scene: Any, filename: str) -> bool:
        self.saves[filename] = [e.id for e in scene.entity_manager.get_all_entities()]
        return True

    def load_scene(self, scene: Any, filename: str) -> bool:
        if filename not in self.saves:
            return False
        world = scene.entity_manager
        world.clear()
        for entity_id in self.saves[filename]:
            world.create_entity(entity_id)
        return True

    def list_saves(self) -> list[str]:
        return list(self.saves)

    def exists(self, key: str) -> bool:
        return key in self.saves


class FakeScene:
    """Just enough scene for the serializer to work on."""

    def __init__(self, world: EntityManager, name: str = "level") -> None:
        self.entity_manager = world
        self.name = name


@pytest.fixture
def scene_session(populated: EntityManager, core_registry) -> StudioSession:
    """A session that can reach a scene, as `attach_studio` builds one."""
    from pyguara.studio.sceneio import SceneIO

    serializer = FakeSerializer()
    scene = FakeScene(populated)
    return StudioSession(
        populated,
        scene_name="level",
        component_registry=core_registry,
        scene_io=SceneIO(serializer, lambda: scene),
    )


def _call(
    ops: OperationRegistry,
    session: StudioSession,
    operation_name: str,
    /,
    **arguments: object,
) -> Any:
    """Invoke an operation, asserting it succeeded.

    Positional-only up to the operation's name, because `scene` takes an
    argument called `name` and a keyword of that name would otherwise bind
    to this function's own parameter instead.
    """
    outcome = ops.invoke(session, operation_name, dict(arguments))
    assert outcome.ok, outcome.error
    return outcome.result


def _error(
    ops: OperationRegistry,
    session: StudioSession,
    operation_name: str,
    /,
    **arguments: object,
) -> str:
    """Invoke an operation, asserting it failed, and return the message."""
    outcome = ops.invoke(session, operation_name, dict(arguments))
    assert not outcome.ok, f"expected a failure, got {outcome.result!r}"
    assert outcome.error is not None
    return outcome.error


@pytest.mark.unit
class TestSaving:
    def test_it_saves_under_the_scenes_own_name(
        self, ops: OperationRegistry, scene_session: StudioSession
    ) -> None:
        result = _call(ops, scene_session, "scene", operation="save")

        assert result["saved"] == "level"
        assert "level" in _call(ops, scene_session, "scene", operation="list")["scenes"]

    def test_a_name_can_be_given(
        self, ops: OperationRegistry, scene_session: StudioSession
    ) -> None:
        _call(ops, scene_session, "scene", operation="save", name="checkpoint")

        assert _call(ops, scene_session, "scene", operation="list")["scenes"] == [
            "checkpoint"
        ]

    def test_saving_clears_the_history(
        self, ops: OperationRegistry, scene_session: StudioSession
    ) -> None:
        """Undoing past a save leaves the file and the world disagreeing,
        with nothing on screen to show it."""
        _call(ops, scene_session, "set_enabled", entity_id="root", enabled=False)
        assert scene_session.stack.can_undo

        _call(ops, scene_session, "scene", operation="save")

        assert not scene_session.stack.can_undo

    def test_a_session_that_cannot_reach_a_scene_says_so(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """Rather than failing somewhere deeper. A session built by hand
        has no container behind it, which is every test that does not boot
        an application."""
        message = _error(ops, session, "scene", operation="save")

        assert "cannot reach the scene serializer" in message


@pytest.mark.unit
class TestOpening:
    def test_it_replaces_the_contents(
        self,
        ops: OperationRegistry,
        scene_session: StudioSession,
        populated: EntityManager,
    ) -> None:
        _call(ops, scene_session, "scene", operation="save", name="before")
        populated.create_entity("added_later")

        _call(ops, scene_session, "scene", operation="open", name="before")

        assert populated.get_entity("added_later") is None
        assert populated.get_entity("root") is not None

    def test_opening_clears_the_history(
        self, ops: OperationRegistry, scene_session: StudioSession
    ) -> None:
        """Every command on the stack describes a world that no longer
        exists, so reverting one would apply its inverse to entities it
        never touched."""
        _call(ops, scene_session, "scene", operation="save", name="before")
        _call(ops, scene_session, "set_enabled", entity_id="root", enabled=False)
        assert scene_session.stack.can_undo

        _call(ops, scene_session, "scene", operation="open", name="before")

        assert not scene_session.stack.can_undo

    def test_an_unknown_name_lists_the_real_ones(
        self, ops: OperationRegistry, scene_session: StudioSession
    ) -> None:
        _call(ops, scene_session, "scene", operation="save", name="level_one")

        message = _error(ops, scene_session, "scene", operation="open", name="typo")

        assert "level_one" in message

    def test_a_name_is_required(
        self, ops: OperationRegistry, scene_session: StudioSession
    ) -> None:
        assert "name" in _error(ops, scene_session, "scene", operation="open")


@pytest.mark.unit
class TestEmptying:
    def test_it_removes_everything(
        self,
        ops: OperationRegistry,
        scene_session: StudioSession,
        populated: EntityManager,
    ) -> None:
        _call(ops, scene_session, "scene", operation="new")

        assert list(populated.get_all_entities()) == []

    def test_it_is_one_undoable_entry(
        self,
        ops: OperationRegistry,
        scene_session: StudioSession,
        populated: EntityManager,
    ) -> None:
        """A destroy of every root inside one transaction, rather than a
        `clear()` that nothing could take back."""
        before = sorted(e.id for e in populated.get_all_entities())

        _call(ops, scene_session, "scene", operation="new")
        assert len(scene_session.stack.undo_labels) == 1
        scene_session.undo()

        assert sorted(e.id for e in populated.get_all_entities()) == before


@pytest.mark.unit
class TestTheVerbs:
    def test_an_unknown_verb_names_the_valid_ones(
        self, ops: OperationRegistry, scene_session: StudioSession
    ) -> None:
        message = _error(ops, scene_session, "scene", operation="delete")

        for verb in ("list", "new", "open", "save"):
            assert verb in message

    def test_the_whole_scene_verbs_stay_behind_one_operation(
        self, ops: OperationRegistry
    ) -> None:
        """The flat surface is budgeted: a client's tool limit is spent on
        the verbs used every minute, and saving is not one."""
        names = {operation.name for operation in ops}

        assert "scene" in names
        for absent in ("save_scene", "open_scene", "new_scene", "list_scenes"):
            assert absent not in names


@pytest.mark.unit
class TestDuplicating:
    def test_it_copies_the_whole_subtree(
        self,
        ops: OperationRegistry,
        session: StudioSession,
        populated: EntityManager,
    ) -> None:
        from pyguara.studio.commands.entity import snapshot_subtree

        subtree = len(snapshot_subtree(populated, "root"))
        before = sum(1 for _ in populated.get_all_entities())
        assert subtree > 1, "the fixture's root should own something"

        result = _call(ops, session, "duplicate_entity", entity_id="root")

        # The subtree, not the world: the fixture has a second root that
        # nothing hangs off, and copying it too would be a bug.
        assert sum(1 for _ in populated.get_all_entities()) == before + subtree
        assert len(result["created"]) == subtree
        assert result["created"][0] == "root_copy"

    def test_the_copy_is_its_own_entity(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        """Sharing a component instance would mean editing either changed
        both, and the second would never be notified."""
        session.apply(DuplicateEntity("root"), action="duplicate_entity")

        original = populated.get_entity("root").get_component(Transform)
        copy = populated.get_entity("root_copy").get_component(Transform)
        assert copy is not original
        copy.position = Vector2(999, 999)
        assert original.position != copy.position

    def test_the_copied_children_hang_off_the_copied_parent(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        """Not off the original, which would silently move a subtree's
        worth of entities under the thing being copied."""
        session.apply(DuplicateEntity("root"), action="duplicate_entity")

        for child_id in populated.children_of("root_copy"):
            assert child_id.endswith("_copy")
        assert len(populated.children_of("root")) == len(
            populated.children_of("root_copy")
        )

    def test_undo_removes_every_copy(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        before = sorted(e.id for e in populated.get_all_entities())

        session.apply(DuplicateEntity("root"), action="duplicate_entity")
        session.undo()

        assert sorted(e.id for e in populated.get_all_entities()) == before

    def test_redo_reuses_the_same_ids(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        """Minting fresh ones would leave anything holding an id -- a
        selection, an agent's next call -- pointing at an entity that no
        longer exists."""
        command = DuplicateEntity("root")
        session.apply(command, action="duplicate_entity")
        minted = command.created_ids

        session.undo()
        session.redo()

        assert command.created_ids == minted
        for entity_id in minted:
            assert populated.get_entity(entity_id) is not None

    def test_duplicating_twice_does_not_collide(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        session.apply(DuplicateEntity("root"), action="duplicate_entity")
        session.apply(DuplicateEntity("root"), action="duplicate_entity")

        assert populated.get_entity("root_copy") is not None
        assert populated.get_entity("root_copy_2") is not None

    def test_an_unknown_entity_is_an_error(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "nope" in _error(ops, session, "duplicate_entity", entity_id="nope")


@pytest.mark.unit
class TestResourcesAreShared:
    """A resource is a handle to one loaded asset, not a value to copy."""

    def test_deep_copying_one_gives_the_same_object(self) -> None:
        """`Resource.__deepcopy__` returns self. Duplicating an entity with
        a sprite failed outright on this -- "cannot pickle 'mgl.Texture'" --
        and succeeding would have been worse: a second upload of the same
        image per copy.

        On the type rather than at the call site, because a call site
        cannot see a resource nested inside a component's own dataclass
        field, which is exactly where the failure came from.
        """
        import copy

        from pyguara.resources.types import Texture

        class FakeTexture(Texture):
            def __init__(self) -> None:
                super().__init__("assets/fake.png")

            @property
            def width(self) -> int:
                return 1

            @property
            def height(self) -> int:
                return 1

            @property
            def native_handle(self) -> object:
                return self

        texture = FakeTexture()

        assert copy.deepcopy(texture) is texture
        assert copy.deepcopy({"a": texture, "b": [texture]})["b"][0] is texture

    def test_a_duplicated_sprite_shares_its_texture(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        from pyguara.graphics.components.sprite import Sprite
        from pyguara.resources.types import Texture

        class FakeTexture(Texture):
            def __init__(self) -> None:
                super().__init__("assets/fake.png")

            @property
            def width(self) -> int:
                return 8

            @property
            def height(self) -> int:
                return 8

            @property
            def native_handle(self) -> object:
                return self

        texture = FakeTexture()
        populated.get_entity("root").add_component(Sprite(texture=texture))

        session.apply(DuplicateEntity("root"), action="duplicate_entity")

        copied = populated.get_entity("root_copy").get_component(Sprite)
        assert copied.texture is texture
