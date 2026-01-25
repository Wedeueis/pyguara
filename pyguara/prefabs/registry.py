"""Component registry for the prefab system.

Provides a centralized registry for mapping component names to their types,
enabling dynamic component instantiation from serialized data.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Callable, Dict, Optional, Type, get_type_hints

from pyguara.ecs.component import Component
from pyguara.common.types import Vector2

logger = logging.getLogger(__name__)


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
        self._components: Dict[str, Type[Component]] = {}
        self._deserializers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._type_converters: Dict[type, Callable[[Any], Any]] = {
            Vector2: self._convert_vector2,
        }
        # Register built-in deserializers for special components
        self._register_builtin_deserializers()

    def register(
        self,
        component_type: Type[Component],
        name: Optional[str] = None,
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
        deserializer: Callable[[Dict[str, Any]], Any],
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

    def get(self, name: str) -> Optional[Type[Component]]:
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

    def create(self, name: str, data: Dict[str, Any]) -> Component:
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
        component_type: Type[Component],
        data: Dict[str, Any],
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

    def _instantiate_dataclass(
        self,
        cls: Type[Component],
        data: Dict[str, Any],
    ) -> Component:
        """Instantiate a dataclass component with field conversion.

        Args:
            cls: Dataclass component type.
            data: Field data dictionary.

        Returns:
            Component instance.
        """
        converted_data: Dict[str, Any] = {}

        # Get type hints for field conversion
        try:
            hints = get_type_hints(cls)
        except Exception:
            hints = {}

        for dc_field in dataclasses.fields(cls):  # type: ignore[arg-type]
            field_name = dc_field.name

            # Skip private fields
            if field_name.startswith("_"):
                continue

            if field_name in data:
                value = data[field_name]
                field_type = hints.get(field_name, dc_field.type)
                converted_data[field_name] = self._convert_value(value, field_type)

        return cls(**converted_data)

    def _convert_value(self, value: Any, target_type: Any) -> Any:
        """Convert a value to the target type.

        Args:
            value: Raw value from serialized data.
            target_type: Expected type.

        Returns:
            Converted value.
        """
        # None passthrough
        if value is None:
            return None

        # Check for registered converter
        if target_type in self._type_converters:
            return self._type_converters[target_type](value)

        # Handle Optional types
        origin = getattr(target_type, "__origin__", None)
        if origin is type(None):
            return value

        # Handle dict that looks like Vector2
        if isinstance(value, dict) and "x" in value and "y" in value:
            return Vector2(value["x"], value["y"])

        # Handle enums
        if hasattr(target_type, "__members__"):
            if isinstance(value, str):
                return target_type[value.upper()]
            return target_type(value)

        return value

    def _convert_vector2(self, value: Any) -> Vector2:
        """Convert data to Vector2.

        Args:
            value: Dict with x/y or Vector2 instance.

        Returns:
            Vector2 instance.
        """
        if isinstance(value, Vector2):
            return value
        if isinstance(value, dict):
            return Vector2(value.get("x", 0), value.get("y", 0))
        return Vector2(0, 0)

    def _register_builtin_deserializers(self) -> None:
        """Register deserializers for built-in components."""
        # Transform has a custom __init__ and needs special handling
        self._deserializers["Transform"] = self._deserialize_transform

    def _deserialize_transform(self, data: Dict[str, Any]) -> Any:
        """Deserialize Transform component.

        Args:
            data: Transform data dictionary.

        Returns:
            Transform component instance.
        """
        from pyguara.common.components import Transform

        position = None
        rotation = 0.0
        scale = None

        if "position" in data:
            position = self._convert_vector2(data["position"])
        if "rotation" in data:
            rotation = float(data["rotation"])
        if "scale" in data:
            scale = self._convert_vector2(data["scale"])

        return Transform(position=position, rotation=rotation, scale=scale)

    def list_components(self) -> list[str]:
        """Get list of all registered component names.

        Returns:
            Sorted list of component names.
        """
        return sorted(self._components.keys())

    def clear(self) -> None:
        """Clear all registrations."""
        self._components.clear()
        self._deserializers.clear()


# Global registry instance
_global_registry: Optional[ComponentRegistry] = None


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
    component_type: Type[Component], name: Optional[str] = None
) -> Type[Component]:
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
