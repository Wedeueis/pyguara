"""Gamepad/Controller management system."""

import pygame
import time
from typing import Dict, Optional, List, Any
from pyguara.input.types import (
    GamepadButton,
    GamepadAxis,
    GamepadState,
    GamepadConfig,
)
from pyguara.input.events import GamepadButtonEvent, GamepadAxisEvent
from pyguara.events.dispatcher import EventDispatcher


class GamepadManager:
    """Manages gamepad/controller input with hot-plug support and multi-controller tracking.

    Features:
    - Automatic device detection and hot-plug support
    - Multiple simultaneous controllers (up to 4+)
    - Configurable deadzone for analog inputs
    - Event-driven button and axis changes
    - Rumble/vibration support (where available)
    - Thread-safe state access

    Example:
        >>> gamepad_mgr = GamepadManager(event_dispatcher, config)
        >>> gamepad_mgr.update()
        >>> if gamepad_mgr.get_button(0, GamepadButton.A):
        >>>     print("Player 1 pressed A!")
    """

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        config: Optional[GamepadConfig] = None,
    ) -> None:
        """Initialize the gamepad manager.

        Args:
            event_dispatcher: Event dispatcher for firing gamepad events.
            config: Optional configuration for deadzone, vibration, etc.
        """
        self._event_dispatcher = event_dispatcher
        self._config = config or GamepadConfig()
        self._controllers: Dict[int, GamepadState] = {}
        self._joysticks: Dict[int, Any] = {}  # pygame.joystick.Joystick not typed

        # Initialize pygame joystick subsystem
        if not pygame.joystick.get_init():
            pygame.joystick.init()

        # Initial device scan
        self._scan_devices()

    def _scan_devices(self) -> None:
        """Scan for connected gamepad devices and initialize them."""
        joystick_count = pygame.joystick.get_count()

        # Detect new controllers
        for i in range(joystick_count):
            if i not in self._joysticks:
                try:
                    joystick = pygame.joystick.Joystick(i)
                    joystick.init()

                    # Create state tracking for this controller
                    state = GamepadState(
                        controller_id=i,
                        instance_id=joystick.get_instance_id(),
                        name=joystick.get_name(),
                        is_connected=True,
                    )

                    self._joysticks[i] = joystick
                    self._controllers[i] = state

                    print(f"[GamepadManager] Connected: {state.name} (ID: {i})")
                except pygame.error as e:
                    print(f"[GamepadManager] Failed to initialize controller {i}: {e}")

        # Detect disconnected controllers
        disconnected = []
        for controller_id in list(self._joysticks.keys()):
            if controller_id >= joystick_count:
                disconnected.append(controller_id)

        for controller_id in disconnected:
            self._disconnect_controller(controller_id)

    def _disconnect_controller(self, controller_id: int) -> None:
        """Mark a controller as disconnected and clean up resources.

        Args:
            controller_id: The controller ID to disconnect.
        """
        if controller_id in self._controllers:
            state = self._controllers[controller_id]
            state.is_connected = False
            print(f"[GamepadManager] Disconnected: {state.name} (ID: {controller_id})")

        if controller_id in self._joysticks:
            try:
                self._joysticks[controller_id].quit()
            except pygame.error:
                pass
            del self._joysticks[controller_id]

        # Keep the state for a frame to allow events to process
        # Could be removed after a delay or on next update

    def update(self) -> None:
        """Update all controller states and fire events for changes.

        Call this once per frame, typically from InputManager.update().
        """
        # Check for hot-plug events
        self._scan_devices()

        # Update each connected controller
        for controller_id, joystick in self._joysticks.items():
            if controller_id not in self._controllers:
                continue

            state = self._controllers[controller_id]

            # Update button states
            self._update_buttons(controller_id, joystick, state)

            # Update axis states
            self._update_axes(controller_id, joystick, state)

    def _update_buttons(
        self,
        controller_id: int,
        joystick: Any,  # pygame.joystick.Joystick not typed
        state: GamepadState,
    ) -> None:
        """Update button states and fire events for changes.

        Args:
            controller_id: The controller ID.
            joystick: The pygame joystick object.
            state: The current gamepad state.
        """
        num_buttons = joystick.get_numbuttons()

        for button in GamepadButton:
            button_index = button.value

            # Skip buttons that don't exist on this controller
            if button_index >= num_buttons:
                continue

            # Get current button state
            is_pressed = joystick.get_button(button_index)
            was_pressed = state.button_states.get(button, False)

            # Fire event if state changed
            if is_pressed != was_pressed:
                state.button_states[button] = is_pressed

                event = GamepadButtonEvent(
                    controller_id=controller_id,
                    button=button,
                    is_pressed=is_pressed,
                    timestamp=time.time(),
                    source=self,
                )
                self._event_dispatcher.dispatch(event)

    def _update_axes(
        self,
        controller_id: int,
        joystick: Any,  # pygame.joystick.Joystick not typed
        state: GamepadState,
    ) -> None:
        """Update axis states with deadzone application and fire events for changes.

        Args:
            controller_id: The controller ID.
            joystick: The pygame joystick object.
            state: The current gamepad state.
        """
        num_axes = joystick.get_numaxes()

        for axis in GamepadAxis:
            axis_index = axis.value

            # Skip axes that don't exist on this controller
            if axis_index >= num_axes:
                continue

            # Get raw axis value
            raw_value = joystick.get_axis(axis_index)

            # Apply deadzone
            deadzone = (
                self._config.trigger_deadzone
                if axis in (GamepadAxis.LEFT_TRIGGER, GamepadAxis.RIGHT_TRIGGER)
                else self._config.deadzone
            )

            if abs(raw_value) < deadzone:
                processed_value = 0.0
            else:
                # Scale value to account for deadzone
                sign = 1 if raw_value > 0 else -1
                processed_value = sign * (abs(raw_value) - deadzone) / (1.0 - deadzone)
                processed_value = max(-1.0, min(1.0, processed_value))

            # Apply sensitivity multiplier
            processed_value *= self._config.axis_sensitivity

            # Get previous value
            previous_value = state.axis_values.get(axis, 0.0)

            # Fire event if value changed significantly (avoid spamming)
            if abs(processed_value - previous_value) > 0.01:
                state.axis_values[axis] = processed_value

                event = GamepadAxisEvent(
                    controller_id=controller_id,
                    axis=axis,
                    value=processed_value,
                    previous_value=previous_value,
                    timestamp=time.time(),
                    source=self,
                )
                self._event_dispatcher.dispatch(event)

    def get_button(self, controller_id: int, button: GamepadButton) -> bool:
        """Check if a button is currently pressed.

        Args:
            controller_id: The controller ID (0-based).
            button: The button to check.

        Returns:
            True if the button is pressed, False otherwise.
        """
        if controller_id not in self._controllers:
            return False

        state = self._controllers[controller_id]
        return state.button_states.get(button, False)

    def get_axis(self, controller_id: int, axis: GamepadAxis) -> float:
        """Get the current value of an analog axis.

        Args:
            controller_id: The controller ID (0-based).
            axis: The axis to query.

        Returns:
            The axis value (-1.0 to 1.0 for sticks, 0.0 to 1.0 for triggers).
        """
        if controller_id not in self._controllers:
            return 0.0

        state = self._controllers[controller_id]
        return state.axis_values.get(axis, 0.0)

    def is_connected(self, controller_id: int) -> bool:
        """Check if a controller is currently connected.

        Args:
            controller_id: The controller ID to check.

        Returns:
            True if the controller is connected, False otherwise.
        """
        if controller_id not in self._controllers:
            return False
        return self._controllers[controller_id].is_connected

    def get_controller_name(self, controller_id: int) -> Optional[str]:
        """Get the name of a connected controller.

        Args:
            controller_id: The controller ID.

        Returns:
            The controller name, or None if not connected.
        """
        if controller_id not in self._controllers:
            return None
        return self._controllers[controller_id].name

    def get_connected_controllers(self) -> List[int]:
        """Get a list of all connected controller IDs.

        Returns:
            List of controller IDs (0-based indices).
        """
        return [
            controller_id
            for controller_id, state in self._controllers.items()
            if state.is_connected
        ]

    def rumble(
        self,
        controller_id: int,
        low_frequency: float = 0.0,
        high_frequency: float = 0.0,
        duration_ms: int = 0,
    ) -> bool:
        """Trigger controller rumble/vibration (if supported).

        Args:
            controller_id: The controller ID.
            low_frequency: Low frequency motor intensity (0.0 to 1.0).
            high_frequency: High frequency motor intensity (0.0 to 1.0).
            duration_ms: Duration in milliseconds (0 = infinite, stopped by next call).

        Returns:
            True if rumble was triggered, False if not supported or failed.
        """
        if not self._config.vibration_enabled:
            return False

        if controller_id not in self._joysticks:
            return False

        joystick = self._joysticks[controller_id]

        try:
            # pygame 2.0.0+ supports rumble on some platforms
            if hasattr(joystick, "rumble"):
                joystick.rumble(low_frequency, high_frequency, duration_ms)
                return True
        except (pygame.error, AttributeError):
            pass

        return False

    def stop_rumble(self, controller_id: int) -> bool:
        """Stop controller rumble/vibration.

        Args:
            controller_id: The controller ID.

        Returns:
            True if rumble was stopped, False if not supported or failed.
        """
        return self.rumble(controller_id, 0.0, 0.0, 0)

    def shutdown(self) -> None:
        """Shutdown the gamepad manager and clean up resources."""
        for controller_id in list(self._joysticks.keys()):
            self._disconnect_controller(controller_id)

        if pygame.joystick.get_init():
            pygame.joystick.quit()

        print("[GamepadManager] Shutdown complete")
