"""Pause, step, slow down, speed up and seek a replay while it plays.

`Application.load_replay()` creates one `ReplayControls`, reachable as
`Application.replay_controls`. A replay viewer sets `visible`, which draws
the scrub bar along the bottom of the screen and lets the keys in `KEYS`
drive it; a game can call the methods from its own buttons instead.

Seeking back replays the recording from the start, since a replay holds
input rather than world states. That needs a way back to the world the
recording began in, so it works only when `load_replay()` was given
`restart`.
"""

from __future__ import annotations

from bisect import bisect_right

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.input import keys
from pyguara.replay.player import ReplayPlayer

__all__ = ["KEYS", "SPEEDS", "ReplayControls", "draw_replay_controls"]

SPEEDS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
"""The playback speeds, slowest first. A speed is recorded frames per frame."""

SKIP_SECONDS = 5.0
"""How far the arrow keys seek."""

SEEK_FRAMES_PER_STEP = 240
"""Recorded frames simulated per displayed frame while seeking, so a long
seek shows its progress instead of freezing the window."""

KEYS: dict[int, str] = {
    keys.SPACE: "pause or resume",
    keys.PERIOD: "step one frame",
    keys.L_BRACKET: "slower",
    keys.R_BRACKET: "faster",
    keys.LEFT: f"back {SKIP_SECONDS:g} s",
    keys.RIGHT: f"forward {SKIP_SECONDS:g} s",
    keys.HOME: "from the start",
}
"""The keys `ReplayControls.handle_key` answers to, and what each does."""


class ReplayControls:
    """How a loaded replay plays: paused or not, how fast, and where to seek.

    The application asks `frames_due()` once a frame for how many recorded
    frames to simulate, and `take_seek()` for a frame to jump to.

    Attributes:
        visible: Whether the scrub bar is drawn and the keys answered.
    """

    def __init__(self, player: ReplayPlayer, *, can_rewind: bool) -> None:
        """Control `player`, playing at normal speed.

        Args:
            player: The replay being played.
            can_rewind: Whether seeking back is possible, which needs a way
                to put the world back where the recording began.
        """
        self.visible = False
        self._player = player
        self._can_rewind = can_rewind
        self._paused = False
        self._speed_index = SPEEDS.index(1.0)
        self._owed = 0.0
        self._step = False
        self._seek: int | None = None
        self._timestamps = player.timestamps()

    @property
    def paused(self) -> bool:
        """Whether playback is held on the current frame."""
        return self._paused

    @property
    def speed(self) -> float:
        """Recorded frames simulated per displayed frame, one of `SPEEDS`."""
        return SPEEDS[self._speed_index]

    @property
    def frame(self) -> int:
        """How many recorded frames have been played."""
        return self._player.current_frame

    @property
    def total_frames(self) -> int:
        """How many frames the replay has."""
        return self._player.total_frames

    @property
    def can_rewind(self) -> bool:
        """Whether `seek()` can go back."""
        return self._can_rewind

    @property
    def seeking(self) -> bool:
        """Whether a seek is still being simulated."""
        return self._seek is not None

    @property
    def finished(self) -> bool:
        """Whether every recorded frame has been played."""
        return self._player.is_finished()

    def time_at(self, frame: int) -> float:
        """Return how far into the recording, in seconds, `frame` begins."""
        if not self._timestamps:
            return 0.0
        if frame >= len(self._timestamps):
            return self._player.duration
        return self._timestamps[max(frame, 0)]

    def frame_at(self, seconds: float) -> int:
        """Return the frame playing `seconds` into the recording."""
        return max(bisect_right(self._timestamps, seconds) - 1, 0)

    def pause(self) -> None:
        """Hold playback on the current frame."""
        self._paused = True

    def resume(self) -> None:
        """Play on from the current frame."""
        self._paused = False
        self._owed = 0.0

    def toggle_pause(self) -> None:
        """Pause if playing, resume if paused."""
        if self._paused:
            self.resume()
        else:
            self.pause()

    def step(self) -> None:
        """Play exactly one frame, then hold. Pauses playback first."""
        self._paused = True
        self._step = True

    def faster(self) -> None:
        """Move to the next speed up, if there is one."""
        self._speed_index = min(self._speed_index + 1, len(SPEEDS) - 1)

    def slower(self) -> None:
        """Move to the next speed down, if there is one."""
        self._speed_index = max(self._speed_index - 1, 0)

    def seek(self, frame: int) -> None:
        """Jump to `frame`, simulating every frame before it.

        Clamped to the replay. The seek is carried out over the next frames,
        `SEEK_FRAMES_PER_STEP` at a time, and holds playback once there.

        Raises:
            RuntimeError: If `frame` is behind the current one and the replay
                was loaded without `restart`.
        """
        target = min(max(frame, 0), self.total_frames)
        if target < self.frame and not self._can_rewind:
            raise RuntimeError(
                "Seeking back replays from the start, which needs "
                "`load_replay(path, restart=...)` to put the world back where "
                "the recording began."
            )
        self._seek = target
        self._paused = True
        self._step = False

    def skip(self, seconds: float) -> None:
        """Seek `seconds` forward, or back if negative."""
        self.seek(self.frame_at(self.time_at(self.frame) + seconds))

    def handle_key(self, key_code: int) -> bool:
        """Act on one of `KEYS` while visible.

        Returns:
            Whether the key was used. A seek back the replay cannot make is
            not used, so the key does nothing rather than raising.
        """
        if not self.visible or key_code not in KEYS:
            return False
        if key_code == keys.SPACE:
            self.toggle_pause()
        elif key_code == keys.PERIOD:
            self.step()
        elif key_code == keys.L_BRACKET:
            self.slower()
        elif key_code == keys.R_BRACKET:
            self.faster()
        elif key_code in (keys.LEFT, keys.HOME) and not self._can_rewind:
            return False
        elif key_code == keys.LEFT:
            self.skip(-SKIP_SECONDS)
        elif key_code == keys.RIGHT:
            self.skip(SKIP_SECONDS)
        else:
            self.seek(0)
        return True

    def take_seek(self) -> int | None:
        """Return the frame a pending seek is going to, or None.

        The application calls this once a frame, and `seek_done()` on arrival.
        """
        return self._seek

    def seek_done(self) -> None:
        """Mark the pending seek as reached."""
        self._seek = None
        self._owed = 0.0

    def frames_due(self) -> int:
        """Return how many recorded frames to simulate this displayed frame.

        Zero while paused, except straight after `step()`. At a speed below
        one the fraction carries over, so 0.25 plays every fourth frame.
        """
        if self._step:
            self._step = False
            return 1
        if self._paused:
            return 0
        self._owed += self.speed
        due = int(self._owed)
        self._owed -= due
        return due


