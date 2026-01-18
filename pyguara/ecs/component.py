"""Base component definitions for the Entity Component System.

Components in the ECS pattern should be data-only containers. Logic belongs
in Systems, not Components. This module provides:

- BaseComponent: Reference implementation with legacy method support (warns)
- StrictComponent: Enforces data-only pattern (errors on logic methods)

The allowed methods in components are:
- Lifecycle methods: __init__, __post_init__, on_attach, on_detach
- Dunder methods: __repr__, __str__, __eq__, __hash__, etc.
- Properties (via @property decorator)
"""

import logging
import warnings
from typing import Any, Optional, Protocol, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from pyguara.ecs.entity import Entity

logger = logging.getLogger(__name__)

# Methods allowed in data-only components
ALLOWED_METHODS: Set[str] = {
    # Lifecycle
    "__init__",
    "__post_init__",
    "on_attach",
    "on_detach",
    # Dataclass internals
    "__dataclass_fields__",
    "__dataclass_params__",
    # Standard dunders
    "__repr__",
    "__str__",
    "__eq__",
    "__ne__",
    "__hash__",
    "__lt__",
    "__le__",
    "__gt__",
    "__ge__",
    "__bool__",
    "__len__",
    "__iter__",
    "__getitem__",
    "__setitem__",
    "__delitem__",
    "__contains__",
    "__copy__",
    "__deepcopy__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
    "__sizeof__",
    "__format__",
    # Class infrastructure
    "__new__",
    "__del__",
    "__init_subclass__",
    "__class_getitem__",
    "__set_name__",
}


def _is_property(cls: type, name: str) -> bool:
    """Check if a class attribute is a property."""
    for base in cls.__mro__:
        if name in base.__dict__:
            attr = base.__dict__[name]
            return isinstance(attr, property)
    return False


def _get_logic_methods(cls: type, base_cls: type) -> list[str]:
    """Find methods that contain logic (not allowed in data-only components).

    Args:
        cls: The class to check.
        base_cls: The base component class to exclude from checking.

    Returns:
        List of method names that violate data-only principle.
    """
    logic_methods = []

    for name in dir(cls):
        # Skip private/magic unless it's a known method
        if name.startswith("_") and name not in ALLOWED_METHODS:
            # Check if it's a dunder we don't know about
            if name.startswith("__") and name.endswith("__"):
                continue
            # Private methods starting with _ are suspicious but allowed
            continue

        # Skip allowed methods
        if name in ALLOWED_METHODS:
            continue

        # Skip properties
        if _is_property(cls, name):
            continue

        # Check if it's defined in the class (not inherited from base)
        try:
            attr = getattr(cls, name)
        except AttributeError:
            continue

        # Skip class/static variables
        if not callable(attr):
            continue

        # Check if this is defined in our class, not in BaseComponent/StrictComponent
        for base in cls.__mro__:
            if base is base_cls or base is object:
                continue
            if name in base.__dict__:
                # It's a method defined in this class or a non-base parent
                logic_methods.append(name)
                break

    return logic_methods


class Component(Protocol):
    """Interface that all components must implement."""

    entity: Optional["Entity"]

    def on_attach(self, entity: "Entity") -> None:
        """Call when the component is added to an entity."""
        ...

    def on_detach(self) -> None:
        """Call when the component is removed from an entity."""
        ...


class BaseComponent:
    """Reference implementation of the Component protocol.

    Inherit from this to automatically satisfy ECS requirements.

    Note:
        Components should be data-only containers. Logic belongs in Systems.
        This class allows methods for backwards compatibility but will warn
        if logic methods are detected. For strict enforcement, use
        StrictComponent instead.

    Attributes:
        _allow_methods: Class attribute to suppress method warnings.
            Set to True on legacy components that need methods.
    """

    _allow_methods: bool = False

    def __init__(self) -> None:
        """Initialize the Base Component."""
        self.entity: Optional["Entity"] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate subclasses for data-only pattern compliance."""
        super().__init_subclass__(**kwargs)

        # Skip validation if methods are explicitly allowed
        if getattr(cls, "_allow_methods", False):
            return

        # Find logic methods
        logic_methods = _get_logic_methods(cls, BaseComponent)

        if logic_methods:
            method_list = ", ".join(sorted(logic_methods))
            warnings.warn(
                f"Component '{cls.__name__}' has logic methods: {method_list}. "
                f"Components should be data-only. Move logic to a System, or set "
                f"_allow_methods = True to suppress this warning.",
                UserWarning,
                stacklevel=2,
            )

    def on_attach(self, entity: "Entity") -> None:
        """Store reference to the owner entity."""
        self.entity = entity

    def on_detach(self) -> None:
        """Clear reference to the owner entity."""
        self.entity = None


class StrictComponent(BaseComponent):
    """A component that strictly enforces the data-only pattern.

    Unlike BaseComponent, StrictComponent will raise a TypeError at class
    definition time if logic methods are detected. Use this for new components
    to ensure they follow proper ECS principles.

    Example:
        @dataclass
        class Position(StrictComponent):
            x: float = 0.0
            y: float = 0.0
            # No methods allowed!

        @dataclass
        class Velocity(StrictComponent):
            dx: float = 0.0
            dy: float = 0.0

            def update(self):  # This will raise TypeError!
                pass
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate subclasses and error on logic methods."""
        # Skip BaseComponent's warning validation
        object.__init_subclass__()

        # Find logic methods
        logic_methods = _get_logic_methods(cls, StrictComponent)

        if logic_methods:
            method_list = ", ".join(sorted(logic_methods))
            raise TypeError(
                f"StrictComponent '{cls.__name__}' has logic methods: {method_list}. "
                f"Components must be data-only. Move this logic to a System."
            )
