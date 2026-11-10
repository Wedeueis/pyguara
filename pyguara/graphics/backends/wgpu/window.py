"""The window for the wgpu backend.

**Stage A: the window is still pygame's, and it shows a copy.** SDL opens
the window and delivers input exactly as it does for the pygame backend.
The frame is rendered offscreen by wgpu, copied out, and blitted to the
window's surface. That copy is a cost a real swapchain does not have, and
it is here on purpose: it lets the whole renderer be built and checked --
headless, in a test, against the pygame backend's own pixels -- before
any platform's window handle is involved. Stage B draws straight to the
window and deletes `_show`.
"""

from __future__ import annotations

from typing import Any

import pygame

from pyguara.common.types import Color
from pyguara.config.types import WindowConfig
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.wgpu.frame import GpuFrame


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
        super().open(config)
        self.frame = GpuFrame(self.width, self.height)
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
        self._show(gpu)

    def _show(self, gpu: Any) -> None:
        """Copy the rendered frame onto the window's surface."""
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
