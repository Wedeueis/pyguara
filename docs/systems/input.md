# Input System

The `InputManager` (`pyguara.input`) acts as a powerful translation layer between hardware inputs and game actions.

## Architecture

1.  **Backends**: Abstracts the underlying library (e.g., `SDL2`, `Pygame`).
2.  **Raw Input**: Captures low-level events (Key presses, Joystick axis).
3.  **Action Binding**: Maps raw inputs to Semantic Actions (e.g., "SPACE" -> "Jump").
4.  **Action Dispatch**: Emits `OnActionEvent` for game logic to consume.

## Features

*   **Action-Based**: Code against actions ("Jump", "Fire"), not keys (`K_SPACE`). This supports easy rebinding.
*   **Contexts**: Support for input contexts (e.g., `GAMEPLAY`, `MENU`) to reuse keys for different actions.
*   **Gamepad Support**: Native support for controllers with axis deadzones and hot-plugging.
*   **Event-Driven**: Clean integration with the global event system.

## Usage

### 1. Register Actions
```python
input_manager.register_action("Jump", ActionType.PRESS)
input_manager.register_action("MoveX", ActionType.ANALOG)
```

### 2. Bind Keys
```python
input_manager.bind_input(InputDevice.KEYBOARD, pygame.K_SPACE, "Jump")
input_manager.bind_input(InputDevice.GAMEPAD, 0, "Jump") # Button A
```

### 3. Handle Events
```python
def on_action(self, event: OnActionEvent):
    if event.action_name == "Jump" and event.value > 0.5:
        self.player.jump()
```
