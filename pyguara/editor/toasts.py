"""Short-lived messages, shown over the editor and then forgotten.

The gap this fills: an operation that fails writes a log line and nothing
else. A person clicking *Add Component > Sprite*, or typing a value the
component refuses, sees the menu close and nothing happen -- which is
indistinguishable from a control that does not work, and is exactly how
it was reported.

Deliberately not a dialog. An authoring tool interrupts for a decision,
not for a result: a toast says what happened, stays long enough to read,
and goes away without being dismissed. Failures stay longer than
successes, because a failure is the one worth reading twice.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from imgui_bundle import imgui

PADDING = 12.0
"""Gap from the window's bottom-right corner, unscaled."""

MAX_VISIBLE = 4
"""How many to show at once. Beyond this the oldest are dropped: a stack
tall enough to cover the Inspector is worse than a missed message, and
the journal has every one of them anyway."""


class Level(Enum):
    """How much a message wants to be noticed."""

    INFO = "info"
    """Something worked, and saying so is useful -- a scene saved."""

    WARNING = "warning"
    """Something was refused, or did less than asked."""

    ERROR = "error"
    """Something failed outright."""


_LIFETIMES: dict[Level, float] = {
    Level.INFO: 2.5,
    Level.WARNING: 5.0,
    Level.ERROR: 8.0,
}
"""Seconds each level stays up. A failure outlives a success, because it
is the one that has to survive the glance that missed it."""

_COLOURS: dict[Level, tuple[float, float, float]] = {
    Level.INFO: (0.70, 0.72, 0.76),
    Level.WARNING: (0.95, 0.72, 0.30),
    Level.ERROR: (0.93, 0.44, 0.42),
}


@dataclass
class Toast:
    """One message and when it was raised.

    Attributes:
        message: What to show.
        level: How much it wants to be noticed.
        raised_at: When it was pushed, on the monotonic clock.
    """

    message: str
    level: Level = Level.INFO
    raised_at: float = field(default_factory=time.monotonic)

    def age(self, now: float) -> float:
        """Return how long it has been up.

        Args:
            now: The current monotonic time.

        Returns:
            Seconds since it was raised.
        """
        return now - self.raised_at

    def expired(self, now: float) -> bool:
        """Whether it has been up long enough to drop.

        Args:
            now: The current monotonic time.

        Returns:
            True when its time is up.
        """
        return self.age(now) >= _LIFETIMES[self.level]


class ToastStack:
    """Holds the messages waiting to be shown, and draws them."""

    def __init__(self) -> None:
        """Start with nothing to say."""
        self._toasts: list[Toast] = []

    @property
    def toasts(self) -> tuple[Toast, ...]:
        """The messages currently held, oldest first."""
        return tuple(self._toasts)

    def push(self, message: str, level: Level = Level.INFO) -> None:
        """Add a message.

        Args:
            message: What to show. Long ones are wrapped, not truncated:
                an operation's error names the correction, and cutting it
                off removes the useful half.
            level: How much it wants to be noticed.
        """
        self._toasts.append(Toast(message, level))
        while len(self._toasts) > MAX_VISIBLE:
            self._toasts.pop(0)

    def info(self, message: str) -> None:
        """Push an informational message.

        Args:
            message: What to show.
        """
        self.push(message, Level.INFO)

    def warn(self, message: str) -> None:
        """Push a warning.

        Args:
            message: What to show.
        """
        self.push(message, Level.WARNING)

    def error(self, message: str) -> None:
        """Push a failure.

        Args:
            message: What to show.
        """
        self.push(message, Level.ERROR)

    def clear(self) -> None:
        """Drop everything held."""
        self._toasts.clear()

    def prune(self, now: float | None = None) -> None:
        """Drop whatever has been up long enough.

        Args:
            now: The current monotonic time, for a test that wants to
                control it.
        """
        moment = time.monotonic() if now is None else now
        self._toasts = [t for t in self._toasts if not t.expired(moment)]

    def draw(self, width: float, height: float) -> None:
        """Draw the stack in the window's bottom-right corner.

        Args:
            width: The window width in pixels.
            height: The window height in pixels.
        """
        self.prune()
        if not self._toasts:
            return

        scale = max(imgui.get_style().font_scale_main, 1.0)
        padding = PADDING * scale
        now = time.monotonic()
        offset = 0.0

        for index, toast in enumerate(reversed(self._toasts)):
            # Faded over the last second rather than vanishing, so a
            # message that leaves while being read does not look like a
            # glitch.
            remaining = _LIFETIMES[toast.level] - toast.age(now)
            alpha = min(1.0, max(0.0, remaining))
            colour = _COLOURS[toast.level]

            imgui.set_next_window_bg_alpha(0.92 * alpha)
            imgui.set_next_window_pos(
                imgui.ImVec2(width - padding, height - padding - offset),
                imgui.Cond_.always.value,
                imgui.ImVec2(1.0, 1.0),
            )
            imgui.set_next_window_size_constraints(
                imgui.ImVec2(200.0 * scale, 0.0), imgui.ImVec2(420.0 * scale, 400.0)
            )
            imgui.push_style_var(imgui.StyleVar_.alpha, alpha)
            imgui.begin(
                f"##toast{index}",
                None,
                imgui.WindowFlags_.no_decoration.value
                | imgui.WindowFlags_.no_inputs.value
                | imgui.WindowFlags_.no_nav.value
                | imgui.WindowFlags_.no_focus_on_appearing.value
                | imgui.WindowFlags_.no_saved_settings.value
                | imgui.WindowFlags_.no_docking.value
                | imgui.WindowFlags_.always_auto_resize.value,
            )
            try:
                imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(*colour, alpha))
                imgui.text_wrapped(toast.message)
                imgui.pop_style_color()
                offset += imgui.get_window_size().y + padding * 0.5
            finally:
                imgui.end()
                imgui.pop_style_var()
