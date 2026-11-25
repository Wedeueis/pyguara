"""Component registry for the prefab system.

Provides a centralized registry for mapping component names to their types,
enabling dynamic component instantiation from serialized data.
"""

from __future__ import annotations

import dataclasses
import enum
import sys
import types
from collections.abc import Callable
from typing import Any, NamedTuple, Union, get_args, get_origin, get_type_hints

from pyguara.common.modifiers import ModifiableValue
from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import Component
from pyguara.log import get_logger

logger = get_logger(__name__)


class ComponentRegistry:
    """Registry for component types enabling dynamic instantiation.

    The registry maps component class names to their types, allowing
    components to be created from serialized data (JSON/YAML).

    Example:
        registry = ComponentRegistry()
        registry.register(Transform)
        registry.register(RigidBody)

        # Create component from data
        transform = registry.create("Transform", {"position": {"x": 100, "y": 200}})
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._components: dict[str, type[Component]] = {}
        self._deserializers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._field_cache: dict[type, _Fields] = {}
        self._type_converters: dict[type, Callable[[Any], Any]] = self._builtins()
        # Register built-in deserializers for special components
        self._register_builtin_deserializers()

    def register(
        self,
        component_type: type[Component],
        name: str | None = None,
    ) -> None:
        """Register a component type.

        Args:
            component_type: The component class to register.
            name: Optional custom name. Defaults to class name.
        """
        type_name = name or component_type.__name__

        if type_name in self._components:
            logger.warning(f"Overwriting component registration: {type_name}")

        self._components[type_name] = component_type
        logger.debug(f"Registered component: {type_name}")

    def register_deserializer(
        self,
        name: str,
        deserializer: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Register a custom deserializer for a component type.

        Use this for components that need special deserialization logic.

        Args:
            name: Component name this deserializer handles.
            deserializer: Function that takes dict and returns component.
        """
        self._deserializers[name] = deserializer

    def register_type_converter(
        self,
        target_type: type,
        converter: Callable[[Any], Any],
    ) -> None:
        """Register a converter for a specific type.

        Used for nested types like Vector2 that need special handling.

        Args:
            target_type: The type this converter produces.
            converter: Function that converts raw data to the type.
        """
        self._type_converters[target_type] = converter

    def get(self, name: str) -> type[Component] | None:
        """Get a registered component type by name.

        Args:
            name: Component class name.

        Returns:
            The component type, or None if not registered.
        """
        return self._components.get(name)

    def has(self, name: str) -> bool:
        """Check if a component is registered.

        Args:
            name: Component class name.

        Returns:
            True if registered.
        """
        return name in self._components

    def create(self, name: str, data: dict[str, Any]) -> Component:
        """Create a component instance from serialized data.

        Args:
            name: Component class name.
            data: Dictionary of component field values.

        Returns:
            Instantiated component.

        Raises:
            KeyError: If component type not registered.
            TypeError: If data doesn't match component fields.
        """
        if name not in self._components:
            raise KeyError(f"Component '{name}' not registered")

        # Use custom deserializer if available
        if name in self._deserializers:
            result: Component = self._deserializers[name](data)
            return result

        component_type = self._components[name]
        return self._instantiate_component(component_type, data)

    def _instantiate_component(
        self,
        component_type: type[Component],
        data: dict[str, Any],
    ) -> Component:
        """Instantiate a component with type conversion.

        Args:
            component_type: The component class.
            data: Field data dictionary.

        Returns:
            Component instance.
        """
        # Check if dataclass at runtime (avoid mypy's aggressive type narrowing)
        is_dc = dataclasses.is_dataclass(component_type)
        if is_dc:
            return self._instantiate_dataclass(component_type, data)

        # Fallback: try direct instantiation
        return component_type(**data)

    def _builtins(self) -> dict[type, Callable[[Any], Any]]:
        """Return the type converters every registry starts with."""
        return {
            Vector2: _convert_vector2,
            Color: _convert_color,
            ModifiableValue: self._convert_modifiable,
        }

    def _fields_of(self, cls: type[Component]) -> _Fields:
        """A dataclass's type hints and assignable field names, worked out once.

        Resolving type hints evaluates every annotation, which costs far
        more than building the component; a class's hints do not change.
        """
        known = self._field_cache.get(cls)
        if known is None:
            hints, unresolved = _resolve_hints(cls)
            hints = {name: _unwrap_optional(hint) for name, hint in hints.items()}
            assignable = frozenset(
                f.name
                for f in dataclasses.fields(cls)  # type: ignore[arg-type]
                if not f.name.startswith("_")
            )
            known = _Fields(hints, assignable, unresolved)
            self._field_cache[cls] = known
        return known

    def _instantiate_dataclass(
        self,
        cls: type[Component],
        data: dict[str, Any],
    ) -> Component:
        """Instantiate a dataclass component with field conversion.

        Args:
            cls: Dataclass component type.
            data: Field data dictionary.

        Returns:
            Component instance.

        Raises:
            ValueError: If `data` names a field the component does not have.
        """
        converted_data: dict[str, Any] = {}
        hints, assignable, unresolved = self._fields_of(cls)

        # A key that matches no field is an authoring mistake (a typo, a
        # renamed field, wrong component). Dropping it silently would hide
        # the error until the value was missing at runtime.
        unknown = set(data) - assignable
        if unknown:
            raise ValueError(
                f"{cls.__name__} has no field(s) {sorted(unknown)}; "
                f"valid fields: {sorted(assignable)}"
            )

        for dc_field in dataclasses.fields(cls):  # type: ignore[arg-type]
            field_name = dc_field.name

            # Skip private fields
            if field_name.startswith("_"):
                continue

            if field_name in data:
                if field_name in unresolved:
                    raise ValueError(
                        f"{cls.__name__}.{field_name} cannot be set from data: its "
                        f"type annotation does not resolve "
                        f"({unresolved[field_name]})"
                    )
                value = data[field_name]
                converted_data[field_name] = self._convert_value(
                    value, hints[field_name]
                )

        return cls(**converted_data)

    def _convert_value(self, value: Any, target_type: Any) -> Any:
        """Convert a value to the target type.

        A type with no converter takes the value as it is.

        Args:
            value: Raw value from serialized data.
            target_type: The field's resolved type, `X | None` already
                unwrapped to `X`.

        Returns:
            Converted value.
        """
        if value is None:
            return None

        if target_type in self._type_converters:
            return self._type_converters[target_type](value)

        # Handle enums: accept a member name (case-insensitive) or a raw value.
        if isinstance(target_type, type) and issubclass(target_type, enum.Enum):
            return self._convert_enum(value, target_type)

        return value

    def _convert_modifiable(self, value: Any) -> Any:
        """Rebuild a `ModifiableValue` from the number that was stored.

        A stat is written as its base -- the number a designer typed --
        because the modifiers stacked on top are runtime state, put there
        by whatever applied them. Loading one back gives a value with no
        modifiers, which is the authored state and not a half-remembered
        playthrough.

        Args:
            value: What the file held: a number, or a value already.

        Returns:
            A `ModifiableValue`, or `value` unchanged when it is neither
            -- which leaves the component's own construction to raise with
            a better message than this could.
        """
        if isinstance(value, ModifiableValue):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return ModifiableValue(float(value))
        return value

    def _convert_enum(self, value: Any, enum_type: type[enum.Enum]) -> Any:
        """Coerce serialized data to an enum member.

        Accepts an existing member, an exact or case-insensitive member name,
        or a raw member value. A string that matches nothing raises
        ``ValueError`` naming the valid members rather than a bare ``KeyError``.

        Raises:
            ValueError: If the value is not a member of the enum.
        """
        if isinstance(value, enum_type):
            return value

        if isinstance(value, str):
            if value in enum_type.__members__:
                return enum_type[value]
            for member in enum_type:
                if member.name.lower() == value.lower():
                    return member
            try:
                return enum_type(value)
            except ValueError:
                members = ", ".join(m.name for m in enum_type)
                raise ValueError(
                    f"{value!r} is not a valid {enum_type.__name__} "
                    f"(expected one of: {members})"
                ) from None

        return enum_type(value)

    def _register_builtin_deserializers(self) -> None:
        """Register deserializers for built-in components."""
        # Transform has a custom __init__ and needs special handling
        self._deserializers["Transform"] = self._deserialize_transform

    def _deserialize_transform(self, data: dict[str, Any]) -> Any:
        """Deserialize Transform component.

        Args:
            data: Transform data dictionary.

        Returns:
            Transform component instance.

        Raises:
            ValueError: If `data` names a field Transform does not have, or
                a field's value is not of its type.
        """
        from pyguara.common.components import Transform

        if not _TRANSFORM_FIELDS.issuperset(data):
            unknown = set(data) - _TRANSFORM_FIELDS
            raise ValueError(
                f"Transform has no field(s) {sorted(unknown)}; "
                f"valid fields: {sorted(_TRANSFORM_FIELDS)}"
            )
        position = None
        rotation = 0.0
        scale = None

        if "position" in data:
            position = _convert_vector2(data["position"])
        if "rotation" in data:
            if not _is_number(data["rotation"]):
                raise ValueError(
                    f"Transform.rotation is a number, not {data['rotation']!r}"
                )
            rotation = float(data["rotation"])
        if "scale" in data:
            scale = _convert_vector2(data["scale"])

        transform = Transform(position=position, rotation=rotation, scale=scale)
        # Not a constructor argument, so it has to be assigned after. Omitting
        # it meant a saved physics entity reloaded un-interpolated and
        # visibly juddered at any frame rate above the fixed tick --
        # `PhysicsSystem` sets this on every body it creates.
        if "interpolate" in data:
            if not isinstance(data["interpolate"], bool):
                raise ValueError(
                    f"Transform.interpolate is true or false, "
                    f"not {data['interpolate']!r}"
                )
            transform.interpolate = data["interpolate"]
        return transform

    def list_components(self) -> list[str]:
        """Get list of all registered component names.

        Returns:
            Sorted list of component names.
        """
        return sorted(self._components.keys())

    def clear(self) -> None:
        """Clear user registrations, restoring the registry's built-in state.

        Removes every component type and custom deserializer/type converter
        added since construction, then re-seeds the built-ins (the ``Vector2``,
        ``Color`` and ``ModifiableValue`` converters and the ``Transform``
        deserializer). Without the
        re-seed, a cleared registry could no longer round-trip ``Transform`` —
        it has a custom ``__init__`` and is not a dataclass, so the generic
        instantiation path cannot build it from raw dict data.
        """
        self._components.clear()
        self._deserializers.clear()
        self._field_cache.clear()
        self._type_converters = self._builtins()
        self._register_builtin_deserializers()


