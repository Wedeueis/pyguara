"""Core input processing system."""

from pyguara.log import get_logger
import pygame
from typing import Any, Dict, Optional

from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.binding import KeyBindingManager
from pyguara.input.events import (
    GamepadAxisEvent,
    GamepadButtonEvent,
    OnActionEvent,
    OnMouseEvent,
    OnRawKeyEvent,
)
from pyguara.input.protocols import IInputBackend
from pyguara.input.types import (
    ActionType,
    InputAction,
    InputContext,
    InputDevice,
    GamepadConfig,
)
from pyguara.input.gamepad import GamepadManager
from pyguara.replay.recorder import ReplayRecorder
from pyguara.replay.types import InputEventType, RecordedInputEvent

logger = get_logger(__name__)


class InputManager:
    """Translates Hardware Events (Keyboard/Mouse/Gamepad) into Actions."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        input_backend: IInputBackend,
        gamepad_config: Optional[GamepadConfig] = None,
    ) -> None:
        """Initialize input manager and bindings.

        Args:
            dispatcher: Event dispatcher for firing input events.
            input_backend: Backend for joystick subsystem access, shared with
                the owned `GamepadManager`.
            gamepad_config: Optional gamepad configuration (deadzone, vibration, etc.).
        """
        self._dispatcher = dispatcher
        self._bindings = KeyBindingManager()
        self._input_backend = input_backend

        self._context = InputContext.GAMEPLAY
        self._registered_actions: Dict[str, InputAction] = {}
        self._recorder: Optional[ReplayRecorder] = None

        # GamepadManager owns hot-plug, per-button/axis state, and deadzone
        # filtering; bound gamepad Actions are driven off the
        # GamepadButtonEvent/GamepadAxisEvent it fires on state changes.
        self._gamepad_manager = GamepadManager(
            dispatcher, input_backend, gamepad_config
        )
        self._dispatcher.subscribe(GamepadButtonEvent, self._on_gamepad_button)
        self._dispatcher.subscribe(GamepadAxisEvent, self._on_gamepad_axis)

    @property
    def gamepad(self) -> GamepadManager:
        """Access the gamepad manager for direct controller queries.

        Returns:
            The GamepadManager instance.
        """
        return self._gamepad_manager

    def attach_recorder(self, recorder: ReplayRecorder) -> None:
        """Start feeding every processed input event to `recorder`.

        Args:
            recorder: An already-`start_recording()`-ed `ReplayRecorder`.
        """
        self._recorder = recorder

    def detach_recorder(self) -> None:
        """Stop feeding input events to any attached recorder."""
        self._recorder = None

    def process_replayed_event(self, event: RecordedInputEvent) -> None:
        """Feed a recorded input event through the same handling as a live one.

        Args:
            event: A single event from a loaded `ReplayData` frame.
        """
        if event.event_type in (InputEventType.KEY_DOWN, InputEventType.KEY_UP):
            self._handle_input(
                InputDevice.KEYBOARD,
                event.code,
                is_down=event.event_type == InputEventType.KEY_DOWN,
            )
        elif event.event_type in (InputEventType.MOUSE_DOWN, InputEventType.MOUSE_UP):
            self._handle_input(
                InputDevice.MOUSE,
                event.code,
                is_down=event.event_type == InputEventType.MOUSE_DOWN,
            )
        elif event.event_type in (
            InputEventType.GAMEPAD_BUTTON_DOWN,
            InputEventType.GAMEPAD_BUTTON_UP,
        ):
            self._handle_input(
                InputDevice.GAMEPAD,
                event.code,
                is_down=event.event_type == InputEventType.GAMEPAD_BUTTON_DOWN,
            )
        elif event.event_type == InputEventType.GAMEPAD_AXIS:
            self._handle_axis(event.code, event.value)
        elif event.event_type == InputEventType.ACTION and event.action is not None:
            self._dispatch_action(event.action, event.value)
        # MOUSE_MOVE has no bound-action equivalent today; nothing to replay.

    def update(self) -> None:
        """Update input state. Call this once per frame before processing events.

        This updates the gamepad manager which handles:
        - Hot-plug detection
        - Button state tracking
        - Axis state tracking with deadzone
        - Event firing for changes
        """
        self._gamepad_manager.update()

    def _on_gamepad_button(self, event: GamepadButtonEvent) -> None:
        """Translate a GamepadManager button-state change into bound Actions."""
        self._handle_input(
            InputDevice.GAMEPAD, event.button.value, is_down=event.is_pressed
        )

    def _on_gamepad_axis(self, event: GamepadAxisEvent) -> None:
        """Translate a GamepadManager axis-state change into bound Actions."""
        self._handle_axis(event.axis.value, event.value)

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
            is_down = event.type == pygame.KEYDOWN
            self._handle_input(InputDevice.KEYBOARD, event.key, is_down=is_down)

            if self._recorder is not None and self._recorder.is_recording:
                if is_down:
                    self._recorder.record_key_down(event.key)
                else:
                    self._recorder.record_key_up(event.key)

            # Dispatch raw key event for UI system
            modifiers = set()
            try:
                mods = pygame.key.get_mods()
                if mods & pygame.KMOD_SHIFT:
                    modifiers.add(pygame.KMOD_SHIFT)
                if mods & pygame.KMOD_CTRL:
                    modifiers.add(pygame.KMOD_CTRL)
                if mods & pygame.KMOD_ALT:
                    modifiers.add(pygame.KMOD_ALT)
            except pygame.error:
                pass

            raw_key_event = OnRawKeyEvent(
                key_code=event.key, is_down=is_down, modifiers=modifiers, source=self
            )
            self._dispatcher.dispatch(raw_key_event)

        # --- Mouse Buttons ---
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            is_down = event.type == pygame.MOUSEBUTTONDOWN
            self._handle_input(InputDevice.MOUSE, event.button, is_down=is_down)

            if self._recorder is not None and self._recorder.is_recording:
                if is_down:
                    self._recorder.record_mouse_down(event.button, event.pos)
                else:
                    self._recorder.record_mouse_up(event.button, event.pos)

            # Dispatch mouse event for UI system
            mouse_event = OnMouseEvent(
                position=event.pos,
                button=event.button,
                is_down=is_down,
                is_motion=False,
                source=self,
            )
            self._dispatcher.dispatch(mouse_event)

        # --- Mouse Motion ---
        elif event.type == pygame.MOUSEMOTION:
            if self._recorder is not None and self._recorder.is_recording:
                self._recorder.record_mouse_move(event.pos)

            mouse_event = OnMouseEvent(
                position=event.pos,
                button=0,
                is_down=False,
                is_motion=True,
                source=self,
            )
            self._dispatcher.dispatch(mouse_event)

        # Gamepad input isn't read from pygame events at all: GamepadManager
        # polls device/button/axis state directly (see update(), called once
        # per frame from Application.run() before poll_events()), and its
        # GamepadButtonEvent/GamepadAxisEvent drive bound Actions via
        # _on_gamepad_button()/_on_gamepad_axis() above.

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
