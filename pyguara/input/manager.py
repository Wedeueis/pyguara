"""Core input processing system."""

import pygame
from typing import Any, Dict, Optional

from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.binding import KeyBindingManager
from pyguara.input.events import OnActionEvent
from pyguara.input.types import (
    ActionType,
    InputAction,
    InputContext,
    InputDevice,
    GamepadConfig,
)
from pyguara.input.gamepad import GamepadManager


class InputManager:
    """Translates Hardware Events (Keyboard/Mouse/Gamepad) into Actions."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        gamepad_config: Optional[GamepadConfig] = None,
    ) -> None:
        """Initialize input manager, bindings, and detect controllers.

        Args:
            dispatcher: Event dispatcher for firing input events.
            gamepad_config: Optional gamepad configuration (deadzone, vibration, etc.).
        """
        self._dispatcher = dispatcher
        self._bindings = KeyBindingManager()

        self._context = InputContext.GAMEPLAY
        self._registered_actions: Dict[str, InputAction] = {}
        self._cooldowns: Dict[str, float] = {}

        # Initialize GamepadManager for comprehensive gamepad support
        self._gamepad_manager = GamepadManager(dispatcher, gamepad_config)

        # Legacy gamepad support (kept for backwards compatibility with process_event)
        pygame.joystick.init()
        self._joysticks: Dict[int, Any] = {}  # Use Any to bypass valid-type error
        self._detect_controllers()

    @property
    def gamepad(self) -> GamepadManager:
        """Access the gamepad manager for direct controller queries.

        Returns:
            The GamepadManager instance.
        """
        return self._gamepad_manager

    def update(self) -> None:
        """Update input state. Call this once per frame before processing events.

        This updates the gamepad manager which handles:
        - Hot-plug detection
        - Button state tracking
        - Axis state tracking with deadzone
        - Event firing for changes
        """
        self._gamepad_manager.update()

    def _detect_controllers(self) -> None:
        """Find and init plugged-in controllers (legacy support)."""
        if pygame.joystick.get_count() > 0:
            for i in range(pygame.joystick.get_count()):
                # Use Any to avoid mypy confusion with pygame.joystick.Joystick vs function
                joy: Any = pygame.joystick.Joystick(i)
                joy.init()
                self._joysticks[i] = joy
                print(f"Controller detected: {joy.get_name()}")

    def register_action(
        self, name: str, action_type: ActionType, deadzone: float = 0.1
    ) -> None:
        """
        Register a new action definition.

        Args:
            name: Unique name (e.g., "Jump").
            action_type: Behavior (PRESS, RELEASE, HOLD, ANALOG).
            deadzone: Threshold for analog inputs.
        """
        self._registered_actions[name] = InputAction(name, action_type, deadzone)

    def bind_input(
        self,
        device: InputDevice,
        code: int,
        action: str,
        context: InputContext = InputContext.GAMEPLAY,
    ) -> None:
        """
        Bind a physical key/button to an action.

        Args:
            device: KEYBOARD, MOUSE, GAMEPAD.
            code: KeyCode or ButtonIndex.
            action: The action name to trigger.
            context: The input context for this binding.
        """
        self._bindings.bind(device, code, action, context)

    def process_event(self, event: Any) -> None:
        """Ingest raw Pygame events."""
        # --- Keyboard ---
        if event.type in (pygame.KEYDOWN, pygame.KEYUP):
            self._handle_input(
                InputDevice.KEYBOARD, event.key, is_down=(event.type == pygame.KEYDOWN)
            )

        # --- Mouse Buttons ---
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self._handle_input(
                InputDevice.MOUSE,
                event.button,
                is_down=(event.type == pygame.MOUSEBUTTONDOWN),
            )

        # --- Gamepad Buttons ---
        elif event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
            self._handle_input(
                InputDevice.GAMEPAD,
                event.button,
                is_down=(event.type == pygame.JOYBUTTONDOWN),
            )

        # --- Gamepad Axis (Sticks/Triggers) ---
        elif event.type == pygame.JOYAXISMOTION:
            self._handle_axis(event.axis, event.value)

        # --- Hotplugging ---
        elif event.type == pygame.JOYDEVICEADDED:
            self._detect_controllers()
        elif event.type == pygame.JOYDEVICEREMOVED:
            # In a real engine, handle removal gracefully (pause game)
            if event.instance_id in self._joysticks:
                del self._joysticks[event.instance_id]

    def _handle_input(self, device: InputDevice, code: int, is_down: bool) -> None:
        """Handle binary inputs (Buttons/Keys)."""
        actions = self._bindings.get_actions(device, code, self._context)

        for action_name in actions:
            action_def = self._registered_actions.get(action_name)
            if not action_def:
                continue

            # Determine value (1.0 = Pressed, 0.0 = Released)
            value = 1.0 if is_down else 0.0

            # Logic: Dispatch based on Action Type
            should_dispatch = False

            if action_def.action_type == ActionType.PRESS and is_down:
                should_dispatch = True
            elif action_def.action_type == ActionType.RELEASE and not is_down:
                should_dispatch = True
            elif action_def.action_type == ActionType.HOLD:
                # Holds are usually handled in update(), but state change matters here
                should_dispatch = True

            if should_dispatch:
                self._dispatch_action(action_name, value)

    def _handle_axis(self, axis_index: int, value: float) -> None:
        """Handle analog inputs (Sticks)."""
        # Note: 'code' for axis is just the axis index (0=LeftX, 1=LeftY, etc.)
        actions = self._bindings.get_actions(
            InputDevice.GAMEPAD, axis_index, self._context
        )

        for action_name in actions:
            action_def = self._registered_actions.get(action_name)
            if not action_def:
                continue

            # Deadzone Check
            if abs(value) < action_def.deadzone:
                value = 0.0

            # Only dispatch if it's an Analog action or crosses threshold
            if action_def.action_type == ActionType.ANALOG:
                self._dispatch_action(action_name, value)

    def _dispatch_action(self, name: str, value: float) -> None:
        """Emit the high-level semantic event."""
        event = OnActionEvent(
            action_name=name, context=self._context.value, value=value, source=self
        )
        self._dispatcher.dispatch(event)
