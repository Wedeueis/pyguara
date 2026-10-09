"""Tests for scene serialization."""

from typing import Any

import pytest

from pyguara.common.components import ResourceLink, Tag, Transform
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.sprite import Sprite
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.types import StorageBackend
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.types import BodyType, ShapeType
from pyguara.resources.types import Texture
from pyguara.scene.base import Scene
from pyguara.scene.serializer import RESOURCE_KEY, SceneSerializer


class MockStorageBackend(StorageBackend):
    """In-memory blob store for testing."""

    def __init__(self) -> None:
        self._storage: dict[str, bytes] = {}

    def save(self, key: str, blob: bytes) -> bool:
        self._storage[key] = blob
        return True

    def load(self, key: str) -> bytes | None:
        return self._storage.get(key)

    def delete(self, key: str) -> bool:
        if key in self._storage:
            del self._storage[key]
            return True
        return False

    def list_keys(self) -> list[str]:
        return list(self._storage)


class MockScene(Scene):
    """Minimal scene implementation for testing."""

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def render(self, world_renderer: Any, ui_renderer: Any) -> None:
        pass


@pytest.fixture
def storage_backend() -> MockStorageBackend:
    """Create a mock storage backend."""
    return MockStorageBackend()


@pytest.fixture
def persistence_manager(storage_backend: MockStorageBackend) -> PersistenceManager:
    """Create a persistence manager with mock storage."""
    return PersistenceManager(storage_backend)


@pytest.fixture
def component_registry():
    """Create and populate a component registry for testing."""
    from pyguara.prefabs.registry import ComponentRegistry

    registry = ComponentRegistry()
    registry.register(Tag)
    registry.register(Transform)
    registry.register(RigidBody)
    registry.register(Collider)
    registry.register(ResourceLink)
    return registry


@pytest.fixture
def serializer(
    persistence_manager: PersistenceManager, component_registry
) -> SceneSerializer:
    """Create a scene serializer."""
    return SceneSerializer(persistence_manager, component_registry)


@pytest.fixture
def scene() -> MockScene:
    """Create a test scene."""
    dispatcher = EventDispatcher()
    return MockScene("test_scene", dispatcher)


class TestSceneSerializerBasics:
    """Test basic serializer functionality."""

    def test_serializer_creation(
        self, persistence_manager: PersistenceManager, component_registry
    ) -> None:
        """SceneSerializer can be instantiated."""
        serializer = SceneSerializer(persistence_manager, component_registry)
        assert serializer.persistence is persistence_manager
        assert serializer._registry.has("Tag")
        assert serializer._registry.has("Transform")

    def test_supported_components(self, serializer: SceneSerializer) -> None:
        """Serializer supports expected component types."""
        assert serializer._registry.get("Tag") is Tag
        assert serializer._registry.get("Transform") is Transform
        assert serializer._registry.get("RigidBody") is RigidBody
        assert serializer._registry.get("Collider") is Collider
        assert serializer._registry.get("ResourceLink") is ResourceLink


