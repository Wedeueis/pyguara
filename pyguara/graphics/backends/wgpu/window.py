"""The window for the wgpu backend, on winit.

The window, its keyboard and mouse input and its native handle come from
`NativeWindow` (`rust/src/window.rs`), and wgpu presents straight to that
handle. Nothing here imports pygame: SDL is no longer part of this path.

**Offscreen when asked, or when no window can be opened.** Under
`PYGUARA_WINDOW=offscreen` -- which the test suite, `agent_view` and the
Studio harness set -- the frame is rendered into the device's own target
and nothing is shown. SDL's `SDL_VIDEODRIVER` does not reach it. A capture
reads it back with `read_pixels()`. `frame.gpu.has_surface` says which path
is in use, and the boot log does too.
"""

from __future__ import annotations

import os
import signal
import threading
from collections.abc import Iterable
from types import FrameType
from typing import Any

from pyguara import native
from pyguara.common.types import Color
from pyguara.config.types import WindowConfig
from pyguara.events.input import (
    KeyDownEvent,
    KeyUpEvent,
    MouseButtonEvent,
    MouseMotionEvent,
    MouseWheelEvent,
    TextInputEvent,
)
from pyguara.events.lifecycle import QuitEvent
from pyguara.events.window import WindowResizeEvent
from pyguara.graphics.backends.wgpu.frame import GpuFrame
from pyguara.log import get_logger

logger = get_logger(__name__)

# SDL's `KMOD_SHIFT`, `KMOD_CTRL`, `KMOD_ALT`: the engine's modifier values.
_MODIFIER_MASKS = (0x0003, 0x00C0, 0x0300)


def wants_offscreen() -> bool:
    """Return whether `PYGUARA_WINDOW=offscreen` asks for no window at all.

    Only the engine's own variable: SDL's `SDL_VIDEODRIVER` configures a
    library this window does not use, and honouring it would keep a name
    alive that says the opposite of what is going on.
    """
    return os.environ.get("PYGUARA_WINDOW", "").lower() == "offscreen"


def _modifiers(mods: int) -> set[int]:
    return {mask for mask in _MODIFIER_MASKS if mods & mask}


def translate(raw: tuple[Any, ...]) -> object | None:
    """Turn one `NativeWindow.pump` tuple into an engine event.

    Args:
        raw: The tuple, its first item naming the kind.

    Returns:
        The engine event, or None for one the engine has no event for.
    """
    kind = raw[0]
    if kind == "quit":
        return QuitEvent()
    if kind == "key_down":
        return KeyDownEvent(key_code=raw[1], modifiers=_modifiers(raw[2]))
    if kind == "key_up":
        return KeyUpEvent(key_code=raw[1], modifiers=_modifiers(raw[2]))
    if kind == "text":
        return TextInputEvent(text=raw[1])
    if kind == "mouse_button":
        _, button, x, y, down, mods = raw
        return MouseButtonEvent(
            button=button, x=x, y=y, is_down=down, modifiers=_modifiers(mods)
        )
    if kind == "mouse_motion":
        _, x, y, rel_x, rel_y = raw
        return MouseMotionEvent(x=x, y=y, rel_x=rel_x, rel_y=rel_y)
    if kind == "wheel":
        return MouseWheelEvent(x=float(raw[1]), y=float(raw[2]))
    if kind == "resize":
        return WindowResizeEvent(width=raw[1], height=raw[2])
    return None


