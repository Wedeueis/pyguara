"""A full-viewport color flash that fades out.

The screen-space half of #28's "TintPulse/flash" item. Deliberately not
a per-sprite tint -- `Renderable`/`Sprite` carries no
color field, so flashing one specific sprite (a hit-white-flash on an
enemy) needs a protocol change this does not make. This covers the other
common case: a full-screen flash on taking damage, a white pulse on
level-up. Built on the plain `IRenderer.draw_rect` primitive, so it works
identically on every backend -- unlike `VignetteEffect`, which is
ModernGL-only and has no color parameter at all.
"""

from __future__ import annotations

from pyguara.common.types import Color, Rect
from pyguara.graphics.protocols import IRenderer


class ScreenFlash:
    """One active flash at a time; triggering again replaces it, not stacks."""

    def __init__(self) -> None:
        """Start idle -- `render()` draws nothing until `trigger()` is called."""
        self._color: Color | None = None
        self._elapsed = 0.0
        self._duration = 0.0

    @property
    def is_active(self) -> bool:
        """Whether a flash is currently fading, for a caller that wants to check."""
        return self._color is not None

    def trigger(self, color: Color, duration: float = 0.15) -> None:
        """Start (or restart) a flash.

        Args:
            color: The flash color; its own alpha is the peak opacity the
                fade starts from (255 for a fully opaque flash).
            duration: Seconds to fade from `color` to fully transparent.
        """
        self._color = color
        self._elapsed = 0.0
        self._duration = duration

    def update(self, dt: float) -> None:
        """Advance the fade; clears the flash once `duration` has elapsed."""
        if self._color is None:
            return
        self._elapsed += dt
        if self._elapsed >= self._duration:
            self._color = None

    def render(self, backend: IRenderer, viewport: Rect) -> None:
        """Draw the current fade state as one full-viewport rectangle.

        A no-op while idle.

        Args:
            backend: Target renderer.
            viewport: The screen-space region to cover -- normally the
                whole window, but a split-screen view would pass its own
                pane.
        """
        if self._color is None:
            return
        fraction_remaining = (
            0.0
            if self._duration <= 0
            else max(0.0, 1.0 - self._elapsed / self._duration)
        )
        faded = Color(
            self._color.r,
            self._color.g,
            self._color.b,
            int(self._color.a * fraction_remaining),
        )
        backend.draw_rect(viewport, faded)
