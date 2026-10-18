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
from enum import Enum
from functools import cache
from typing import Any, get_type_hints

from pyguara.common.components import Transform, set_parent
from pyguara.common.modifiers import ModifiableValue
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


@cache
def _resolved_hints(cls: type) -> dict[str, Any]:
    """Return `cls`'s annotations as types rather than strings.

    Cached, because resolving them walks the defining module's namespace
    and a scene load calls this once per component instance -- 252
    entities in the smallest demo.

    Args:
        cls: The component class.

    Returns:
        Field name to resolved type. Empty when the annotations cannot be
        resolved, which leaves each field's raw `field.type` in play and
        the behaviour exactly as it was.
    """
    try:
        return dict(get_type_hints(cls))
    except Exception as exc:  # pragma: no cover - a forward ref we cannot see
        logger.debug(f"Could not resolve {cls.__name__}'s annotations: {exc}")
        return {}


def _to_enum(enum_type: type[Enum], value: Any) -> Any:
    """Turn a stored value back into a member of `enum_type`.

    Accepts the stored value, a member name, or a member already. A stored
    enum is its `value`, but a hand-written scene file is likely to carry
    the name -- and the point of this format is that a person could have
    written it.

    Args:
        enum_type: The enum to produce.
        value: What the file held.

    Returns:
        The member, or `value` unchanged when it matches nothing. Leaving
        it alone lets the component's own construction raise with a
        message naming the valid members, which is better than one from
        here.
    """
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError:
        pass
    if isinstance(value, str):
        try:
            return enum_type[value.upper()]
        except KeyError:
            pass
    return value


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

        # Two passes. Both kinds of parent are restored only once every
        # entity exists: `set_parent` raises KeyError for a parent it cannot
        # find, and a child may appear before its parent in the file.
        #
        # The two kinds are separate on purpose, and both have to be here.
        # `ChildOf` is *ownership* and cascades on destroy; `Transform`
        # parenting is *spatial* and is what makes a child's stored position
        # local. Only the first survived a save: a turret stored at local
        # (10, 0) under a hull at (100, 200) reloaded as a root at world
        # (10, 0), having moved 190 pixels, because its position was read
        # back as a world coordinate.
        parents: dict[str, str] = {}
        transform_parents: dict[str, str] = {}
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
                if comp_name == "Transform":
                    spatial_parent = comp_raw_data.get("parent", "")
                    if spatial_parent:
                        transform_parents[entity.id] = spatial_parent
                self._load_component(entity, comp_name, comp_raw_data)

        for child_id, parent_id in parents.items():
            try:
                manager.set_parent(child_id, parent_id)
            except (KeyError, ValueError) as exc:
                logger.warning(
                    f"Could not restore parent of '{child_id}': {exc}. "
                    f"The entity is loaded, unparented."
                )

        self._restore_transform_parents(manager, transform_parents)

        for entity_id in disabled:
            manager.set_entity_enabled(entity_id, False)

        return True

    def _restore_transform_parents(
        self, manager: EntityManager, links: dict[str, str]
    ) -> None:
        """Re-link spatial `Transform` hierarchies after every entity exists.

        **`keep_world_transform` is False, and that is the whole point.**
        The stored `position` of a parented transform is already *local* to
        its parent -- that is what being parented means. Re-linking with
        `keep_world_transform=True`, the default, would read that local
        value as a world coordinate and rewrite the local one to compensate,
        so a turret stored at (10, 0) under a hull at (100, 200) would come
        back at local (-90, -200) and the hierarchy would be correct about a
        position that was never saved. `PrefabFactory._create_children`
        parents with the same flag for the same reason.

        Order within the pass does not matter: with no world transform to
        preserve, linking is just a pointer and a child list append, so a
        chain three deep re-links correctly whichever end is seen first.

        Args:
            manager: The entity manager holding every loaded entity.
            links: Child entity id -> parent entity id.
        """
        for child_id, parent_id in links.items():
            child = manager.get_entity(child_id)
            parent = manager.get_entity(parent_id)
            if child is None or parent is None:
                logger.warning(
                    f"Could not restore the spatial parent of '{child_id}': "
                    f"no entity '{parent_id}' in the file. The entity is "
                    f"loaded, unparented -- so its stored position, which is "
                    f"local to that parent, is now being read as a world one."
                )
                continue
            # `has_component` rather than a None check: `get_component`
            # raises KeyError for a type that is not attached, so testing
            # its result would have let a hand-written file -- or a
            # component the registry declined to build -- abort the whole
            # load instead of dropping one link.
            if not (child.has_component(Transform) and parent.has_component(Transform)):
                missing = parent_id if not parent.has_component(Transform) else child_id
                logger.warning(
                    f"Could not restore the spatial parent of '{child_id}': "
                    f"'{missing}' has no Transform. The entity is loaded, "
                    f"unparented."
                )
                continue
            child_transform = child.get_component(Transform)
            parent_transform = parent.get_component(Transform)
            try:
                set_parent(child_transform, parent_transform, False)
            except ValueError as exc:
                # A cycle. `set_parent` refuses it rather than building a
                # hierarchy whose `world_*` reads recurse until the stack
                # runs out, which is what a hand-edited file could ask for.
                logger.warning(
                    f"Could not restore the spatial parent of '{child_id}': "
                    f"{exc} The entity is loaded, unparented."
                )

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
            # Resolved rather than read off the field. Component modules
            # use `from __future__ import annotations`, so `field.type` is
            # the *string* "LightType", not the class -- which is why the
            # original code compared names and could only ever know the
            # two it had been told about.
            hints = _resolved_hints(cls)
            filtered = {}
            for field in dataclasses.fields(cls):
                if field.name in data and not field.name.startswith("_"):
                    value = self._deserialize_value(
                        data[field.name], hints.get(field.name, field.type)
                    )
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

        if (
            isinstance(type_hint, type)
            and issubclass(type_hint, ModifiableValue)
            and isinstance(value, (int, float))
        ):
            return ModifiableValue(float(value))

        # Any enum the field is declared as, by the same reasoning as the
        # encode: the two the engine shipped first are not the only two.
        if isinstance(type_hint, type) and issubclass(type_hint, Enum):
            return _to_enum(type_hint, value)

        # Named rather than declared. A type hint arrives as a string
        # under `from __future__ import annotations`, and the two enums
        # the engine resolves by name are kept resolvable so a scene
        # written before this still loads.
        for enum_type in (BodyType, ShapeType):
            if str(type_hint) == enum_type.__name__ and isinstance(value, (str, int)):
                return _to_enum(enum_type, value)

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
            data: dict[str, Any] = {
                "position": {"x": component.position.x, "y": component.position.y},
                "rotation": component.rotation,
                "scale": {"x": component.scale.x, "y": component.scale.y},
                "interpolate": component.interpolate,
            }
            parent_id = self._transform_parent_id(component)
            # Omitted when there is no parent, so a scene with no spatial
            # hierarchy writes exactly the file it wrote before.
            if parent_id is not None:
                data["parent"] = parent_id
            return data

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

    def _transform_parent_id(self, component: Transform) -> str | None:
        """Name `component`'s spatial parent by its owning entity's id.

        A `Transform` points at its parent `Transform`, not at an entity, so
        the link has to be turned into something a file can hold. Every
        attached component knows its owner, which is what makes that
        possible without a reverse index.

        Args:
            component: The child transform.

        Returns:
            The parent's entity id, or None when there is no parent -- or
            when the parent is a `Transform` that belongs to no entity,
            which is a link nothing can name.
        """
        parent = component.parent
        if parent is None:
            return None
        owner = parent.entity
        if owner is None:
            logger.warning(
                "A Transform is parented to one that belongs to no entity, so "
                "the link cannot be written to the file and is dropped. A "
                "bare Transform used as a pivot has no id to refer to; "
                "attach it to an entity to make the hierarchy saveable."
            )
            return None
        return owner.id

    def _serialize_value(self, value: Any) -> Any:
        """Convert a value to a JSON-serializable form.

        Args:
            value: The value to encode.

        Returns:
            Its JSON-serializable form.
        """
        if isinstance(value, Vector2):
            return {"x": value.x, "y": value.y}
        # Every enum, not a list of the two the engine happened to ship
        # first. A `LightType` -- or any enum a game declares -- took the
        # dataclass arm below, came out as `{}`, and then failed the JSON
        # encode outright: saving `guara_falcao` raised "Object of type
        # LightType is not JSON serializable".
        if isinstance(value, Enum):
            return value.value
        # Its base, which is the authored number. The modifiers stacked on
        # top are runtime state -- a buff, a ring being worn -- put there
        # by whatever applied them and re-applied the same way; writing
        # them into a scene file would make a snapshot of one playthrough
        # part of the level.
        if isinstance(value, ModifiableValue):
            return value.base
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
