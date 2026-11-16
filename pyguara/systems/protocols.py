"""Protocol definitions for game systems."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class System(Protocol):
    """Protocol for game logic systems.

    A system processes game state once per fixed step, not once per
    rendered frame; see `update()`. `PhysicsSystem`, `AISystem` and
    `AnimationSystem` are examples.

    Conformance is structural and checked by method name at runtime: a
    class with a matching `update` satisfies this without inheriting from
    it. That is why `update` keeps its name; see ADR 0005
    (`docs/adr/0005-fixed-and-variable-step-naming.md`).
    """

    def update(self, dt: float) -> None:
        """Advance one fixed step -- the deterministic channel.

        `SceneManager.fixed_update()` calls this, so it runs at a constant
        rate (60 Hz by default) regardless of display framerate.

        This is the opposite of `Scene.update()`, which is the variable,
        per-frame step; see ADR 0005
        (`docs/adr/0005-fixed-and-variable-step-naming.md`). For per-frame
        work implement `VariableStepSystem` as well and use
        `variable_update()`.

        Args:
            dt: The fixed step in seconds -- the same value every call,
                not the time the last frame took.
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
        """Advance one fixed step, exactly as `System.update()`.

        The deterministic channel, driven by `SceneManager.fixed_update()`
        at a constant rate -- and so the opposite of `Scene.update()`,
        which is the per-frame one. See ADR 0005
        (`docs/adr/0005-fixed-and-variable-step-naming.md`).

        Args:
            dt: The fixed step in seconds.
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
        """Advance one fixed step, exactly as `System.update()`.

        The deterministic channel, driven by `SceneManager.fixed_update()`
        at a constant rate -- and so the opposite of `Scene.update()`,
        which is the per-frame one. See ADR 0005
        (`docs/adr/0005-fixed-and-variable-step-naming.md`).

        Args:
            dt: The fixed step in seconds.
        """
        ...


@runtime_checkable
class VariableStepSystem(Protocol):
    """Protocol for systems that also want a per-frame tick.

    `SystemManager.update()` runs on the fixed step: every registered
    system ticks at a constant rate regardless of framerate.

    A system implementing this protocol additionally gets
    `variable_update()` once per rendered frame, for work that should look
    smooth: camera smoothing, tweens, particle drift.

    `update()` here means the fixed step, the opposite of
    `Scene.update()`; see ADR 0005
    (`docs/adr/0005-fixed-and-variable-step-naming.md`).
    """

    def variable_update(self, dt: float) -> None:
        """Advance one variable step: once per rendered frame.

        The other channel from `update()`, which is the fixed step. See
        ADR 0005 (`docs/adr/0005-fixed-and-variable-step-naming.md`) for
        why the two are named the way they are.

        Args:
            dt: Seconds since the last rendered frame; varies with
                framerate, so nothing deterministic should depend on it.
        """
        ...
