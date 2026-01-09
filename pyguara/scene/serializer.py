"""Scene serialization logic."""

from typing import Dict, Any
from pyguara.scene.base import Scene
from pyguara.persistence.manager import PersistenceManager
from pyguara.common.components import Tag, Transform, ResourceLink
from pyguara.physics.components import RigidBody, Collider
from pyguara.ecs.entity import Entity


class SceneSerializer:
    """Handles saving and loading full scenes."""

    def __init__(self, persistence: PersistenceManager) -> None:
        """Initialize the serializer."""
        self.persistence = persistence
        # Component Registry for loading
        self._comp_map = {
            "Tag": Tag,
            "Transform": Transform,
            "RigidBody": RigidBody,
            "Collider": Collider,
            "ResourceLink": ResourceLink,
        }

    def save_scene(self, scene: Scene, filename: str) -> bool:
        """
        Serialize the current state of a scene to storage.

        Args:
            scene: The scene instance to save.
            filename: The identifier for the save file.
        """
        scene_data = {"name": scene.name, "entities": []}

        # Iterate all entities
        for entity in scene.entity_manager.get_all_entities():
            entity_data = self._serialize_entity(entity)
            scene_data["entities"].append(entity_data)  # type: ignore

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

        # 2. Reconstruct Entities
        for ent_data in data.get("entities", []):
            eid = ent_data.get("id")
            entity = scene.entity_manager.create_entity(eid)

            for comp_name, comp_raw_data in ent_data.get("components", {}).items():
                if comp_name in self._comp_map:
                    cls = self._comp_map[comp_name]

                    if hasattr(cls, "__dataclass_fields__"):
                        # Filter keys to match dataclass
                        filtered = {
                            k: v
                            for k, v in comp_raw_data.items()
                            if k in cls.__dataclass_fields__
                        }
                        instance = cls(**filtered)
                        entity.add_component(instance)
                    else:
                        # Handle Transform or other non-dataclasses
                        if cls == Transform:
                            t = Transform()
                            if "position" in comp_raw_data:
                                t.position = comp_raw_data["position"]
                            if "rotation" in comp_raw_data:
                                t.rotation = comp_raw_data["rotation"]
                            if "scale" in comp_raw_data:
                                t.scale = comp_raw_data["scale"]
                            entity.add_component(t)

        return True

    def _serialize_entity(self, entity: Entity) -> Dict[str, Any]:
        """Convert an entity to a dictionary."""
        components_data = {}
        for comp_type, component in entity.components.items():
            components_data[comp_type.__name__] = component

        return {"id": entity.id, "components": components_data}