_PANEL = Color(0, 0, 0, 200)
_TRACK = Color(70, 75, 85)
_PLAYED = Color(110, 190, 255)
_TEXT = Color(225, 230, 235)
_DIM = Color(140, 150, 160)
_HEIGHT = 46
_PADDING = 8
_TRACK_HEIGHT = 6
_TEXT_SIZE = 14


def _clock(seconds: float) -> str:
    minutes, rest = divmod(max(seconds, 0.0), 60.0)
    return f"{int(minutes)}:{rest:04.1f}"


def status_text(controls: ReplayControls) -> str:
    """Return the scrub bar's status line: state, speed, frame and time."""
    if controls.seeking:
        state = "seeking"
    elif controls.finished:
        state = "ended"
    elif controls.paused:
        state = "paused"
    else:
        state = "playing"
    total = controls.total_frames
    now = _clock(controls.time_at(controls.frame))
    end = _clock(controls.time_at(total))
    return (
        f"{state}  {controls.speed:g}x  frame {controls.frame}/{total}  {now} / {end}"
    )


def draw_replay_controls(
    controls: ReplayControls, renderer: UIRenderer, width: int, height: int
) -> None:
    """Draw the scrub bar along the bottom of the screen, if visible.

    Args:
        controls: The replay's controls.
        renderer: The UI renderer to draw with.
        width: The screen's width, in pixels.
        height: The screen's height, in pixels.
    """
    if not controls.visible:
        return
    top = height - _HEIGHT
    renderer.draw_rect(Rect(0, top, width, _HEIGHT), _PANEL, 0)

    track_width = width - 2 * _PADDING
    track = Rect(_PADDING, top + _PADDING, track_width, _TRACK_HEIGHT)
    renderer.draw_rect(track, _TRACK, 0)
    total = controls.total_frames
    if total > 0:
        played = round(track_width * controls.frame / total)
        if played > 0:
            renderer.draw_rect(
                Rect(_PADDING, top + _PADDING, played, _TRACK_HEIGHT),
                _PLAYED,
                0,
            )

    text_y = top + _PADDING + _TRACK_HEIGHT + 8
    renderer.draw_text(
        status_text(controls),
        Vector2(_PADDING, text_y),
        _TEXT,
        size=_TEXT_SIZE,
    )
    hint = "space pause  . step  [ ] speed"
    if controls.can_rewind:
        hint += "  arrows seek  home start"
    else:
        hint += "  right seek"
    renderer.draw_text(hint, Vector2(width // 2, text_y), _DIM, size=_TEXT_SIZE)
