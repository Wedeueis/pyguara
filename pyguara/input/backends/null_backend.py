"""An input backend with no devices, for a run that has no display."""

from __future__ import annotations

from pyguara.input.protocols import IJoystick


class NullInputBackend:
    """Reports no gamepads, and needs no library to do it.

    Implements `IInputBackend`. The headless application uses it, so a
    game's tests run without a windowing library installed.
    """

    def __init__(self) -> None:
        """Start uninitialized."""
        self._initialized = False

    def init_joysticks(self) -> None:
        """Mark the joystick subsystem as initialized."""
        self._initialized = True

    def quit_joysticks(self) -> None:
        """Mark the joystick subsystem as shut down."""
        self._initialized = False

    def is_initialized(self) -> bool:
        """Report whether `init_joysticks()` has run."""
        return self._initialized

    def get_joystick_count(self) -> int:
        """Return zero: there are no devices."""
        return 0

    def get_joystick(self, device_index: int) -> IJoystick:
        """Refuse: there is no device at any index.

        Raises:
            IndexError: Always.
        """
        raise IndexError(
            f"No joystick {device_index}: the null input backend has no devices."
        )
