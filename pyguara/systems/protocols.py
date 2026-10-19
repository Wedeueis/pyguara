"""Protocol definitions for game systems."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class System(Protocol):
    """Protocol for game logic systems.

    A system processes game state once per **fixed** step, not once per
    rendered frame -- see `update()`. Examples include:

    - PhysicsSystem: Updates physics simulation
    - AISystem: Updates AI decision making
    - AnimationSystem: Updates animations
    - AudioSystem: Updates sound effects

    Conformance is structural and checked by method name at runtime: a
    class with a matching `update` satisfies this without inheriting from
    it, and nothing in the engine declares that it implements it. That is
    why `update` keeps its name rather than being corrected to
    `fixed_update` -- a rename would leave every unmigrated system
    satisfying this protocol and silently never ticking. ADR 0005
    (`docs/adr/0005-fixed-and-variable-step-naming.md`) has the argument.
    """

    def update(self, dt: float) -> None:
        """Advance one **fixed** step -- the deterministic channel.

        `SceneManager.fixed_update()` is what calls this, so it runs at a
        constant rate (60 Hz by default) regardless of display framerate.
        That is what game logic generally wants.

        Note:
            This is the **opposite** of `Scene.update()`, which is the
            variable, per-frame step. The two spellings are inverted
            between scenes and systems, deliberately: see ADR 0005
            (`docs/adr/0005-fixed-and-variable-step-naming.md`). For
            per-frame work implement `VariableStepSystem` as well and use
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
        """Advance one **fixed** step, exactly as `System.update()`.

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
        """Advance one **fixed** step, exactly as `System.update()`.

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
        Recorded as ADR 0005
        (`docs/adr/0005-fixed-and-variable-step-naming.md`), which also
        says what a safe rename would have to look like.
    """

    def variable_update(self, dt: float) -> None:
        """Advance one **variable** step: once per rendered frame.

        The other channel from `update()`, which is the fixed step. See
        ADR 0005 (`docs/adr/0005-fixed-and-variable-step-naming.md`) for
        why the two are named the way they are.

        Args:
            dt: Seconds since the last rendered frame; varies with
                framerate, so nothing deterministic should depend on it.
        """
        ...
