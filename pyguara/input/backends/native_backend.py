"""Input backends in the native extension: what the wgpu backend uses.

The keyboard and mouse arrive with the window (`NativeWindow`); what is
here is the rest of what SDL provided through pygame: gamepads (gilrs) and
the clipboard (arboard).
"""

from __future__ import annotations

from typing import Any

from pyguara import native


class NativeClipboard:
    """The desktop clipboard, through arboard.

    Implements `pyguara.ui.clipboard.Clipboard`, as `PygameClipboard` does,
    with the same promise: **no call raises.** A clipboard that cannot be
    opened -- no clipboard manager, no display -- reads as empty and
    swallows writes, because a text field is no place to surface either.
    """

    def __init__(self) -> None:
        """Open the clipboard, or remember that it cannot be."""
        self._clipboard: Any = None
        try:
            extension = native.require_extension("The native clipboard")
            self._clipboard = extension.NativeClipboard()
        except RuntimeError:
            self._clipboard = None

    def get_text(self) -> str:
        """Return the clipboard's text, or `""` when there is none to read."""
        if self._clipboard is None:
            return ""
        return str(self._clipboard.get_text())

    def set_text(self, text: str) -> None:
        """Put `text` on the clipboard; a refusal is swallowed."""
        if self._clipboard is not None:
            self._clipboard.set_text(text)


class NativeJoystick:
    """One gamepad, as `IJoystick`, read from `NativeGamepads`.

    Buttons and axes are already in `GamepadButton` and `GamepadAxis`
    numbering, so `GamepadManager`'s indices mean the same button on every
    pad -- see `rust/src/gamepad.rs`.
    """

    def __init__(self, pads: Any, pad_id: int) -> None:
        """Wrap one pad.

        Args:
            pads: The `NativeGamepads` it belongs to.
            pad_id: Its id there.
        """
        self._pads = pads
        self._id = pad_id

    def init(self) -> None:
        """Nothing to do: a connected pad is already readable."""

    def quit(self) -> None:
        """Nothing to release: the pads are shared."""

    def get_instance_id(self) -> int:
        """Return the pad's id, stable while it stays connected."""
        return self._id

    def get_name(self) -> str:
        """Return the pad's name, or a placeholder once it is gone."""
        name = self._pads.name(self._id)
        return str(name) if name is not None else "disconnected gamepad"

    def get_numbuttons(self) -> int:
        """Return the standard layout's button count, which every pad has."""
        return int(self._pads.BUTTONS)

    def get_numaxes(self) -> int:
        """Return the standard layout's axis count, which every pad has."""
        return int(self._pads.AXES)

    def get_button(self, button_index: int) -> bool:
        """Whether a button is held, by `GamepadButton` value."""
        return bool(self._pads.button(self._id, button_index))

    def get_axis(self, axis_index: int) -> float:
        """Return an axis, by `GamepadAxis` value."""
        return float(self._pads.axis(self._id, axis_index))

    def rumble(
        self, low_frequency: float, high_frequency: float, duration_ms: int
    ) -> bool:
        """Rumble, if the pad can; returns whether it did."""
        return bool(
            self._pads.rumble(
                self._id, low_frequency, high_frequency, max(0, duration_ms)
            )
        )


class NativeInputBackend:
    """Gamepads through gilrs, as `IInputBackend`: the wgpu backend's.

    `get_joystick_count` takes in the pads' events first, which is once a
    frame, since `GamepadManager` scans for hot-plugs every update.
    """

    def __init__(self) -> None:
        """Defer opening until `init_joysticks`, as SDL's subsystem does."""
        self._pads: Any = None

    def init_joysticks(self) -> None:
        """Start watching for gamepads."""
        if self._pads is None:
            extension = native.require_extension("Native gamepads")
            self._pads = extension.NativeGamepads()
            if self._pads.error:
                from pyguara.log import get_logger

                get_logger(__name__).warning("Gamepads: %s", self._pads.error)

    def quit_joysticks(self) -> None:
        """Stop watching."""
        self._pads = None

    def is_initialized(self) -> bool:
        """Whether `init_joysticks` has run."""
        return self._pads is not None

    def get_joystick_count(self) -> int:
        """Take in this frame's events, then count the connected pads."""
        if self._pads is None:
            return 0
        self._pads.poll()
        return len(self._pads.ids())

    def get_joystick(self, device_index: int) -> NativeJoystick:
        """Return the pad at a position in the connected list.

        Raises:
            IndexError: If fewer pads are connected.
        """
        if self._pads is None:
            raise IndexError(device_index)
        return NativeJoystick(self._pads, int(self._pads.ids()[device_index]))
