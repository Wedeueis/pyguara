"""Base component definitions for the Entity Component System.

Components are data-only containers; logic belongs in Systems. Two base
classes enforce that rule at different strengths:

- `BaseComponent` warns when a subclass declares a logic method.
- `StrictComponent` raises `TypeError` at class-definition time instead.

Prefer `StrictComponent` for new components. A component may still declare
lifecycle hooks (`__init__`, `__post_init__`, `on_attach`, `on_detach`),
dunder methods, `@property` accessors, and methods marked `@pure_query` --
side-effect-free reads of the component's own fields.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

if TYPE_CHECKING:
    from pyguara.ecs.entity import Entity

ALLOWED_METHODS: frozenset[str] = frozenset(
    {
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
)


_PURE_QUERY_FLAG = "__pyguara_pure_query__"


def pure_query(method: _F) -> _F:
    """Mark a component method as a side-effect-free read of its own fields.

    The data-only rule exists so behaviour cannot hide inside components,
    and a method that only *reads* the component it is called on hides
    nothing. `tags.has_tag("enemy")` is the same fact as
    `has_tag(tags, "enemy")` and reads better at the call site, so the
    rule allows it -- explicitly, at the definition, rather than by
    accident.

    **This is not an escape hatch.** A pure query may not mutate anything,
    may not reach a system, a backend or the event dispatcher, and may not
    touch another entity's state. Anything that does is logic and belongs
    in a system; `_allow_methods = True` remains the way to say "this is
    logic and I know it", and remains a thing to migrate rather than keep.

    Example:
        ```python
        @dataclass(slots=True)
        class EntityTags(StrictComponent):
            tags: set[str] = field(default_factory=set)

            @pure_query
            def has_tag(self, tag: str) -> bool:
                return tag in self.tags
        ```

    Args:
        method: The method to mark.

    Returns:
        The same method, flagged so the data-only check skips it.
    """
    setattr(method, _PURE_QUERY_FLAG, True)
    return method


def _is_pure_query(cls: type, name: str) -> bool:
    """Report whether `name` resolves to a method marked `@pure_query`.

    Args:
        cls: The class whose MRO is searched.
        name: The attribute name to resolve.

    Returns:
        True if the first definition of `name` in the MRO carries the mark.
    """
    for base in cls.__mro__:
        if name in base.__dict__:
            return getattr(base.__dict__[name], _PURE_QUERY_FLAG, False) is True
    return False


def _is_property(cls: type, name: str) -> bool:
    """Report whether a class attribute resolves to a property descriptor.

    Args:
        cls: The class whose MRO is searched.
        name: The attribute name to resolve.

    Returns:
        True if the first definition of `name` in the MRO is a `property`.
    """
    for base in cls.__mro__:
        if name in base.__dict__:
            return isinstance(base.__dict__[name], property)
    return False


def _get_logic_methods(cls: type, base_cls: type) -> list[str]:
    """Find methods on a component class that violate the data-only rule.

    Args:
        cls: The component subclass being validated.
        base_cls: The component base class whose own methods are exempt.

    Returns:
        Sorted names of callables declared by `cls` (or by a parent other
        than `base_cls`) that are neither allowed lifecycle hooks nor
        properties.
    """
    logic_methods = []

    for name in dir(cls):
        # Underscore-prefixed names are exempt: unrecognised dunders belong to
        # Python or to @dataclass, and a private helper is a deliberate opt-out.
        if name in ALLOWED_METHODS or name.startswith("_"):
            continue

        if _is_property(cls, name) or _is_pure_query(cls, name):
            continue

        try:
            attr = getattr(cls, name)
        except AttributeError:
            continue

        if not callable(attr):
            continue

        for base in cls.__mro__:
            if base is base_cls or base is object:
                continue
            if name in base.__dict__:
                logic_methods.append(name)
                break

    return sorted(logic_methods)


class Component(Protocol):
    """Structural interface that every component satisfies."""

    entity: Entity | None

    def on_attach(self, entity: Entity) -> None:
        """Bind the component to the entity that now owns it."""
        ...

    def on_detach(self) -> None:
        """Unbind the component from its owning entity."""
        ...


class BaseComponent:
    """Reference implementation of the `Component` protocol.

    Subclasses that declare logic methods trigger a `UserWarning` at class
    definition time. Set `_allow_methods = True` on a subclass to opt out;
    prefer `StrictComponent` for new code, which rejects such methods outright.

    `__slots__` keeps per-instance overhead low. Dataclass subclasses should
    declare `@dataclass(slots=True)`; non-dataclass subclasses should declare
    their own `__slots__`.

    Attributes:
        entity: The owning entity, or None while detached.
    """

    __slots__ = ("entity",)

    _allow_methods: bool = False

    def __init__(self) -> None:
        """Initialise the component in a detached state."""
        self.entity: Entity | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Warn if the subclass declares logic methods.

        Args:
            **kwargs: Class keyword arguments, forwarded to `super()`.
        """
        super().__init_subclass__(**kwargs)

        if getattr(cls, "_allow_methods", False):
            return

        logic_methods = _get_logic_methods(cls, BaseComponent)
        if logic_methods:
            warnings.warn(
                f"Component '{cls.__name__}' has logic methods: "
                f"{', '.join(logic_methods)}. Components should be data-only. "
                f"Move logic to a System, or set _allow_methods = True to "
                f"suppress this warning.",
                UserWarning,
                stacklevel=2,
            )

    def on_attach(self, entity: Entity) -> None:
        """Bind the component to the entity that now owns it.

        Args:
            entity: The owning entity.
        """
        self.entity = entity

    def on_detach(self) -> None:
        """Unbind the component from its owning entity."""
        self.entity = None


class StrictComponent(BaseComponent):
    """A component that rejects logic methods at class-definition time.

    Where `BaseComponent` warns, `StrictComponent` raises `TypeError`. Use it
    for new components so ECS boundaries cannot erode silently.

    Raises:
        TypeError: If a subclass declares a method that is not a lifecycle
            hook, a dunder, or a property.

    Example:
        ```python
        @dataclass(slots=True)
        class Position(StrictComponent):
            x: float = 0.0
            y: float = 0.0
        ```
    """

    __slots__ = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Reject subclasses that declare logic methods.

        Args:
            **kwargs: Class keyword arguments, forwarded to `super()`.

        Raises:
            TypeError: If logic methods are found.
        """
        # Chain past BaseComponent deliberately: its warn-only check would
        # otherwise fire alongside the hard error raised here.
        super(BaseComponent, cls).__init_subclass__(**kwargs)

        logic_methods = _get_logic_methods(cls, StrictComponent)
        if logic_methods:
            raise TypeError(
                f"StrictComponent '{cls.__name__}' has logic methods: "
                f"{', '.join(logic_methods)}. Components must be data-only. "
                f"Move this logic to a System."
            )
