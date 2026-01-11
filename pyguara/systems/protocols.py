"""Protocol definitions for game systems."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class System(Protocol):
    """Protocol for game logic systems.

    Systems process game state each frame. Examples include:
    - PhysicsSystem: Updates physics simulation
    - AISystem: Updates AI decision making
    - AnimationSystem: Updates animations
    - AudioSystem: Updates sound effects
    """

    def update(self, dt: float) -> None:
        """Update system logic.

        Args:
            dt: Delta time in seconds since last update
        """
        ...


@runtime_checkable
class InitializableSystem(Protocol):
    """Protocol for systems that need initialization."""

    def initialize(self) -> None:
        """Initialize the system.

        Called once before the first update.
        """
        ...

    def update(self, dt: float) -> None:
        """Update system logic.

        Args:
            dt: Delta time in seconds since last update
        """
        ...


@runtime_checkable
class CleanupSystem(Protocol):
    """Protocol for systems that need cleanup."""

    def cleanup(self) -> None:
        """Cleanup system resources.

        Called when the system is being removed or the application is shutting down.
        """
        ...

    def update(self, dt: float) -> None:
        """Update system logic.

        Args:
            dt: Delta time in seconds since last update
        """
        ...
