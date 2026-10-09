"""Scene serialization logic.

What a scene file is meant to be: everything needed to rebuild the world a
designer authored, in a shape a human could have typed. That makes
round-trip fidelity the whole contract, and four things used to fall
through it -- each silently, which is the part that mattered:

- **Entity tags.** `entity.tags` is a plain `set[str]` with no component
  behind it, so component-by-component serialisation never saw it.
- **Ownership.** `ChildOf` was not in the component registry, so
  `load_scene` skipped it and every parent/child link -- and the cascade
  destroy that rides on it -- was lost.
- **Enabled state.** `EntityManager` holds disabled ids in a side set, not
  on the entity, so a disabled entity reloaded as enabled.
- **Resources.** A `Sprite` holds a live `Texture`, not a path. Encoding it
  produced a `Texture` object that `json` refused, `PersistenceManager`
  caught the `TypeError`, and `save_scene` returned `False` -- so a scene
  containing any sprite at all did not save. Not "saved without its
  sprites": did not save.

Resources are written as `{"__resource__": path}` and resolved on load by
the `texture_resolver` the bootstrap injects. A path that will not resolve
skips the component with a warning rather than attaching a `Sprite` whose
`texture` is `None`, which would pass here and crash in the renderer
instead.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.log import get_logger
from pyguara.persistence.manager import PersistenceManager
from pyguara.physics.types import BodyType, ShapeType
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.resources.types import Resource, Texture
from pyguara.scene.base import Scene

logger = get_logger(__name__)

RESOURCE_KEY = "__resource__"
"""Marks an encoded resource reference, holding the resource's path.

