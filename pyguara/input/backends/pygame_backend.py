"""Pygame-based input backend implementation."""

import pygame
from typing import Any

from pyguara.input.protocols import IJoystick


class PygameJoystick:
    """Wrapper around pygame.joystick.Joystick implementing IJoystick protocol."""

    def __init__(self, device_index: int) -> None:
        """Create a joystick wrapper for the given device index.

        Args:
            device_index: The device index (0-based).
        """
        self._joystick: Any = pygame.joystick.Joystick(device_index)

    def init(self) -> None:
        """Initialize this joystick for use."""
        self._joystick.init()

    def quit(self) -> None:
        """Release this joystick's resources."""
        self._joystick.quit()

    def get_instance_id(self) -> int:
        """Get the unique instance ID for this joystick."""
        return int(self._joystick.get_instance_id())

    def get_name(self) -> str:
        """Get the human-readable name of the joystick."""
        return str(self._joystick.get_name())

    def get_numbuttons(self) -> int:
        """Get the number of buttons on this joystick."""
        return int(self._joystick.get_numbuttons())

    def get_numaxes(self) -> int:
        """Get the number of analog axes on this joystick."""
        return int(self._joystick.get_numaxes())

    def get_button(self, button_index: int) -> bool:
        """Get the current state of a button."""
        return bool(self._joystick.get_button(button_index))

    def get_axis(self, axis_index: int) -> float:
        """Get the current value of an analog axis."""
        return float(self._joystick.get_axis(axis_index))

    def rumble(
        self, low_frequency: float, high_frequency: float, duration_ms: int
    ) -> bool:
        """Trigger haptic feedback/rumble."""
        try:
            if hasattr(self._joystick, "rumble"):
                self._joystick.rumble(low_frequency, high_frequency, duration_ms)
                return True
        except (pygame.error, AttributeError):
            pass
        return False


class PygameInputBackend:
    """Pygame-based input backend implementing IInputBackend protocol.

    Wraps pygame.joystick subsystem to allow dependency injection
    and headless testing.
    """

    def init_joysticks(self) -> None:
        """Initialize the pygame joystick subsystem."""
        pygame.joystick.init()

    def quit_joysticks(self) -> None:
        """Shutdown the pygame joystick subsystem."""
        pygame.joystick.quit()

    def is_initialized(self) -> bool:
        """Check if the joystick subsystem is initialized."""
        return bool(pygame.joystick.get_init())

    def get_joystick_count(self) -> int:
        """Get the number of connected joysticks."""
        return pygame.joystick.get_count()

    def get_joystick(self, device_index: int) -> IJoystick:
        """Get a joystick handle by device index."""
        return PygameJoystick(device_index)
