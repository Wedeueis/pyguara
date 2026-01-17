"""Interfaces for input backend adapters."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class IJoystick(Protocol):
    """Interface for a joystick/gamepad handle.

    Abstracts the underlying joystick implementation to allow
    headless testing without hardware dependencies.
    """

    def init(self) -> None:
        """Initialize this joystick for use."""
        ...

    def quit(self) -> None:
        """Release this joystick's resources."""
        ...

    def get_instance_id(self) -> int:
        """Get the unique instance ID for this joystick.

        Returns:
            The instance ID assigned by the system.
        """
        ...

    def get_name(self) -> str:
        """Get the human-readable name of the joystick.

        Returns:
            The device name (e.g., "Xbox Controller").
        """
        ...

    def get_numbuttons(self) -> int:
        """Get the number of buttons on this joystick.

        Returns:
            The number of buttons available.
        """
        ...

    def get_numaxes(self) -> int:
        """Get the number of analog axes on this joystick.

        Returns:
            The number of axes available.
        """
        ...

    def get_button(self, button_index: int) -> bool:
        """Get the current state of a button.

        Args:
            button_index: The button index (0-based).

        Returns:
            True if the button is pressed, False otherwise.
        """
        ...

    def get_axis(self, axis_index: int) -> float:
        """Get the current value of an analog axis.

        Args:
            axis_index: The axis index (0-based).

        Returns:
            The axis value (-1.0 to 1.0).
        """
        ...

    def rumble(
        self, low_frequency: float, high_frequency: float, duration_ms: int
    ) -> bool:
        """Trigger haptic feedback/rumble.

        Args:
            low_frequency: Low frequency motor intensity (0.0 to 1.0).
            high_frequency: High frequency motor intensity (0.0 to 1.0).
            duration_ms: Duration in milliseconds.

        Returns:
            True if rumble was triggered, False if not supported.
        """
        ...


@runtime_checkable
class IInputBackend(Protocol):
    """Interface for the input backend.

    Abstracts joystick/controller subsystem initialization and
    device enumeration to enable headless testing without pygame.
    """

    def init_joysticks(self) -> None:
        """Initialize the joystick subsystem."""
        ...

    def quit_joysticks(self) -> None:
        """Shutdown the joystick subsystem and release resources."""
        ...

    def is_initialized(self) -> bool:
        """Check if the joystick subsystem is initialized.

        Returns:
            True if initialized, False otherwise.
        """
        ...

    def get_joystick_count(self) -> int:
        """Get the number of connected joysticks.

        Returns:
            The number of joysticks detected.
        """
        ...

    def get_joystick(self, device_index: int) -> IJoystick:
        """Get a joystick handle by device index.

        Args:
            device_index: The device index (0-based).

        Returns:
            A joystick handle implementing IJoystick.
        """
        ...
