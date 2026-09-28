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


@runtime_checkable
class VariableStepSystem(Protocol):
    """Protocol for systems that also want a per-frame tick.

    `SystemManager.update()` runs on the **fixed** step -- `SceneManager`
    calls it from `fixed_update()`, so every registered system ticks at a
    constant rate regardless of framerate, which is what game logic
    generally wants.

    A system implementing this protocol *additionally* gets
    `variable_update()` once per rendered frame, for the work `Scene.update`
    documents: camera smoothing, tweens, particle drift -- anything whose
    job is to look smooth rather than to be deterministic. Implementing it
    is opt-in and independent; a system may define either method or both.

    Note:
        `update()` here means the fixed step, the opposite of
        `Scene.update()`. That asymmetry is deliberate rather than
        accidental: systems have ticked on the fixed step since before
        there was a variable channel to offer them, and renaming it would
        silently re-time every system in the engine and in every demo.
    """

    def variable_update(self, dt: float) -> None:
        """Advance per rendered frame.

        Args:
            dt: Seconds since the last rendered frame; varies with
                framerate.
        """
        ...
