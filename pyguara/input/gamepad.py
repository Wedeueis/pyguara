"""Gamepad/Controller management system."""

import contextlib

from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.events import GamepadAxisEvent, GamepadButtonEvent
from pyguara.input.protocols import IInputBackend, IJoystick
from pyguara.input.types import (
    GamepadAxis,
    GamepadButton,
    GamepadConfig,
    GamepadState,
)
from pyguara.log import get_logger

logger = get_logger(__name__)


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
        >>> gamepad_mgr = GamepadManager(event_dispatcher, input_backend, config)
        >>> gamepad_mgr.update()
        >>> if gamepad_mgr.get_button(0, GamepadButton.A):
        >>>     print("Player 1 pressed A!")
    """

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        input_backend: IInputBackend,
        config: GamepadConfig | None = None,
    ) -> None:
        """Initialize the gamepad manager.

        Args:
            event_dispatcher: Event dispatcher for firing gamepad events.
            input_backend: Backend for joystick subsystem access and enumeration.
            config: Optional configuration for deadzone, vibration, etc.
        """
        self._event_dispatcher = event_dispatcher
        self._config = config or GamepadConfig()
        self._input_backend = input_backend
        # Controllers are keyed by a stable `controller_id` -- a small slot
        # number ("Player 1") that stays pinned to one physical device for as
        # long as it is plugged in. It is NOT the pygame device index: SDL
        # renumbers the remaining devices when one in the middle unplugs, so
        # indexing by it flags the wrong controller as gone. `_instance_ids`
        # maps our slot to SDL's stable instance id, which is what a scan
        # reconciles against.
        self._controllers: dict[int, GamepadState] = {}
        self._joysticks: dict[int, IJoystick] = {}
        self._instance_ids: dict[int, int] = {}

        if not self._input_backend.is_initialized():
            self._input_backend.init_joysticks()

        # Initial device scan
        self._scan_devices()

    def _allocate_controller_id(self) -> int:
        """Return the lowest slot number not currently assigned to a controller."""
        candidate = 0
        while candidate in self._controllers:
            candidate += 1
        return candidate

    def _scan_devices(self) -> None:
        """Reconcile tracked controllers against the devices SDL reports now.

        Enumeration is by SDL instance id, not device index: a fresh handle is
        taken for every present device each scan (device indices may have
        shifted), and controllers whose instance id is no longer present are
        disconnected.
        """
        joystick_count = self._input_backend.get_joystick_count()

        present: dict[int, IJoystick] = {}
        for i in range(joystick_count):
            try:
                joystick = self._input_backend.get_joystick(i)
                joystick.init()
                present[joystick.get_instance_id()] = joystick
            except Exception as e:
                logger.error(
                    "Failed to query joystick at device index %d: %s",
                    i,
                    e,
                    exc_info=True,
                )

        # Disconnect controllers whose device is no longer present.
        for controller_id in list(self._controllers):
            if self._instance_ids.get(controller_id) not in present:
                self._disconnect_controller(controller_id)

        # Connect devices we are not already tracking; refresh handles for the
        # ones we are (their device index, and thus the old handle, may have
        # moved).
        instance_to_slot = {iid: cid for cid, iid in self._instance_ids.items()}
        for instance_id, joystick in present.items():
            existing_slot = instance_to_slot.get(instance_id)
            if existing_slot is not None:
                self._joysticks[existing_slot] = joystick
                continue

            try:
                controller_id = self._allocate_controller_id()
                state = GamepadState(
                    controller_id=controller_id,
                    instance_id=instance_id,
                    name=joystick.get_name(),
                    is_connected=True,
                )
                self._joysticks[controller_id] = joystick
                self._controllers[controller_id] = state
                self._instance_ids[controller_id] = instance_id
                logger.info(
                    "Connected: %s (slot %d, instance %d)",
                    state.name,
                    controller_id,
                    instance_id,
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize controller (instance %d): %s",
                    instance_id,
                    e,
                    exc_info=True,
                )

    def _disconnect_controller(self, controller_id: int) -> None:
        """Mark a controller as disconnected and release its handle.

        The `GamepadState` is dropped, so the slot is free for reuse; a caller
        that queried it will see it as an unknown controller from here on.

        Args:
            controller_id: The controller ID to disconnect.
        """
        if controller_id in self._controllers:
            state = self._controllers[controller_id]
            logger.info(
                "Disconnected: %s (slot %d, instance %d)",
                state.name,
                controller_id,
                self._instance_ids.get(controller_id, -1),
            )
            del self._controllers[controller_id]

        if controller_id in self._joysticks:
            with contextlib.suppress(Exception):
                self._joysticks[controller_id].quit()
            del self._joysticks[controller_id]

        self._instance_ids.pop(controller_id, None)

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
        joystick: IJoystick,
        state: GamepadState,
    ) -> None:
        """Update button states and fire events for changes.

        Args:
            controller_id: The controller ID.
            joystick: The joystick handle.
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
                    source=self,
                )
                self._event_dispatcher.dispatch(event)

    def _update_axes(
        self,
        controller_id: int,
        joystick: IJoystick,
        state: GamepadState,
    ) -> None:
        """Update axis states with deadzone application and fire events for changes.

        Args:
            controller_id: The controller ID.
            joystick: The joystick handle.
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

    def get_controller_name(self, controller_id: int) -> str | None:
        """Get the name of a connected controller.

        Args:
            controller_id: The controller ID.

        Returns:
            The controller name, or None if not connected.
        """
        if controller_id not in self._controllers:
            return None
        return self._controllers[controller_id].name

    def get_connected_controllers(self) -> list[int]:
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
            # IJoystick protocol includes rumble method
            return joystick.rumble(low_frequency, high_frequency, duration_ms)
        except Exception:
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

        if self._input_backend.is_initialized():
            self._input_backend.quit_joysticks()

        logger.info("Shutdown complete")
