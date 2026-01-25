"""Tests for scene serialization."""

import pytest
from typing import Any, Dict, Optional, Tuple

from pyguara.scene.serializer import SceneSerializer
from pyguara.scene.base import Scene
from pyguara.events.dispatcher import EventDispatcher
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.types import StorageBackend
from pyguara.common.components import Tag, Transform, ResourceLink
from pyguara.common.types import Vector2
from pyguara.physics.components import RigidBody, Collider
from pyguara.physics.types import BodyType, ShapeType


class MockStorageBackend(StorageBackend):
    """In-memory storage backend for testing."""

    def __init__(self) -> None:
        self._storage: Dict[str, Tuple[bytes, Dict[str, Any]]] = {}

    def save(self, key: str, data: bytes, metadata: Dict[str, Any]) -> None:
        self._storage[key] = (data, metadata)

    def load(self, key: str) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        return self._storage.get(key)

    def delete(self, key: str) -> bool:
        if key in self._storage:
            del self._storage[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        return key in self._storage


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
        """Entity ID is preserved during serialization."""
        entity = scene.entity_manager.create_entity("my_unique_id")
        entity.add_component(Tag(name="Test"))

        data = serializer._serialize_entity(entity)
        assert data["id"] == "my_unique_id"

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
