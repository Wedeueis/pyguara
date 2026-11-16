"""Where a frame's time goes, measured by the frame loop itself.

`FrameProfiler` records how long each phase of `Application.step()` took
over the last couple of seconds, and `draw_frame_profile()` shows it through
the `UIRenderer`. It needs no developer tooling, so it works in a shipped
build: `debug.enable_profiler` in the game's config turns it on.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer

PHASES: tuple[str, ...] = ("wait", "input", "events", "fixed", "update", "render")
"""The phases of a frame, in the order `Application.step()` runs them.

`wait` is the clock holding the frame to `display.fps_target`. It is idle
time, not work, and is listed so the other five add up to what the game
costs and all six add up to the frame.
"""

HISTORY_FRAMES = 120

REFRESH_FRAMES = 15
"""How many frames the overlay shows the same numbers for. Summarising
every frame costs more than recording it, and figures that change sixty
times a second cannot be read."""

_PANEL = Color(0, 0, 0, 200)
_TEXT = Color(225, 230, 235)
_DIM = Color(140, 150, 160)
_OVER_BUDGET = Color(255, 110, 90)
_LINE_HEIGHT = 18
_TEXT_SIZE = 14
_PADDING = 8
_PANEL_WIDTH = 270
_COLUMNS = (0, 80, 170)
"""Where a row's label, mean and maximum start, from the row's left edge."""


@dataclass(frozen=True)
class PhaseStats:
    """One phase over the recorded frames.

    Attributes:
        name: The phase, one of `PHASES`.
        mean_ms: Its mean duration, in milliseconds.
        max_ms: Its longest duration, in milliseconds.
    """

    name: str
    mean_ms: float
    max_ms: float


@dataclass(frozen=True)
class FrameStats:
    """A summary of the recorded frames.

    Attributes:
        frames: How many frames the summary covers.
        phases: One entry per phase, in `PHASES` order.
        frame_mean_ms: The mean whole frame, `wait` included.
        frame_max_ms: The longest whole frame.
        work_mean_ms: The mean frame without `wait`: what the game costs.
        fixed_steps_mean: Fixed updates per frame, on average.
    """

    frames: int
    phases: tuple[PhaseStats, ...]
    frame_mean_ms: float
    frame_max_ms: float
    work_mean_ms: float
    fixed_steps_mean: float

    @property
    def fps(self) -> float:
        """Frames per second, from the mean whole frame."""
        if self.frame_mean_ms <= 0:
            return 0.0
        return 1000.0 / self.frame_mean_ms


class FrameProfiler:
    """Records how long each phase of a frame took.

    The frame loop calls `begin_frame()`, then `mark()` as each phase ends,
    then `end_frame()`. Only the last `HISTORY_FRAMES` frames are kept.

    Attributes:
        visible: Whether the application draws the overlay. Recording goes
            on either way, so a game can bind a key to this.
    """

    def __init__(self, visible: bool = True) -> None:
        """Start with no frames recorded.

        Args:
            visible: Whether the overlay is drawn.
        """
        self.visible = visible
        self._history: dict[str, deque[float]] = {
            phase: deque(maxlen=HISTORY_FRAMES) for phase in PHASES
        }
        self._fixed_steps: deque[int] = deque(maxlen=HISTORY_FRAMES)
        self._current: dict[str, float] = dict.fromkeys(PHASES, 0.0)
        self._last_mark = 0.0
        self._frames_recorded = 0
        self._shown: tuple[int, FrameStats] | None = None
        self._shown_rows: list[tuple[str, str, str]] = []

    def begin_frame(self) -> None:
        """Start timing a frame."""
        for phase in PHASES:
            self._current[phase] = 0.0
        self._last_mark = time.perf_counter()

    def mark(self, phase: str) -> None:
        """Charge the time since the last mark to `phase`.

        Args:
            phase: One of `PHASES`.

        Raises:
            KeyError: If `phase` is not one of `PHASES`.
        """
        now = time.perf_counter()
        if phase not in self._current:
            raise KeyError(f"{phase!r} is not a frame phase; expected one of {PHASES}")
        self._current[phase] += now - self._last_mark
        self._last_mark = now

    def end_frame(self, fixed_steps: int) -> None:
        """Keep the frame just timed.

        Args:
            fixed_steps: How many fixed updates the frame ran.
        """
        for phase in PHASES:
            self._history[phase].append(self._current[phase])
        self._fixed_steps.append(fixed_steps)
        self._frames_recorded += 1

    def shown_stats(self) -> FrameStats | None:
        """Return the summary the overlay shows, refreshed now and then.

        The same summary for `REFRESH_FRAMES` frames at a time; `stats()`
        is the one that is always current.

        Returns:
            The summary, or None before the first frame has ended.
        """
        window = self._frames_recorded // REFRESH_FRAMES
        if self._shown is None or self._shown[0] != window:
            stats = self.stats()
            if stats is None:
                return None
            self._shown = (window, stats)
            self._shown_rows = profile_rows(stats)
        return self._shown[1]

    def shown_rows(self) -> list[tuple[str, str, str]]:
        """Return `shown_stats()` as the overlay's rows, formatted once.

        Returns:
            The rows, or an empty list before the first frame has ended.
        """
        if self.shown_stats() is None:
            return []
        return self._shown_rows

    def stats(self) -> FrameStats | None:
        """Summarise the recorded frames.

        Returns:
            The summary, or None before the first frame has ended.
        """
        frames = len(self._fixed_steps)
        if frames == 0:
            return None

        phases = tuple(
            PhaseStats(
                phase,
                1000.0 * sum(self._history[phase]) / frames,
                1000.0 * max(self._history[phase]),
            )
            for phase in PHASES
        )
        totals = [
            sum(self._history[phase][index] for phase in PHASES)
            for index in range(frames)
        ]
        frame_mean_ms = 1000.0 * sum(totals) / frames
        wait_mean_ms = phases[PHASES.index("wait")].mean_ms
        return FrameStats(
            frames=frames,
            phases=phases,
            frame_mean_ms=frame_mean_ms,
            frame_max_ms=1000.0 * max(totals),
            work_mean_ms=frame_mean_ms - wait_mean_ms,
            fixed_steps_mean=sum(self._fixed_steps) / frames,
        )


def profile_rows(stats: FrameStats) -> list[tuple[str, str, str]]:
    """Format a summary as the rows the overlay shows.

    Args:
        stats: The summary to format.

    Returns:
        Rows of label, mean and maximum: the whole frame, the work in it,
        each phase, and the fixed steps per frame.
    """
    rows = [
        (
            f"{stats.fps:.0f} fps",
            f"{stats.frame_mean_ms:.2f} ms",
            f"max {stats.frame_max_ms:.2f}",
        ),
        ("work", f"{stats.work_mean_ms:.2f} ms", ""),
    ]
    rows.extend(
        (phase.name, f"{phase.mean_ms:.2f} ms", f"max {phase.max_ms:.2f}")
        for phase in stats.phases
    )
    rows.append(("fixed steps", f"{stats.fixed_steps_mean:.2f}", "per frame"))
    return rows


def draw_frame_profile(
    profiler: FrameProfiler,
    renderer: UIRenderer,
    budget_ms: float | None = None,
) -> None:
    """Draw the profiler's overlay in the top-left corner.

    Draws nothing while the profiler is hidden or has no frame yet.

    Args:
        profiler: The profiler to show.
        renderer: The UI renderer to draw with.
        budget_ms: The frame time the game is aiming for. The work row is
            highlighted when the mean exceeds it.
    """
    if not profiler.visible:
        return
    stats = profiler.shown_stats()
    if stats is None:
        return

    rows = profiler.shown_rows()
    height = _PADDING * 2 + _LINE_HEIGHT * len(rows)
    renderer.draw_rect(Rect(_PADDING, _PADDING, _PANEL_WIDTH, height), _PANEL, 0)

    over_budget = budget_ms is not None and stats.work_mean_ms > budget_ms
    for index, row in enumerate(rows):
        if row[0] == "work" and over_budget:
            colour = _OVER_BUDGET
        elif row[0] == "wait":
            colour = _DIM
        else:
            colour = _TEXT
        top = _PADDING * 2 + index * _LINE_HEIGHT
        for offset, cell in zip(_COLUMNS, row, strict=True):
            if cell:
                renderer.draw_text(
                    cell, Vector2(_PADDING * 2 + offset, top), colour, size=_TEXT_SIZE
                )
