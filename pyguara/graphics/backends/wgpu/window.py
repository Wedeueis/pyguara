"""The window for the wgpu backend.

SDL, through pygame, still opens the window and delivers input: that half
of the platform stack is a later workstream. What changes is who draws.
The window's native handle -- an HWND, an X11 window, a Wayland surface --
is handed to wgpu, which presents to it directly, and pygame's own display
surface is never drawn to or flipped.

**There is a fallback, and it is slow.** If no handle is available (SDL's
`dummy` driver, as in a test or a headless capture) or wgpu cannot draw to
the window, the frame is rendered offscreen, copied out, and blitted to
the pygame surface. That costs a readback per frame -- about 19 ms on the
machine this was written on -- and exists so the renderer can be checked
without a screen and so a frame can be captured. `frame.gpu.has_surface`
says which path is in use, and the boot log does too.
"""

from __future__ import annotations

import ctypes
import dataclasses
from typing import Any

import pygame

from pyguara.common.types import Color
from pyguara.config.types import WindowConfig
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.wgpu.frame import GpuFrame


def _pointer(capsule: Any) -> int:
    """Return the address a PyCapsule from `get_wm_info()` holds."""
    api = ctypes.pythonapi
    api.PyCapsule_GetName.restype = ctypes.c_char_p
    api.PyCapsule_GetName.argtypes = [ctypes.py_object]
    api.PyCapsule_GetPointer.restype = ctypes.c_void_p
    api.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    return int(api.PyCapsule_GetPointer(capsule, api.PyCapsule_GetName(capsule)) or 0)


def native_window() -> tuple[str, int, int] | None:
    """Name the open pygame window as `NativeGpu.for_window` wants it.

    Returns:
        `(kind, window, display)`, or None when SDL has no native window
        to offer -- the `dummy` driver, or a platform not handled yet
        (macOS, where wgpu needs the window's view rather than the window).
    """
    try:
        driver = pygame.display.get_driver()
        info = pygame.display.get_wm_info()
    except pygame.error:
        return None
    # By SDL's driver name, never by which keys are present: on X11
    # pygame's dictionary also carries `surface` and `shell_surface`, the
    # Wayland fields of the same C union, holding whatever bytes were
    # there. Reading them as a Wayland surface crashed the process.
    if driver == "windows":
        window = info.get("window")
        return ("win32", int(window), 0) if window else None
    if driver == "x11" and info.get("window") and "display" in info:
        return ("x11", int(info["window"]), _pointer(info["display"]))
    if driver == "wayland" and "surface" in info and "display" in info:
        return ("wayland", _pointer(info["surface"]), _pointer(info["display"]))
    return None


class WgpuWindow(PygameWindow):
    """A pygame window whose pixels come from a wgpu frame.

    Attributes:
        frame: The frame the renderers draw into. None until `open()`.
    """

    def __init__(self) -> None:
        """Initialise with no window and no device."""
        super().__init__()
        self.frame: GpuFrame | None = None

    def open(self, config: WindowConfig) -> bool:
        """Create the window, then the device that draws for it.

        Args:
            config: Window settings to open with.

        Returns:
            True once both exist.
        """
        # SDL is asked for no vsync of its own: it would wait on a buffer
        # this backend never flips, and on some drivers asking promotes the
        # window to an OpenGL surface (see `PygameWindow`). wgpu's swapchain
        # does the waiting.
        super().open(dataclasses.replace(config, vsync=False))
        self.frame = GpuFrame(self.width, self.height, native_window(), config.vsync)
        return True

    def clear(self, color: Color | None = None) -> None:
        """Start the frame from a solid colour."""
        if self.frame is None:
            return
        fill = color if color is not None else self._default_color
        self.frame.gpu.clear(fill.r, fill.g, fill.b, 255)

    def present(self) -> None:
        """Render the frame and show it."""
        if self.frame is None:
            return
        gpu: Any = self.frame.gpu
        gpu.end_frame()
        self.frame.after_frame()
        if gpu.has_surface:
            gpu.present()
        else:
            self._show(gpu)

    def _show(self, gpu: Any) -> None:
        """Copy the rendered frame onto the window's surface: the slow path."""
        if self._screen is None:
            return
        image = pygame.image.frombuffer(
            gpu.read_pixels(), (gpu.width, gpu.height), "RGBA"
        )
        self._screen.blit(image, (0, 0))
        pygame.display.flip()

    def close(self) -> None:
        """Release the device, then the window."""
        self.frame = None
        super().close()
