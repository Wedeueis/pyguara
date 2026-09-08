"""Core input processing system."""

from typing import Any

import pygame

from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.binding import KeyBindingManager
from pyguara.input.events import (
    GamepadAxisEvent,
    GamepadButtonEvent,
    InputContextChangedEvent,
    OnActionEvent,
    OnMouseEvent,
    OnRawKeyEvent,
)
from pyguara.input.gamepad import GamepadManager
from pyguara.input.protocols import IInputBackend
from pyguara.input.types import (
    ActionType,
    GamepadConfig,
    InputAction,
    InputContext,
    InputDevice,
)
from pyguara.log import get_logger
from pyguara.replay.recorder import ReplayRecorder
from pyguara.replay.types import InputEventType, RecordedInputEvent

logger = get_logger(__name__)


def _replayed_position(event: RecordedInputEvent) -> tuple[int, int]:
    """Return the recorded pointer position as ints, or (0, 0) if none was captured."""
    if event.position is None:
        return (0, 0)
    return (int(event.position[0]), int(event.position[1]))


class InputManager:
    """Translates Hardware Events (Keyboard/Mouse/Gamepad) into Actions."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        input_backend: IInputBackend,
        gamepad_config: GamepadConfig | None = None,
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
        self._registered_actions: dict[str, InputAction] = {}
        self._recorder: ReplayRecorder | None = None

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

    @property
    def bindings(self) -> KeyBindingManager:
        """The binding table, for rebinding, conflict queries and persistence.

        Returns:
            The `KeyBindingManager` this manager resolves inputs against.
        """
        return self._bindings

    @property
    def context(self) -> InputContext:
        """The input context bindings are currently resolved against.

        Only bindings registered for this context fire. Starts at
        `InputContext.GAMEPLAY`.

        Returns:
            The active `InputContext`.
        """
        return self._context

    @context.setter
    def context(self, context: InputContext) -> None:
        """Switch the active input context.

        A game sets this when it changes mode -- opening a menu, focusing a
        text field, entering a debug overlay -- so the same physical key can
        drive `InputContext.GAMEPLAY` "jump" and `InputContext.MENU` "confirm".
        Setting the context it already holds is a no-op and fires no event.

        Args:
            context: The context to make active.
        """
        if context == self._context:
            return

        old_context = self._context
        self._context = context
        self._dispatcher.dispatch(
            InputContextChangedEvent(
                old_context=old_context.value,
                new_context=context.value,
                source=self,
            )
        )

    def set_context(self, context: InputContext) -> None:
        """Switch the active input context (imperative alias for `context`).

        Args:
            context: The context to make active.
        """
        self.context = context

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

        Drives both the bound-action path (`_handle_input`/`_handle_axis`) and
        the raw `OnRawKeyEvent`/`OnMouseEvent` stream, with the recorded pointer
        position and modifier keys, so a replay reproduces what the UI layer and
        pointer-aimed game code saw -- not just the actions.

        Args:
            event: A single event from a loaded `ReplayData` frame.
        """
        modifiers = set(event.modifiers)
        if event.event_type in (InputEventType.KEY_DOWN, InputEventType.KEY_UP):
            is_down = event.event_type == InputEventType.KEY_DOWN
            self._handle_input(InputDevice.KEYBOARD, event.code, is_down=is_down)
            self._dispatcher.dispatch(
                OnRawKeyEvent(
                    key_code=event.code,
                    is_down=is_down,
                    modifiers=modifiers,
                    source=self,
                )
            )
        elif event.event_type in (InputEventType.MOUSE_DOWN, InputEventType.MOUSE_UP):
            is_down = event.event_type == InputEventType.MOUSE_DOWN
            self._handle_input(InputDevice.MOUSE, event.code, is_down=is_down)
            self._dispatcher.dispatch(
                OnMouseEvent(
                    position=_replayed_position(event),
                    button=event.code,
                    is_down=is_down,
                    is_motion=False,
                    source=self,
                )
            )
        elif event.event_type == InputEventType.MOUSE_MOVE:
            self._dispatcher.dispatch(
                OnMouseEvent(
                    position=_replayed_position(event),
                    button=0,
                    is_down=False,
                    is_motion=True,
                    source=self,
                )
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
        if self._recorder is not None and self._recorder.is_recording:
            self._recorder.record_gamepad_button(event.button.value, event.is_pressed)

    def _on_gamepad_axis(self, event: GamepadAxisEvent) -> None:
        """Translate a GamepadManager axis-state change into bound Actions."""
        self._handle_axis(event.axis.value, event.value)
        if self._recorder is not None and self._recorder.is_recording:
            self._recorder.record_gamepad_axis(event.axis.value, event.value)

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
            modifiers = self._current_modifiers()
            self._handle_input(InputDevice.KEYBOARD, event.key, is_down=is_down)

            if self._recorder is not None and self._recorder.is_recording:
                record_key = (
                    self._recorder.record_key_down
                    if is_down
                    else self._recorder.record_key_up
                )
                record_key(event.key, sorted(modifiers))

            # Dispatch raw key event for UI system
            raw_key_event = OnRawKeyEvent(
                key_code=event.key, is_down=is_down, modifiers=modifiers, source=self
            )
            self._dispatcher.dispatch(raw_key_event)

        # --- Mouse Buttons ---
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            is_down = event.type == pygame.MOUSEBUTTONDOWN
            self._handle_input(InputDevice.MOUSE, event.button, is_down=is_down)

            if self._recorder is not None and self._recorder.is_recording:
                record_mouse = (
                    self._recorder.record_mouse_down
                    if is_down
                    else self._recorder.record_mouse_up
                )
                record_mouse(event.button, event.pos, sorted(self._current_modifiers()))

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

    @staticmethod
    def _current_modifiers() -> set[int]:
        """Return the held shift/ctrl/alt flags, empty if SDL video is down."""
        modifiers: set[int] = set()
        try:
            mods = pygame.key.get_mods()
        except pygame.error:
            return modifiers
        if mods & pygame.KMOD_SHIFT:
            modifiers.add(pygame.KMOD_SHIFT)
        if mods & pygame.KMOD_CTRL:
            modifiers.add(pygame.KMOD_CTRL)
        if mods & pygame.KMOD_ALT:
            modifiers.add(pygame.KMOD_ALT)
        return modifiers

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

            if (
                action_def.action_type == ActionType.PRESS
                and is_down
                or action_def.action_type == ActionType.RELEASE
                and not is_down
            ):
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