_TRANSFORM_FIELDS = frozenset({"position", "rotation", "scale", "interpolate"})


class _Fields(NamedTuple):
    """What the registry needs to know about a dataclass's fields."""

    hints: dict[str, Any]
    assignable: frozenset[str]
    unresolved: dict[str, str]


def _resolve_hints(cls: type) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve a dataclass's field types, field by field if need be.

    An annotation naming a type imported only for type checking cannot be
    resolved at run time. Only that field is left out: its name maps, in
    the second result, to why it did not resolve.
    """
    fields = dataclasses.fields(cls)
    try:
        hints = get_type_hints(cls)
    except (NameError, TypeError):
        pass
    else:
        return {f.name: hints.get(f.name, f.type) for f in fields}, {}
    resolved: dict[str, Any] = {}
    unresolved: dict[str, str] = {}
    for f in fields:
        owner = next(
            k for k in cls.__mro__ if f.name in getattr(k, "__annotations__", {})
        )
        annotation = owner.__annotations__[f.name]
        if not isinstance(annotation, str):
            resolved[f.name] = annotation
            continue
        namespace = vars(sys.modules[owner.__module__])
        try:
            # What `get_type_hints` does for the whole class, one field at a
            # time, on annotations from the engine's or the game's own code.
            resolved[f.name] = eval(annotation, namespace, dict(vars(owner)))  # noqa: S307
        except (NameError, TypeError) as error:
            unresolved[f.name] = str(error)
    return resolved, unresolved


def _unwrap_optional(hint: Any) -> Any:
    """Return `X` for a hint of `X | None`, so the field converts as `X`."""
    if get_origin(hint) in (Union, types.UnionType):
        members = [t for t in get_args(hint) if t is not type(None)]
        if len(members) == 1:
            return members[0]
    return hint


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _convert_vector2(value: Any) -> Vector2:
    """Build a `Vector2` from `{"x": .., "y": ..}` or `[x, y]`.

    Raises:
        ValueError: If the data is neither, or a coordinate is not a number.
    """
    if isinstance(value, Vector2):
        return value
    if isinstance(value, dict) and len(value) == 2 and "x" in value and "y" in value:
        x, y = value["x"], value["y"]
    elif isinstance(value, list | tuple) and len(value) == 2:
        x, y = value
    else:
        raise ValueError(f'a Vector2 is {{"x": .., "y": ..}} or [x, y], not {value!r}')
    if not (_is_number(x) and _is_number(y)):
        raise ValueError(f"a Vector2's coordinates are numbers, not {value!r}")
    return Vector2(x, y)


def _convert_color(value: Any) -> Color:
    """Build a `Color` from a dict, a list of 3 or 4 channels, or hex.

    Raises:
        ValueError: If the data is none of those, or a channel is not a
            number.
    """
    if isinstance(value, Color):
        return value
    if isinstance(value, str):
        return Color.from_hex(value)
    if isinstance(value, dict) and {"r", "g", "b"} <= set(value) <= {
        "r",
        "g",
        "b",
        "a",
    }:
        channels = [value[k] for k in ("r", "g", "b", "a") if k in value]
    elif isinstance(value, list | tuple) and len(value) in (3, 4):
        channels = list(value)
    else:
        raise ValueError(
            f'a Color is {{"r", "g", "b"[, "a"]}}, [r, g, b(, a)] or "#rrggbb", '
            f"not {value!r}"
        )
    if not all(_is_number(channel) for channel in channels):
        raise ValueError(f"a Color's channels are numbers, not {value!r}")
    return Color(*channels)


# Global registry instance
_global_registry: ComponentRegistry | None = None


def get_component_registry() -> ComponentRegistry:
    """Get the global component registry instance.

    Creates the registry on first access.

    Returns:
        The global ComponentRegistry.
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ComponentRegistry()
    return _global_registry


def register_component(
    component_type: type[Component], name: str | None = None
) -> type[Component]:
    """Register a component with the global registry.

    Can be used as a decorator:
        @register_component
        class MyComponent(BaseComponent):
            ...

    Args:
        component_type: The component class.
        name: Optional custom registration name.

    Returns:
        The component class unchanged.
    """
    get_component_registry().register(component_type, name)
    return component_type
