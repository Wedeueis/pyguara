"""Scene serialization logic."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Optional

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.persistence.manager import PersistenceManager
from pyguara.physics.types import BodyType, ShapeType
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.scene.base import Scene


class SceneSerializer:
    """Handles saving and loading full scenes."""

    def __init__(
        self,
        persistence: PersistenceManager,
        component_registry: Optional[ComponentRegistry] = None,
    ) -> None:
        """Initialize the serializer.

        Args:
            persistence: PersistenceManager for storage operations.
            component_registry: Optional ComponentRegistry for component
                instantiation. If not provided, uses global registry.
        """
        self.persistence = persistence

        # Use provided registry or get global
        if component_registry is not None:
            self._registry = component_registry
        else:
            from pyguara.prefabs.registry import get_component_registry

            self._registry = get_component_registry()

    def save_scene(self, scene: Scene, filename: str) -> bool:
        """
        Serialize the current state of a scene to storage.

        Args:
            scene: The scene instance to save.
            filename: The identifier for the save file.
        """
        entities_data: list[Dict[str, Any]] = []
        for entity in scene.entity_manager.get_all_entities():
            entities_data.append(self._serialize_entity(entity))

        scene_data: Dict[str, Any] = {"name": scene.name, "entities": entities_data}

        return self.persistence.save_data(filename, scene_data)

    def load_scene(self, scene: Scene, filename: str) -> bool:
        """
        Populate a scene with entities from a save file.

        Args:
            scene: The scene to populate.
            filename: The identifier of the save data.
        """
        data = self.persistence.load_data(filename)
        if not data:
            return False

        # Reconstruct Entities
        for ent_data in data.get("entities", []):
            eid = ent_data.get("id")
            entity = scene.entity_manager.create_entity(eid)

            for comp_name, comp_raw_data in ent_data.get("components", {}).items():
                if self._registry.has(comp_name):
                    try:
                        instance = self._registry.create(comp_name, comp_raw_data)
                        entity.add_component(instance)
                    except Exception:
                        # Fallback to legacy deserialization for complex types
                        cls = self._registry.get(comp_name)
                        if cls:
                            instance = self._deserialize_component(cls, comp_raw_data)
                            if instance:
                                entity.add_component(instance)

        return True

    def _deserialize_component(self, cls: type, data: Dict[str, Any]) -> Any:
        """Deserialize a component from a dictionary."""
        if cls == Transform:
            t = Transform()
            if "position" in data:
                pos = data["position"]
                t.position = Vector2(pos.get("x", 0), pos.get("y", 0))
            if "rotation" in data:
                t.rotation = data["rotation"]
            if "scale" in data:
                scale = data["scale"]
                t.scale = Vector2(scale.get("x", 1), scale.get("y", 1))
            return t

        if dataclasses.is_dataclass(cls):
            # Filter and convert values for dataclass fields
            filtered = {}
            for field in dataclasses.fields(cls):
                if field.name in data and not field.name.startswith("_"):
                    value = self._deserialize_value(data[field.name], field.type)
                    filtered[field.name] = value
            return cls(**filtered)

        return None

    def _deserialize_value(self, value: Any, type_hint: Any = None) -> Any:
        """Deserialize a value from JSON form back to Python types."""
        # Handle Vector2 dict
        if isinstance(value, dict) and "x" in value and "y" in value:
            return Vector2(value["x"], value["y"])

        # Handle BodyType enum
        if type_hint == BodyType or (
            isinstance(value, (str, int)) and str(type_hint) == "BodyType"
        ):
            if isinstance(value, str):
                return BodyType[value.upper()]
            return BodyType(value)

        # Handle ShapeType enum
        if type_hint == ShapeType or (
            isinstance(value, (str, int)) and str(type_hint) == "ShapeType"
        ):
            if isinstance(value, str):
                return ShapeType[value.upper()]
            return ShapeType(value)

        # Handle lists
        if isinstance(value, list):
            return value

        return value

    def _serialize_entity(self, entity: Entity) -> Dict[str, Any]:
        """Convert an entity to a dictionary."""
        components_data = {}
        for comp_type, component in entity._components.items():
            components_data[comp_type.__name__] = self._serialize_component(component)

        return {"id": entity.id, "components": components_data}

    def _serialize_component(self, component: Any) -> Dict[str, Any]:
        """Convert a component to a JSON-serializable dictionary."""
        if isinstance(component, Transform):
            return {
                "position": {"x": component.position.x, "y": component.position.y},
                "rotation": component.rotation,
                "scale": {"x": component.scale.x, "y": component.scale.y},
            }

        if dataclasses.is_dataclass(component) and not isinstance(component, type):
            result: Dict[str, Any] = {}
            for field in dataclasses.fields(component):
                value = getattr(component, field.name)
                # Skip private/internal fields
                if field.name.startswith("_"):
                    continue
                result[field.name] = self._serialize_value(value)
            return result

        # Fallback: try to convert to dict
        if hasattr(component, "__dict__"):
            return {
                k: self._serialize_value(v)
                for k, v in component.__dict__.items()
                if not k.startswith("_")
            }

        return {}

    def _serialize_value(self, value: Any) -> Any:
        """Convert a value to a JSON-serializable form."""
        if isinstance(value, Vector2):
            return {"x": value.x, "y": value.y}
        if isinstance(value, (BodyType, ShapeType)):
            return value.value
        if isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return self._serialize_component(value)
        return value