class TestSaveScene:
    """Test scene saving functionality."""

    def test_save_empty_scene(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Saving an empty scene succeeds."""
        result = serializer.save_scene(scene, "empty_scene")
        assert result is True

    def test_save_scene_with_entity(
        self,
        serializer: SceneSerializer,
        scene: MockScene,
        storage_backend: MockStorageBackend,
    ) -> None:
        """Saving a scene with an entity stores the entity data."""
        entity = scene.entity_manager.create_entity("player")
        entity.add_component(Tag(name="Player"))

        result = serializer.save_scene(scene, "scene_with_entity")

        assert result is True
        assert "scene_with_entity" in storage_backend._storage

    def test_save_scene_with_transform(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Transform component data is serialized correctly."""
        entity = scene.entity_manager.create_entity()
        transform = Transform()
        transform.position = Vector2(100, 200)
        transform.rotation = 45.0
        transform.scale = Vector2(2.0, 2.0)
        entity.add_component(transform)

        result = serializer.save_scene(scene, "transform_scene")
        assert result is True

    def test_save_scene_with_physics(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Physics components are serialized correctly."""
        entity = scene.entity_manager.create_entity()
        entity.add_component(RigidBody(mass=10.0, body_type=BodyType.DYNAMIC))
        entity.add_component(Collider(shape_type=ShapeType.CIRCLE, dimensions=[32.0]))

        result = serializer.save_scene(scene, "physics_scene")
        assert result is True

    def test_save_multiple_entities(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Multiple entities are saved correctly."""
        for i in range(5):
            entity = scene.entity_manager.create_entity(f"entity_{i}")
            entity.add_component(Tag(name=f"Entity {i}"))

        result = serializer.save_scene(scene, "multi_entity_scene")
        assert result is True


class TestLoadScene:
    """Test scene loading functionality."""

    def test_load_empty_scene(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Loading an empty scene succeeds."""
        serializer.save_scene(scene, "empty")
        scene.entity_manager._entities.clear()

        result = serializer.load_scene(scene, "empty")
        assert result is True

    def test_load_nonexistent_scene(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Loading a nonexistent scene returns False."""
        result = serializer.load_scene(scene, "does_not_exist")
        assert result is False

    def test_load_scene_with_tag(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Tag component is loaded correctly."""
        entity = scene.entity_manager.create_entity("player")
        entity.add_component(Tag(name="Hero"))
        serializer.save_scene(scene, "tag_scene")

        # Clear and reload
        scene.entity_manager._entities.clear()
        result = serializer.load_scene(scene, "tag_scene")

        assert result is True
        entities = list(scene.entity_manager.get_all_entities())
        assert len(entities) == 1
        tag = entities[0].get_component(Tag)
        assert tag.name == "Hero"


class TestRoundtrip:
    """Test save/load roundtrip functionality."""

    def test_roundtrip_tag_component(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Tag component survives roundtrip."""
        entity = scene.entity_manager.create_entity("test_entity")
        original_tag = Tag(name="TestTag")
        entity.add_component(original_tag)

        serializer.save_scene(scene, "roundtrip_tag")
        scene.entity_manager._entities.clear()
        scene.entity_manager._component_index.clear()
        serializer.load_scene(scene, "roundtrip_tag")

        entities = list(scene.entity_manager.get_all_entities())
        assert len(entities) == 1
        loaded_tag = entities[0].get_component(Tag)
        assert loaded_tag.name == original_tag.name

    def test_roundtrip_rigidbody_component(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """RigidBody component survives roundtrip."""
        entity = scene.entity_manager.create_entity()
        original = RigidBody(
            mass=5.0,
            body_type=BodyType.KINEMATIC,
            fixed_rotation=True,
            gravity_scale=0.5,
        )
        entity.add_component(original)

        serializer.save_scene(scene, "roundtrip_rb")
        scene.entity_manager._entities.clear()
        scene.entity_manager._component_index.clear()
        serializer.load_scene(scene, "roundtrip_rb")

        entities = list(scene.entity_manager.get_all_entities())
        loaded = entities[0].get_component(RigidBody)
        assert loaded.mass == original.mass
        assert loaded.fixed_rotation == original.fixed_rotation
        assert loaded.gravity_scale == original.gravity_scale

    def test_roundtrip_multiple_entities(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Multiple entities survive roundtrip."""
        entity_count = 3
        for i in range(entity_count):
            entity = scene.entity_manager.create_entity(f"ent_{i}")
            entity.add_component(Tag(name=f"Entity{i}"))

        serializer.save_scene(scene, "roundtrip_multi")
        scene.entity_manager._entities.clear()
        scene.entity_manager._component_index.clear()
        serializer.load_scene(scene, "roundtrip_multi")

        entities = list(scene.entity_manager.get_all_entities())
        assert len(entities) == entity_count

    def test_roundtrip_entity_with_multiple_components(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Entity with multiple components survives roundtrip."""
        entity = scene.entity_manager.create_entity("complex")
        entity.add_component(Tag(name="Complex"))
        entity.add_component(RigidBody(mass=2.0))
        entity.add_component(
            Collider(shape_type=ShapeType.BOX, dimensions=[64.0, 32.0])
        )

        serializer.save_scene(scene, "roundtrip_complex")
        scene.entity_manager._entities.clear()
        scene.entity_manager._component_index.clear()
        serializer.load_scene(scene, "roundtrip_complex")

        entities = list(scene.entity_manager.get_all_entities())
        assert len(entities) == 1
        loaded = entities[0]
        assert loaded.has_component(Tag)
        assert loaded.has_component(RigidBody)
        assert loaded.has_component(Collider)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_serialize_entity_preserves_id(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Entity ID is preserved across a save and load.

        Asserted through the public API rather than against
        `_serialize_entity`'s dict, so a change to the stored shape breaks
        this test only when it actually breaks id preservation.
        """
        entity = scene.entity_manager.create_entity("my_unique_id")
        entity.add_component(Tag(name="Test"))

        assert serializer.save_scene(scene, "ids")
        loaded = MockScene("loaded", EventDispatcher())
        assert serializer.load_scene(loaded, "ids")

        assert loaded.entity_manager.get_entity("my_unique_id") is not None

    def test_unknown_component_ignored_on_load(
        self,
        serializer: SceneSerializer,
        scene: MockScene,
        persistence_manager: PersistenceManager,
    ) -> None:
        """Unknown component types are gracefully ignored during load."""
        # Manually create save data with unknown component
        save_data = {
            "name": "test",
            "entities": [
                {
                    "id": "ent1",
                    "components": {
                        "Tag": {"name": "Known"},
                        "UnknownComponent": {"foo": "bar"},
                    },
                }
            ],
        }
        persistence_manager.save_data("unknown_comp", save_data)

        # Load should succeed, ignoring unknown component
        result = serializer.load_scene(scene, "unknown_comp")
        assert result is True

        entities = list(scene.entity_manager.get_all_entities())
        assert len(entities) == 1
        assert entities[0].has_component(Tag)

    def test_empty_entities_list(
        self,
        serializer: SceneSerializer,
        scene: MockScene,
        persistence_manager: PersistenceManager,
    ) -> None:
        """Scene with empty entities list loads correctly."""
        save_data = {"name": "empty", "entities": []}
        persistence_manager.save_data("truly_empty", save_data)

        result = serializer.load_scene(scene, "truly_empty")
        assert result is True

        entities = list(scene.entity_manager.get_all_entities())
        assert len(entities) == 0


class TestResourceLink:
    """Test ResourceLink component serialization."""

    def test_roundtrip_resource_link(
        self, serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """ResourceLink component survives roundtrip."""
        entity = scene.entity_manager.create_entity()
        entity.add_component(ResourceLink(resource_path="assets/sprite.png"))

        serializer.save_scene(scene, "resource_link")
        scene.entity_manager._entities.clear()
        scene.entity_manager._component_index.clear()
        serializer.load_scene(scene, "resource_link")

        entities = list(scene.entity_manager.get_all_entities())
        assert len(entities) == 1
        link = entities[0].get_component(ResourceLink)
        assert link.resource_path == "assets/sprite.png"


class FakeTexture(Texture):
    """A texture that needs no file, no backend and no GL context."""

    def __init__(self, path: str, width: int = 32, height: int = 32) -> None:
        super().__init__(path)
        self._width = width
        self._height = height

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def native_handle(self) -> Any:
        return None


@pytest.fixture
def core_registry():
    """A registry wired exactly as `create_application()` wires it.

    Deliberately *not* the hand-rolled `component_registry` fixture above,
    which lists five components by hand. That uniform setup is why the
    round-trip losses below went unnoticed for so long: every existing test
    built a registry that happened to exclude the components that were
    missing from the real one. Tests that assert on fidelity have to use
    the registry a game actually gets.
    """
    from pyguara.application.bootstrap import _register_core_components
    from pyguara.prefabs.registry import ComponentRegistry

    registry = ComponentRegistry()
    _register_core_components(registry)
    return registry


@pytest.fixture
def fidelity_serializer(
    persistence_manager: PersistenceManager, core_registry
) -> SceneSerializer:
    """A serializer over the real component set, resolving textures."""
    return SceneSerializer(
        persistence_manager,
        component_registry=core_registry,
        texture_resolver=lambda path: FakeTexture(path),
    )


class TestRoundtripFidelity:
    """State that used to be dropped silently by a save/load cycle.

    Each test here corresponds to something a scene file lost before: a
    designer saved a level and got back something that was not the level.
    """

    def test_entity_tags_survive(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """`entity.tags` round-trips.

        It has no component behind it -- it is a plain `set[str]` on the
        entity -- so component-by-component serialization never saw it.
        """
        entity = scene.entity_manager.create_entity("tagged")
        entity.add_component(Transform())
        entity.tags.update({"player", "spawn"})

        assert fidelity_serializer.save_scene(scene, "tags")
        loaded = MockScene("loaded", EventDispatcher())
        assert fidelity_serializer.load_scene(loaded, "tags")

        restored = loaded.entity_manager.get_entity("tagged")
        assert restored is not None
        assert restored.tags == {"player", "spawn"}

    def test_tags_are_sorted_in_the_file(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Tags are written in a stable order.

        `tags` is a set, so an unordered dump would make every save a
        spurious diff against the last one.
        """
        entity = scene.entity_manager.create_entity("e")
        entity.tags.update({"zeta", "alpha", "mu"})

        data = fidelity_serializer._serialize_entity(entity, scene.entity_manager)
        assert data["tags"] == ["alpha", "mu", "zeta"]

    def test_parent_child_links_survive(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """`ChildOf` ownership round-trips, in both index directions."""
        manager = scene.entity_manager
        manager.create_entity("parent").add_component(Transform())
        manager.create_entity("child").add_component(Transform())
        manager.set_parent("child", "parent")

        assert fidelity_serializer.save_scene(scene, "hierarchy")
        loaded = MockScene("loaded", EventDispatcher())
        assert fidelity_serializer.load_scene(loaded, "hierarchy")

        restored = loaded.entity_manager
        assert restored.parent_of("child") == "parent"
        assert restored.children_of("parent") == ["child"]

    def test_a_child_stored_before_its_parent_still_links(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Ownership is restored after every entity exists.

        `set_parent` raises `KeyError` for a parent it cannot find, and
        nothing orders a scene file's entities parents-first.
        """
        manager = scene.entity_manager
        # "a_child" sorts before "z_parent", so it is written first.
        manager.create_entity("z_parent").add_component(Transform())
        manager.create_entity("a_child").add_component(Transform())
        manager.set_parent("a_child", "z_parent")

        assert fidelity_serializer.save_scene(scene, "order")
        loaded = MockScene("loaded", EventDispatcher())
        assert fidelity_serializer.load_scene(loaded, "order")

        assert loaded.entity_manager.parent_of("a_child") == "z_parent"

    def test_a_dangling_parent_loads_the_child_unparented(
        self,
        fidelity_serializer: SceneSerializer,
        persistence_manager: PersistenceManager,
    ) -> None:
        """A parent id that is not in the file does not fail the load."""
        persistence_manager.save_data(
            "dangling",
            {
                "name": "s",
                "entities": [
                    {
                        "id": "orphan",
                        "tags": [],
                        "enabled": True,
                        "components": {"ChildOf": {"parent_id": "gone"}},
                    }
                ],
            },
        )

        loaded = MockScene("loaded", EventDispatcher())
        assert fidelity_serializer.load_scene(loaded, "dangling")
        assert loaded.entity_manager.get_entity("orphan") is not None
        assert loaded.entity_manager.parent_of("orphan") is None

    def test_disabled_state_survives(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """A disabled entity reloads disabled.

        The disabled set lives on the `EntityManager`, not the entity, so
        nothing entity-shaped carried it.
        """
        manager = scene.entity_manager
        manager.create_entity("on").add_component(Transform())
        manager.create_entity("off").add_component(Transform())
        manager.set_entity_enabled("off", False)

        assert fidelity_serializer.save_scene(scene, "enabled")
        loaded = MockScene("loaded", EventDispatcher())
        assert fidelity_serializer.load_scene(loaded, "enabled")

        assert loaded.entity_manager.is_entity_enabled("on") is True
        assert loaded.entity_manager.is_entity_enabled("off") is False

    def test_transform_interpolate_survives(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """`Transform.interpolate` round-trips.

        `PhysicsSystem` sets it on every body it creates; losing it made a
        reloaded physics entity judder above the fixed tick rate.
        """
        transform = Transform(position=Vector2(5, 5))
        transform.interpolate = True
        scene.entity_manager.create_entity("body").add_component(transform)

        assert fidelity_serializer.save_scene(scene, "interp")
        loaded = MockScene("loaded", EventDispatcher())
        assert fidelity_serializer.load_scene(loaded, "interp")

        restored = loaded.entity_manager.get_entity("body")
        assert restored is not None
        assert restored.get_component(Transform).interpolate is True


class TestSpriteAndResources:
    """Sprites hold a live `Texture`, so they need a path on disk."""

    def test_a_scene_with_a_sprite_saves_at_all(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """The regression that mattered most.

        A `Texture` is not JSON-serializable. `PersistenceManager` caught
        the `TypeError` and returned False, so `save_scene` reported
        failure for the *whole scene* -- not "saved without its sprites".
        Every level with a single sprite in it was unsaveable.
        """
        entity = scene.entity_manager.create_entity("visible")
        entity.add_component(Transform())
        entity.add_component(Sprite(texture=FakeTexture("hero.png")))

        assert fidelity_serializer.save_scene(scene, "sprite") is True

    def test_sprite_texture_is_stored_as_a_path(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """A resource is encoded by path, not by its backend handle."""
        sprite = Sprite(texture=FakeTexture("art/hero.png"))
        encoded = fidelity_serializer._serialize_component(sprite)

        assert encoded["texture"] == {RESOURCE_KEY: "art/hero.png"}

    def test_sprite_round_trips_through_the_resolver(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """A sprite reloads with a live texture and its own fields."""
        entity = scene.entity_manager.create_entity("visible")
        entity.add_component(Transform())
        entity.add_component(
            Sprite(texture=FakeTexture("hero.png"), layer=10, flip_x=True, y_sort=True)
        )

        assert fidelity_serializer.save_scene(scene, "sprite")
        loaded = MockScene("loaded", EventDispatcher())
        assert fidelity_serializer.load_scene(loaded, "sprite")

        restored = loaded.entity_manager.get_entity("visible")
        assert restored is not None
        sprite = restored.get_component(Sprite)
        assert sprite.texture.path == "hero.png"
        assert sprite.layer == 10
        assert sprite.flip_x is True
        assert sprite.y_sort is True

    def test_an_unresolvable_texture_skips_the_component(
        self, persistence_manager: PersistenceManager, core_registry, scene: MockScene
    ) -> None:
        """A sprite is dropped, not attached with a None texture.

        Attaching it would pass here and crash later in the renderer, on a
        frame far from the load that caused it.
        """
        serializer = SceneSerializer(
            persistence_manager,
            component_registry=core_registry,
            texture_resolver=lambda path: None,
        )
        entity = scene.entity_manager.create_entity("visible")
        entity.add_component(Transform())
        entity.add_component(Sprite(texture=FakeTexture("missing.png")))

        assert serializer.save_scene(scene, "broken")
        loaded = MockScene("loaded", EventDispatcher())
        assert serializer.load_scene(loaded, "broken")

        restored = loaded.entity_manager.get_entity("visible")
        assert restored is not None
        assert restored.has_component(Transform)
        assert not restored.has_component(Sprite)

    def test_no_resolver_still_saves_the_path(
        self, persistence_manager: PersistenceManager, core_registry, scene: MockScene
    ) -> None:
        """Saving records the path even with no resolver configured.

        So a scene saved by a resolver-less serializer loses nothing
        permanently -- a later load with a resolver recovers the sprite.
        """
        writer = SceneSerializer(persistence_manager, component_registry=core_registry)
        entity = scene.entity_manager.create_entity("visible")
        entity.add_component(Sprite(texture=FakeTexture("hero.png")))
        assert writer.save_scene(scene, "pathonly")

        reader = SceneSerializer(
            persistence_manager,
            component_registry=core_registry,
            texture_resolver=lambda path: FakeTexture(path),
        )
        loaded = MockScene("loaded", EventDispatcher())
        assert reader.load_scene(loaded, "pathonly")
        restored = loaded.entity_manager.get_entity("visible")
        assert restored is not None
        assert restored.get_component(Sprite).texture.path == "hero.png"


class TestLoadIsNotAMerge:
    """`load_scene` replaces the world rather than adding to it."""

    def test_loading_clears_entities_that_are_not_in_the_file(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """An entity absent from the save is gone after loading it.

        `EntityManager.add_entity` overwrites an existing id without
        complaint, so loading into a populated world used to replace the
        ids that collided and silently keep the ones that did not.
        """
        scene.entity_manager.create_entity("from_file").add_component(Transform())
        assert fidelity_serializer.save_scene(scene, "replace")

        target = MockScene("target", EventDispatcher())
        target.entity_manager.create_entity("stale").add_component(Transform())

        assert fidelity_serializer.load_scene(target, "replace")

        ids = sorted(e.id for e in target.entity_manager.get_all_entities())
        assert ids == ["from_file"]

    def test_loading_twice_is_idempotent(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """The same file loaded twice yields the same world."""
        manager = scene.entity_manager
        manager.create_entity("a").add_component(Transform())
        manager.create_entity("b").add_component(Transform())
        manager.set_parent("b", "a")
        assert fidelity_serializer.save_scene(scene, "twice")

        target = MockScene("target", EventDispatcher())
        assert fidelity_serializer.load_scene(target, "twice")
        assert fidelity_serializer.load_scene(target, "twice")

        ids = sorted(e.id for e in target.entity_manager.get_all_entities())
        assert ids == ["a", "b"]
        assert target.entity_manager.children_of("a") == ["b"]


class TestFullSceneFidelity:
    """One scene exercising everything above at once."""

    def test_a_populated_scene_round_trips_whole(
        self, fidelity_serializer: SceneSerializer, scene: MockScene
    ) -> None:
        """Sprites, a parent chain, tags and a disabled entity together."""
        manager = scene.entity_manager

        root = manager.create_entity("root")
        root.add_component(Transform(position=Vector2(10, 20)))
        root.add_component(Sprite(texture=FakeTexture("root.png"), layer=5))
        root.tags.add("level")

        child = manager.create_entity("child")
        child_transform = Transform(position=Vector2(1, 2))
        child_transform.interpolate = True
        child.add_component(child_transform)
        child.add_component(Tag("mob"))
        child.tags.update({"enemy", "spawned"})
        manager.set_parent("child", "root")

        hidden = manager.create_entity("hidden")
        hidden.add_component(Transform())
        manager.set_entity_enabled("hidden", False)

        assert fidelity_serializer.save_scene(scene, "whole")
        loaded = MockScene("loaded", EventDispatcher())
        assert fidelity_serializer.load_scene(loaded, "whole")
        target = loaded.entity_manager

        assert sorted(e.id for e in target.get_all_entities()) == [
            "child",
            "hidden",
            "root",
        ]

        new_root = target.get_entity("root")
        assert new_root is not None
        assert new_root.tags == {"level"}
        assert new_root.get_component(Transform).position == Vector2(10, 20)
        assert new_root.get_component(Sprite).texture.path == "root.png"
        assert new_root.get_component(Sprite).layer == 5

        new_child = target.get_entity("child")
        assert new_child is not None
        assert new_child.tags == {"enemy", "spawned"}
        assert new_child.get_component(Tag).name == "mob"
        assert new_child.get_component(Transform).interpolate is True
        assert target.parent_of("child") == "root"

        assert target.is_entity_enabled("hidden") is False