class WgpuWindow:
    """A winit window whose pixels come from a wgpu frame.

    Attributes:
        frame: The frame the renderers draw into. None until `open()`.
    """

    def __init__(self) -> None:
        """Initialise with no window and no device."""
        self.frame: GpuFrame | None = None
        self._window: Any = None
        self._default_color = Color(0, 0, 0)
        self._is_open = False
        self._posted: list[object] = []
        self._size = (0, 0)
        self._move_target: tuple[int, int] | None = None
        self._previous_sigterm: Any = None

    def _quit_on_sigterm(self) -> None:
        """Turn SIGTERM into a `QuitEvent`, so the game shuts down cleanly.

        SDL did this for the pygame window: it catches SIGTERM and queues a
        quit, which that window's event pump delivers. With no SDL window,
        whoever opens SDL next -- `pygame.mixer`, for the audio -- still
        caught it, and nothing read SDL's queue, so a SIGTERM was swallowed
        and only SIGKILL ended the game. Telling SDL to keep out of signals
        and handling the one that matters here restores what a game had.

        Left alone when the game has its own handler, and off the main
        thread, where Python cannot install one.
        """
        os.environ.setdefault("SDL_NO_SIGNAL_HANDLERS", "1")
        if threading.current_thread() is not threading.main_thread():
            return
        if signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL:
            return

        def on_sigterm(_signum: int, _frame: FrameType | None) -> None:
            self.post_event(QuitEvent())

        self._previous_sigterm = signal.signal(signal.SIGTERM, on_sigterm)

    # -- IWindowBackend -----------------------------------------------------

    def open(self, config: WindowConfig) -> bool:
        """Create the window, then the device that draws for it.

        Args:
            config: Window settings to open with.

        Returns:
            True once the device exists. A window that cannot be opened is
            logged and replaced by an offscreen target, not raised.
        """
        self._default_color = config.default_color
        self._quit_on_sigterm()
        width, height = config.screen_width, config.screen_height
        handles = None
        if not wants_offscreen():
            extension = native.require_extension("The wgpu window")
            try:
                self._window = extension.NativeWindow(
                    config.title,
                    width,
                    height,
                    fullscreen=config.fullscreen,
                    resizable=getattr(config, "resizable", False),
                    # Only useful with `resizable`: a borderless window the
                    # user cannot drag an edge of is one they cannot size.
                    borderless=getattr(config, "borderless", False),
                )
            except RuntimeError as error:
                logger.warning(f"No window could be opened ({error}); offscreen.")
            if self._window is not None:
                # The OS need not grant the size asked for -- fullscreen
                # takes the monitor's -- so the device is sized by what it got.
                width, height = self._window.size
                handles = self._window.native_handles()
        self._size = (width, height)
        self.frame = GpuFrame(width, height, handles, config.vsync)
        self._is_open = True
        return True

    @property
    def width(self) -> int:
        """The drawable width in pixels, as the window system granted it."""
        return self._size[0]

    @property
    def height(self) -> int:
        """The drawable height in pixels, as the window system granted it."""
        return self._size[1]

    @property
    def has_window(self) -> bool:
        """Whether a real window is open, rather than an offscreen target."""
        return self._window is not None

    def set_caption(self, title: str) -> None:
        """Set the window title."""
        if self._window is not None:
            self._window.set_title(title)

    def poll_events(self) -> Iterable[Any]:
        """Pump the window and return this frame's engine events.

        Posted events (`post_event`) come first, then the window's own.
        """
        if not self._is_open:
            return []
        events, self._posted = self._posted, []
        if self._window is not None:
            for raw in self._window.pump():
                event = translate(raw)
                if event is None:
                    continue
                if isinstance(event, WindowResizeEvent):
                    if event.width <= 0 or event.height <= 0:
                        # Minimised: nothing to size a target to.
                        continue
                    self._size = (event.width, event.height)
                events.append(event)
        for event in events:
            if isinstance(event, QuitEvent):
                self._is_open = False
        return events

    def post_event(self, event: object) -> None:
        """Deliver an engine event with the next `poll_events`.

        How a tool drives a game -- `agent_view`'s clicks, a test's keys --
        through the path real input takes.

        Args:
            event: An engine event, such as a `KeyDownEvent`.
        """
        self._posted.append(event)

    def get_screen(self) -> Any:
        """Return the frame: what this backend's renderers draw into."""
        return self.frame

    def clear(self, color: Color | None = None) -> None:
        """Start the frame from a solid colour."""
        if self.frame is None:
            return
        fill = color if color is not None else self._default_color
        self.frame.gpu.clear(fill.r, fill.g, fill.b, 255)

    def present(self) -> None:
        """Render the frame and show it, if there is a window to show it on."""
        if self.frame is None:
            return
        gpu: Any = self.frame.gpu
        gpu.end_frame()
        self.frame.after_frame()
        if gpu.has_surface:
            gpu.present()

    def read_pixels(self) -> tuple[bytes, int, int]:
        """Return the last rendered frame, UI included, as RGBA top row first.

        Returns:
            `(pixels, width, height)`.

        Raises:
            RuntimeError: Before `open()`.
        """
        if self.frame is None:
            raise RuntimeError("The window is not open.")
        gpu: Any = self.frame.gpu
        return bytes(gpu.read_pixels()), int(gpu.width), int(gpu.height)

    def close(self) -> None:
        """Release the device, then the window."""
        self.frame = None
        if self._window is not None:
            self._window.close()
            self._window = None
        if self._previous_sigterm is not None:
            signal.signal(signal.SIGTERM, self._previous_sigterm)
            self._previous_sigterm = None
        self._is_open = False

    # -- IWindowChrome: what Studio's title bar drives ----------------------

    def minimize(self) -> None:
        """Iconify the window."""
        if self._window is not None:
            self._window.minimize()

    def maximize(self) -> None:
        """Fill the work area."""
        if self._window is not None:
            self._window.maximize()

    def restore(self) -> None:
        """Return to the size before maximising."""
        if self._window is not None:
            self._window.restore()

    @property
    def is_maximized(self) -> bool:
        """Whether the window fills the work area, as the window system says.

        Asked rather than remembered, so a maximise through the window
        manager's own control is seen too.
        """
        return bool(self._window is not None and self._window.is_maximized)

    def begin_move(self) -> None:
        """Start a drag of the window from the title bar.

        Where the window system places windows itself (Wayland, which will
        not tell a client where its window is), the drag is handed to it
        and the `move_by` calls that follow do nothing. Elsewhere the
        position is read once and every move adds to it: a read straight
        after a move can return the old position while the window manager
        catches up, and a delta landing on a stale base jitters.
        """
        self._move_target = None
        if self._window is None:
            return
        position = self._window.position
        if position is None:
            self._window.drag()
            return
        self._move_target = (int(position[0]), int(position[1]))

    def move_by(self, dx: int, dy: int) -> None:
        """Move the window by a screen-space delta.

        Args:
            dx: Horizontal movement in pixels.
            dy: Vertical movement in pixels.
        """
        if self._window is None or self._move_target is None:
            return
        x, y = self._move_target
        self._move_target = (x + dx, y + dy)
        self._window.set_position(*self._move_target)

    def end_move(self) -> None:
        """Forget the remembered position, so the next drag reads afresh."""
        self._move_target = None

    def request_close(self) -> None:
        """Ask the application to shut down, as the OS close button does.

        Queued rather than closing: a borderless window's close button is
        pressed from inside a frame still being drawn.
        """
        self.post_event(QuitEvent())
