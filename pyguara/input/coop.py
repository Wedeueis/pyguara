"""Local co-op: routes input devices to player slots.

`InputManager` resolves bindings the same way regardless of who's playing;
`PlayerRouter` is the piece that decides *which* player a given device's
input belongs to, and lets a game query the result. Initial assignment
(keyboard is player 0, say) is the game's job -- `assign()` -- since the
engine has no way to guess it. What genuinely needs engine mechanism is the
dynamic part: an unassigned gamepad pressing a join button, and a gamepad
disconnecting mid-session.
"""

from __future__ import annotations

from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.events import (
    GamepadButtonEvent,
    GamepadDisconnectedEvent,
    OnActionEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
)
from pyguara.input.types import GamepadButton, InputDevice

DeviceKey = tuple[InputDevice, int | None]


class PlayerRouter:
    """Maps input devices to local player slots, and tracks per-player action state.

    Attributes:
        join_button: The gamepad button an unassigned controller presses to
            claim the next free player slot.
    """

    def __init__(
        self,
        dispatcher: EventDispatcher,
        join_button: GamepadButton = GamepadButton.START,
    ) -> None:
        """Subscribe to the events this router needs to stay current.

        Args:
            dispatcher: Event dispatcher shared with `InputManager` --
                subscribes to `GamepadButtonEvent`/`GamepadDisconnectedEvent`
                for join/leave, and `OnActionEvent` to track per-player
                action state for `is_pressed()`/`value_for()`.
            join_button: See `join_button` attribute.
        """
        self._dispatcher = dispatcher
        self.join_button = join_button
        self._device_to_player: dict[DeviceKey, int] = {}
        self._action_state: dict[tuple[int, str], float] = {}

        dispatcher.subscribe(GamepadButtonEvent, self._on_gamepad_button)
        dispatcher.subscribe(GamepadDisconnectedEvent, self._on_gamepad_disconnected)
        dispatcher.subscribe(OnActionEvent, self._on_action)

    def assign(
        self, device: InputDevice, controller_id: int | None, player: int
    ) -> None:
        """Explicitly bind a device to a player slot.

        The usual way a game establishes its default player -- keyboard and
        mouse have no join gesture of their own, so this is how they (and a
        gamepad already connected at startup, if a game wants one to just
        work without pressing anything) get attributed at all.

        Overwrites any previous assignment for `(device, controller_id)`
        silently; does not fire `PlayerLeftEvent` for whatever player it
        previously held, only a real disconnect does that.

        Args:
            device: The device type.
            controller_id: The specific gamepad's slot, or None for
                keyboard/mouse (which have only one instance).
            player: The player slot to assign it to.
        """
        self._device_to_player[(device, controller_id)] = player
        self._dispatcher.dispatch(
            PlayerJoinedEvent(
                player=player, device=device, controller_id=controller_id, source=self
            )
        )

    def player_for(
        self, device: InputDevice, controller_id: int | None = None
    ) -> int | None:
        """Return the player `device` currently drives, or None if unassigned."""
        return self._device_to_player.get((device, controller_id))

    def is_pressed(self, action: str, player: int) -> bool:
        """Return whether `player`'s last dispatched value for `action` was truthy."""
        return self._action_state.get((player, action), 0.0) > 0.0

    def value_for(self, action: str, player: int) -> float:
        """Return `player`'s last dispatched value for `action` (0.0 if none yet)."""
        return self._action_state.get((player, action), 0.0)

    def _next_free_player(self) -> int:
        """Return the lowest player slot not currently held by any device."""
        used = set(self._device_to_player.values())
        candidate = 0
        while candidate in used:
            candidate += 1
        return candidate

    def _on_gamepad_button(self, event: GamepadButtonEvent) -> None:
        """Claim the next free player slot when an unassigned pad presses join."""
        if event.button != self.join_button or not event.is_pressed:
            return
        key: DeviceKey = (InputDevice.GAMEPAD, event.controller_id)
        if key in self._device_to_player:
            return
        self.assign(InputDevice.GAMEPAD, event.controller_id, self._next_free_player())

    def _on_gamepad_disconnected(self, event: GamepadDisconnectedEvent) -> None:
        """Free the player slot a disconnected controller held, if any."""
        key: DeviceKey = (InputDevice.GAMEPAD, event.controller_id)
        player = self._device_to_player.pop(key, None)
        if player is not None:
            self._dispatcher.dispatch(
                PlayerLeftEvent(
                    player=player,
                    device=InputDevice.GAMEPAD,
                    controller_id=event.controller_id,
                    source=self,
                )
            )

    def _on_action(self, event: OnActionEvent) -> None:
        """Track the last value dispatched for each (player, action) pair."""
        self._action_state[(event.player, event.action_name)] = event.value