A dunder-ish key rather than a plain `"path"`: component fields are written
under their own names, and a component with a genuine `path: str` field
would otherwise be indistinguishable from a resource handle.
"""

TextureResolver = Callable[[str], Texture | None]
"""Turns a stored resource path back into a live texture, or None."""


class SceneSerializer:
    """Handles saving and loading full scenes."""

    def __init__(
        self,
        persistence: PersistenceManager,
        component_registry: ComponentRegistry | None = None,
        texture_resolver: TextureResolver | None = None,
    ) -> None:
        """Initialize the serializer.

        Args:
            persistence: PersistenceManager for storage operations.
            component_registry: Optional ComponentRegistry for component
                instantiation. If not provided, uses global registry.
            texture_resolver: Turns a stored texture path back into a
                `Texture`. The bootstrap wires this to the
                `ResourceManager`. Without it, a component holding a
                texture is skipped on load and says so -- saving still
                records the path either way, so a scene saved by a
                resolver-less serializer loses nothing permanently.
        """
        self.persistence = persistence

        # Use provided registry or get global
        if component_registry is not None:
            self._registry = component_registry
        else:
            from pyguara.prefabs.registry import get_component_registry

            self._registry = get_component_registry()

        self._texture_resolver = texture_resolver

    def save_scene(self, scene: Scene, filename: str) -> bool:
        """Serialize the current state of a scene to storage.

        Args:
            scene: The scene instance to save.
            filename: The identifier for the save file.

        Returns:
            True when the data reached storage.
        """
        manager = scene.entity_manager
        entities_data: list[dict[str, Any]] = []
        for entity in manager.get_all_entities():
            entities_data.append(self._serialize_entity(entity, manager))

        scene_data: dict[str, Any] = {"name": scene.name, "entities": entities_data}

        return self.persistence.save_data(filename, scene_data)

    def load_scene(self, scene: Scene, filename: str) -> bool:
        """Populate a scene with entities from a save file.

        The scene's world is cleared first. `load_scene` is a load, not a
        merge: `EntityManager.add_entity` overwrites an existing id without
        complaint, so loading into a populated world used to replace some
        entities, keep others, and leave the result dependent on which ids
        happened to collide.

        Args:
            scene: The scene to populate.
            filename: The identifier of the save data.

        Returns:
            True when the file was found and applied.
        """
        data = self.persistence.load_data(filename)
        if not data:
            return False

        manager = scene.entity_manager
        manager.clear()

        # Two passes. Ownership is restored only once every entity exists:
        # `set_parent` raises KeyError for a parent it cannot find, and a
        # child may appear before its parent in the file.
        parents: dict[str, str] = {}
        disabled: list[str] = []

        for ent_data in data.get("entities", []):
            eid = ent_data.get("id")
            entity = manager.create_entity(eid)
            entity.tags.update(ent_data.get("tags", []))
            if not ent_data.get("enabled", True):
                disabled.append(entity.id)

            for comp_name, comp_raw_data in ent_data.get("components", {}).items():
                # Ownership is a relation, not a component to attach by
                # hand: `set_parent` is what maintains the parent -> children
                # index, and `add_component(ChildOf(...))` below would bypass
                # the ordering guard above.
                if comp_name == "ChildOf":
                    parent_id = comp_raw_data.get("parent_id", "")
                    if parent_id:
                        parents[entity.id] = parent_id
                    continue
                self._load_component(entity, comp_name, comp_raw_data)

        for child_id, parent_id in parents.items():
            try:
                manager.set_parent(child_id, parent_id)
            except (KeyError, ValueError) as exc:
                logger.warning(
                    f"Could not restore parent of '{child_id}': {exc}. "
                    f"The entity is loaded, unparented."
                )

        for entity_id in disabled:
            manager.set_entity_enabled(entity_id, False)

        return True

    def _load_component(
        self, entity: Entity, comp_name: str, comp_raw_data: dict[str, Any]
    ) -> None:
        """Attach one deserialized component to `entity`.

        A component the registry does not know is skipped with a warning.
        It used to be skipped in silence, which made a missing
        `registry.register()` call look like a save-side bug.

        Args:
            entity: The entity to attach to.
            comp_name: The component's registered name.
            comp_raw_data: Its stored fields.
        """
        if not self._registry.has(comp_name):
            logger.warning(
                f"Entity '{entity.id}': component '{comp_name}' is not "
                f"registered, skipping. Register it with "
                f"`container.get(ComponentRegistry).register({comp_name})`."
            )
            return

        resolved = self._resolve_resources(comp_name, comp_raw_data)
        if resolved is None:
            return

        try:
            instance = self._registry.create(comp_name, resolved)
            entity.add_component(instance)
            return
        except Exception:
            # Fallback to legacy deserialization for complex types
            pass

        cls = self._registry.get(comp_name)
        if cls is None:  # pragma: no cover - has() was just checked
            return
        instance = self._deserialize_component(cls, resolved)
        if instance:
            entity.add_component(instance)

    def _resolve_resources(
        self, comp_name: str, comp_raw_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Replace encoded resource references with live resources.

        Args:
            comp_name: The component's name, for the warning message.
            comp_raw_data: Its stored fields.

        Returns:
            The fields with resources resolved, or None when a reference
            could not be resolved and the component must be skipped.
        """
        resolved: dict[str, Any] = {}
        for key, value in comp_raw_data.items():
            if not (isinstance(value, dict) and RESOURCE_KEY in value):
                resolved[key] = value
                continue

            path = value[RESOURCE_KEY]
            texture = (
                None if self._texture_resolver is None else self._texture_resolver(path)
            )
            if texture is None:
                logger.warning(
                    f"Component '{comp_name}' references the resource "
                    f"'{path}', which could not be resolved, so the "
                    f"component is skipped. Attaching it without the "
                    f"resource would fail later, in the renderer."
                )
                return None
            resolved[key] = texture

        return resolved

    def _deserialize_component(self, cls: type, data: dict[str, Any]) -> Any:
        """Deserialize a component from a dictionary.

        Args:
            cls: The component class to build.
            data: Its stored fields.

        Returns:
            The component, or None when `cls` cannot be built this way.
        """
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
            # Whether the renderer interpolates this transform between fixed
            # ticks. Omitted from the three keys above for a long time, so a
            # saved physics entity reloaded un-interpolated and visibly
            # juddered at anything below the fixed rate.
            t.interpolate = bool(data.get("interpolate", False))
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
        """Deserialize a value from JSON form back to Python types.

        Args:
            value: The stored value.
            type_hint: The target field's declared type, when known.

        Returns:
            The Python value.
        """
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

    def _serialize_entity(
        self, entity: Entity, manager: EntityManager
    ) -> dict[str, Any]:
        """Convert an entity to a dictionary.

        Args:
            entity: The entity to serialize.
            manager: Its world, for the state held outside the entity --
                the disabled set lives on the manager, not the entity.

        Returns:
            The entity's stored form.
        """
        components_data = {}
        for component in entity.get_all_components():
            name = type(component).__name__
            components_data[name] = self._serialize_component(component)

        return {
            "id": entity.id,
            # Sorted so a scene file is stable across runs: `tags` is a set,
            # and an unordered dump makes every save a spurious diff.
            "tags": sorted(entity.tags),
            "enabled": manager.is_entity_enabled(entity.id),
            "components": components_data,
        }

    def _serialize_component(self, component: Any) -> dict[str, Any]:
        """Convert a component to a JSON-serializable dictionary.

        Args:
            component: The component to serialize.

        Returns:
            Its stored form.
        """
        if isinstance(component, Transform):
            return {
                "position": {"x": component.position.x, "y": component.position.y},
                "rotation": component.rotation,
                "scale": {"x": component.scale.x, "y": component.scale.y},
                "interpolate": component.interpolate,
            }

        if dataclasses.is_dataclass(component) and not isinstance(component, type):
            result: dict[str, Any] = {}
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
        """Convert a value to a JSON-serializable form.

        Args:
            value: The value to encode.

        Returns:
            Its JSON-serializable form.
        """
        if isinstance(value, Vector2):
            return {"x": value.x, "y": value.y}
        if isinstance(value, (BodyType, ShapeType)):
            return value.value
        # Before the dataclass arm: a `Resource` subclass may well be one,
        # and encoding a texture field by field would store a backend
        # surface rather than the path needed to load it again.
        if isinstance(value, Resource):
            return {RESOURCE_KEY: value.path}
        if isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return self._serialize_component(value)
        return value
