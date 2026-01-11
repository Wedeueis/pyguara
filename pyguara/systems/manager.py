"""System manager for orchestrating game logic systems."""

from typing import Any, Dict, List, Optional, Type

from pyguara.systems.protocols import InitializableSystem, CleanupSystem


class SystemManager:
    """Manages and orchestrates game logic systems.

    The SystemManager maintains a collection of systems and updates them
    in priority order each frame. This centralizes system management and
    removes the need for scenes to manually update each system.

    Example:
        >>> # Setup
        >>> system_manager = SystemManager()
        >>> system_manager.register(PhysicsSystem(engine, dispatcher), priority=100)
        >>> system_manager.register(AISystem(entity_manager), priority=200)
        >>> system_manager.initialize()
        >>>
        >>> # Game loop
        >>> system_manager.update(dt)
    """

    def __init__(self) -> None:
        """Initialize the system manager."""
        self._systems: List[tuple[int, Any]] = []  # (priority, system)
        self._systems_by_type: Dict[Type[Any], Any] = {}
        self._initialized = False
        self._enabled = True

    def register(
        self, system: Any, priority: int = 100, system_type: Optional[Type[Any]] = None
    ) -> None:
        """Register a system.

        Args:
            system: System instance to register (must have update(dt) method)
            priority: Update priority (lower values update first, default=100)
            system_type: Optional type key for retrieval (defaults to type(system))

        Raises:
            ValueError: If system doesn't have update() method
        """
        if not hasattr(system, "update"):
            raise ValueError(f"System {system} must have an update(dt) method")

        # Store system with priority
        self._systems.append((priority, system))
        # Sort by priority after adding
        self._systems.sort(key=lambda x: x[0])

        # Store by type for retrieval
        key = system_type or type(system)
        self._systems_by_type[key] = system

    def unregister(self, system_type: Type[Any]) -> Optional[Any]:
        """Unregister a system by type.

        Args:
            system_type: Type of system to remove

        Returns:
            The removed system, or None if not found
        """
        system = self._systems_by_type.pop(system_type, None)
        if system:
            self._systems = [(p, s) for p, s in self._systems if s is not system]

            # Cleanup if needed
            if isinstance(system, CleanupSystem):
                system.cleanup()

        return system

    def get_system(self, system_type: Type[Any]) -> Optional[Any]:
        """Get a registered system by type.

        Args:
            system_type: Type of system to retrieve

        Returns:
            The system instance, or None if not found
        """
        return self._systems_by_type.get(system_type)

    def has_system(self, system_type: Type[Any]) -> bool:
        """Check if a system type is registered.

        Args:
            system_type: Type of system to check

        Returns:
            True if system is registered
        """
        return system_type in self._systems_by_type

    def initialize(self) -> None:
        """Initialize all systems.

        Calls initialize() on systems that support InitializableSystem protocol.
        Should be called once before the first update.
        """
        if self._initialized:
            return

        for _, system in self._systems:
            if isinstance(system, InitializableSystem):
                system.initialize()

        self._initialized = True

    def update(self, dt: float) -> None:
        """Update all registered systems.

        Systems are updated in priority order (lowest priority first).

        Args:
            dt: Delta time in seconds
        """
        if not self._enabled:
            return

        for _, system in self._systems:
            system.update(dt)

    def cleanup(self) -> None:
        """Cleanup all systems.

        Calls cleanup() on systems that support CleanupSystem protocol.
        """
        for _, system in self._systems:
            if isinstance(system, CleanupSystem):
                system.cleanup()

        self._systems.clear()
        self._systems_by_type.clear()
        self._initialized = False

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable all system updates.

        Args:
            enabled: If False, update() will be a no-op
        """
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Check if system updates are enabled."""
        return self._enabled

    @property
    def system_count(self) -> int:
        """Get number of registered systems."""
        return len(self._systems)

    def get_all_systems(self) -> List[Any]:
        """Get all registered systems in priority order.

        Returns:
            List of system instances
        """
        return [system for _, system in self._systems]
