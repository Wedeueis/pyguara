"""Ordered registry of the systems that make up a scene's game logic."""

from __future__ import annotations

from typing import Any, TypeVar

from pyguara.log import get_logger
from pyguara.systems.protocols import (
    CleanupSystem,
    InitializableSystem,
    System,
    VariableStepSystem,
)

logger = get_logger(__name__)

_S = TypeVar("_S")

DEFAULT_PRIORITY = 100


class SystemManager:
    """Holds a scene's systems and updates them in a fixed order.

    Each scene owns one of these; there is no global instance. Systems run in
    ascending priority order, so a lower number updates earlier.

    Note:
        The direction is the opposite of `EventDispatcher`, where a *higher*
        priority runs first. Systems are a pipeline -- input before physics
        before rendering -- so ascending reads naturally as a sequence; event
        handlers compete for the same event, where "most important first" is
        the natural reading.

    Example:
        ```python
        systems = SystemManager()
        systems.register(PhysicsSystem(engine, dispatcher), priority=100)
        systems.register(AISystem(entity_manager), priority=200)
        systems.initialize()

        systems.update(dt)   # physics, then AI
        ```
    """

    def __init__(self) -> None:
        """Initialise an empty, enabled manager."""
        self._systems: list[tuple[int, Any]] = []  # (priority, system)
        self._systems_by_type: dict[type[Any], Any] = {}
        self._initialized = False
        self._enabled = True
        # Systems explicitly switched off, by identity. Absent means on, so
        # registering does not have to touch this and a system that is
        # unregistered and re-registered comes back enabled.
        self._disabled: set[int] = set()

    def register(
        self,
        system: Any,
        priority: int = DEFAULT_PRIORITY,
        system_type: type[Any] | None = None,
    ) -> None:
        """Add a system to the update order.

        If `initialize()` has already run, the new system is initialised
        immediately rather than never: a scene initialises its manager in
        `resolve_dependencies()`, which happens *before* `on_enter()`, so
        every system a game registers in `on_enter()` would otherwise go
        uninitialised.

        Several systems may share a key. They all update, but `get_system()`
        and `unregister()` then reach only the most recently registered, which
        is logged. Give each a distinct `system_type` to keep them
        addressable.

        Args:
            system: The system to add. Must expose `update(dt)`.
            priority: Update order; lower runs earlier.
            system_type: Key for `get_system()`. Defaults to the system's own
                class. Pass it when several systems share a base class, or to
                register against an interface.

        Raises:
            ValueError: If `system` has no `update()` method.
        """
        if not isinstance(system, System):
            raise ValueError(f"System {system} must have an update(dt) method")

        key = system_type or type(system)
        self._warn_if_key_reused(key, system)

        self._systems.append((priority, system))
        self._systems.sort(key=lambda entry: entry[0])
        self._systems_by_type[key] = system

        if self._initialized and isinstance(system, InitializableSystem):
            system.initialize()

    def unregister(self, system_type: type[Any]) -> Any | None:
        """Remove a system by key, cleaning it up if it supports that.

        Args:
            system_type: The key the system was registered under.

        Returns:
            The removed system, or None if nothing was registered under that
            key.
        """
        system = self._systems_by_type.pop(system_type, None)
        if system is None:
            # `is None`, not truthiness: a system that defines __len__ or
            # __bool__ falsily was dropped from the type map but left in the
            # update list, still ticking and never cleaned up.
            return None

        self._systems = [(p, s) for p, s in self._systems if s is not system]
        self._disabled.discard(id(system))
        if isinstance(system, CleanupSystem):
            system.cleanup()
        return system

    def get_system(self, system_type: type[_S]) -> _S | None:
        """Retrieve a system by the key it was registered under.

        Args:
            system_type: The registration key.

        Returns:
            The system, or None if nothing is registered under that key.
        """
        return self._systems_by_type.get(system_type)

    def has_system(self, system_type: type[Any]) -> bool:
        """Report whether a key has a system registered.

        Args:
            system_type: The registration key.

        Returns:
            True if a system is registered under that key.
        """
        return system_type in self._systems_by_type

    def initialize(self) -> None:
        """Initialise every registered system that supports it.

        Idempotent. Systems registered afterwards are initialised as they are
        registered, so this need only be called once.
        """
        if self._initialized:
            return

        for _, system in self._systems:
            if isinstance(system, InitializableSystem):
                system.initialize()

        self._initialized = True

    def update(self, dt: float) -> None:
        """Advance every enabled system one **fixed** step, in priority order.

        `SceneManager` calls this from its own `fixed_update()`, so this is
        the deterministic channel: a constant rate regardless of framerate.
        A system that also wants per-frame work implements
        `VariableStepSystem` and gets `variable_update()` as well.

        Does nothing while the whole manager is disabled, and skips any
        system switched off with `set_system_enabled()`.

        Args:
            dt: The fixed step, in seconds.
        """
        if not self._enabled:
            return

        for _, system in self._systems:
            if id(system) not in self._disabled:
                system.update(dt)

    def variable_update(self, dt: float) -> None:
        """Advance every enabled `VariableStepSystem` one rendered frame.

        The other half of `update()`, for work whose job is to look smooth
        rather than to be deterministic -- camera easing, tweens, particle
        drift. `SceneManager` calls this from its own `update()`.

        Systems that do not implement `VariableStepSystem` are skipped
        entirely, so the common case costs one `isinstance` per system per
        frame and nothing else.

        Args:
            dt: Seconds since the last rendered frame; varies with framerate.
        """
        if not self._enabled:
            return

        for _, system in self._systems:
            if id(system) in self._disabled:
                continue
            if isinstance(system, VariableStepSystem):
                system.variable_update(dt)

    def cleanup(self) -> None:
        """Clean up and drop every system, leaving the manager empty.

        Systems supporting `CleanupSystem` get `cleanup()` called. The manager
        is reusable afterwards: registering again and calling `initialize()`
        works as it did the first time.
        """
        for _, system in self._systems:
            if isinstance(system, CleanupSystem):
                system.cleanup()

        self._systems.clear()
        self._systems_by_type.clear()
        self._disabled.clear()
        self._initialized = False

    def set_enabled(self, enabled: bool) -> None:
        """Turn `update()` on or off without unregistering anything.

        Used by scene pause and resume.

        Args:
            enabled: False makes `update()` a no-op.
        """
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether `update()` currently does anything."""
        return self._enabled

    def set_system_enabled(self, system_type: type[Any], enabled: bool) -> bool:
        """Turn one system's ticks on or off without unregistering it.

        For the cases where `set_enabled()` is too blunt: silencing AI while
        a menu is open, dropping a render system in a headless balance sim,
        letting a debug overlay toggle a subsystem to see what it was
        contributing. A disabled system keeps its registration, its state
        and its place in the order -- it simply does not tick, on either
        channel.

        `cleanup()` is *not* called: this is a pause, not a removal. Use
        `unregister()` to take a system out for good.

        Args:
            system_type: The key the system was registered under.
            enabled: False to skip it during `update()` and
                `variable_update()`.

        Returns:
            True if a system was found under that key, False if nothing was
            registered -- so a caller toggling an optional system can tell
            "switched off" from "never there", which a silent no-op cannot.
        """
        system = self._systems_by_type.get(system_type)
        if system is None:
            return False

        if enabled:
            self._disabled.discard(id(system))
        else:
            self._disabled.add(id(system))
        return True

    def is_system_enabled(self, system_type: type[Any]) -> bool:
        """Report whether a registered system currently ticks.

        Args:
            system_type: The key the system was registered under.

        Returns:
            True if the system is registered and not switched off. An
            unregistered key reads False: nothing under it is ticking,
            which is the question this answers.
        """
        system = self._systems_by_type.get(system_type)
        return system is not None and id(system) not in self._disabled

    @property
    def system_count(self) -> int:
        """How many systems are registered."""
        return len(self._systems)

    def get_all_systems(self) -> list[Any]:
        """Return every registered system, in update order.

        Returns:
            A snapshot list, lowest priority first.
        """
        return [system for _, system in self._systems]

    def _warn_if_key_reused(self, key: type[Any], system: Any) -> None:
        """Report that a lookup key now refers to more than one system.

        Registering several systems under one key is allowed -- they all
        update, in priority order -- but the lookup table holds a single entry
        per key, so `get_system()` returns only the newest and
        `unregister()` removes only that one. The earlier systems keep
        updating with no way to reach them by type.

        Pass a distinct `system_type` to each registration to keep them
        individually addressable.

        Args:
            key: The registration key being reused.
            system: The incoming system, so re-registering the same object is
                not mistaken for a second one.
        """
        existing = self._systems_by_type.get(key)
        if existing is None or existing is system:
            return

        logger.warning(
            f"A second system is being registered as '{key.__name__}'. Both "
            f"will update, but get_system() and unregister() will only see the "
            f"newest. Pass a distinct system_type to address them separately."
        )
