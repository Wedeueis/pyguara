"""Base component definitions for the Entity Component System."""

from typing import Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from pyguara.ecs.entity import Entity


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
    """
    Reference implementation of the Component protocol.

    Inherit from this to automatically satisfy ECS requirements.
    """

    def __init__(self) -> None:
        """Initialize the Base Component."""
        self.entity: Optional["Entity"] = None

    def on_attach(self, entity: "Entity") -> None:
        """Store reference to the owner entity."""
        self.entity = entity

    def on_detach(self) -> None:
        """Clear reference to the owner entity."""
        self.entity = None
