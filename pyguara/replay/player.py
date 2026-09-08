"""Replay player for playback of recorded input.

Plays back recorded input events for deterministic replay.
"""

from __future__ import annotations

from collections.abc import Callable

from pyguara.log import get_logger
from pyguara.replay.types import (
    InputFrame,
    RecordedInputEvent,
    ReplayData,
    ReplayState,
)

logger = get_logger(__name__)

# Type alias for event callback
EventCallback = Callable[[RecordedInputEvent], None]


class ReplayPlayer:
    """Plays back recorded input events.

    Feeds recorded input events to the game at the correct frame timing
    to reproduce gameplay deterministically.

    Example:
        player = ReplayPlayer(replay_data)
        player.add_event_handler(handle_event)
        player.start_playback()

        # In game loop
        events = player.get_frame_events(frame_id)
        for event in events:
            process_event(event)
    """

    def __init__(self, replay_data: ReplayData | None = None) -> None:
        """Initialize the player.

        Args:
            replay_data: Optional replay data to load immediately.
        """
        self._data: ReplayData | None = replay_data
        self._state = ReplayState.IDLE
        self._current_frame_index: int = 0
        self._event_handlers: list[EventCallback] = []
        self._playback_speed: float = 1.0
        self._elapsed_time: float = 0.0

    @property
    def state(self) -> ReplayState:
        """Get current player state."""
        return self._state

    @property
    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self._state == ReplayState.PLAYING

    @property
    def is_paused(self) -> bool:
        """Check if playback is paused."""
        return self._state == ReplayState.PAUSED

    @property
    def current_frame(self) -> int:
        """Get current playback frame index."""
        return self._current_frame_index

    @property
    def total_frames(self) -> int:
        """Get total number of frames in replay."""
        if self._data:
            return len(self._data.frames)
        return 0

    @property
    def progress(self) -> float:
        """Return playback progress as a value from 0.0 to 1.0."""
        if not self._data or not self._data.frames:
            return 0.0
        return self._current_frame_index / len(self._data.frames)

    @property
    def seed(self) -> int:
        """Get the seed from the replay data."""
        if self._data:
            return self._data.metadata.seed
        return 0

    @property
    def playback_speed(self) -> float:
        """Get current playback speed multiplier."""
        return self._playback_speed

    @playback_speed.setter
    def playback_speed(self, value: float) -> None:
        """Set playback speed multiplier."""
        self._playback_speed = max(0.1, min(10.0, value))

    def load(self, replay_data: ReplayData) -> None:
        """Load replay data for playback.

        Args:
            replay_data: The replay data to play.
        """
        self._data = replay_data
        self._current_frame_index = 0
        self._elapsed_time = 0.0

        logger.info(
            f"Loaded replay: {replay_data.metadata.frame_count} frames, "
            f"seed={replay_data.metadata.seed}"
        )

    def add_event_handler(self, handler: EventCallback) -> None:
        """Add a callback for replay events.

        Args:
            handler: Function to call for each event during playback.
        """
        self._event_handlers.append(handler)

    def remove_event_handler(self, handler: EventCallback) -> None:
        """Remove an event handler.

        Args:
            handler: Handler to remove.
        """
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)

    def start_playback(self) -> bool:
        """Start playback from the beginning.

        Returns:
            True if playback started, False if no data loaded.
        """
        if not self._data:
            logger.error("No replay data loaded")
            return False

        self._current_frame_index = 0
        self._elapsed_time = 0.0
        self._state = ReplayState.PLAYING

        logger.info("Started replay playback")
        return True

    def stop_playback(self) -> None:
        """Stop playback."""
        self._state = ReplayState.IDLE
        logger.info("Stopped replay playback")

    def pause_playback(self) -> None:
        """Pause playback."""
        if self._state == ReplayState.PLAYING:
            self._state = ReplayState.PAUSED
            logger.debug("Paused replay playback")

    def resume_playback(self) -> None:
        """Resume paused playback."""
        if self._state == ReplayState.PAUSED:
            self._state = ReplayState.PLAYING
            logger.debug("Resumed replay playback")

    def seek_to_frame(self, frame_index: int) -> bool:
        """Seek to a specific frame.

        Args:
            frame_index: Frame index to seek to.

        Returns:
            True if seek successful.
        """
        if not self._data:
            return False

        if 0 <= frame_index < len(self._data.frames):
            self._current_frame_index = frame_index
            if self._data.frames:
                self._elapsed_time = self._data.frames[frame_index].timestamp
            return True

        return False

    def get_frame_events(self, frame_id: int) -> list[RecordedInputEvent]:
        """Get events for a specific frame by ID.

        Args:
            frame_id: The frame ID to get events for.

        Returns:
            List of events for that frame, empty if not found.
        """
        if not self._data or self._state not in (
            ReplayState.PLAYING,
            ReplayState.PAUSED,
        ):
            return []

        # Find frame with matching ID
        for frame in self._data.frames:
            if frame.frame_id == frame_id:
                return frame.events

        return []

    def peek_delta(self) -> float | None:
        """Return the ``delta_time`` of the frame :meth:`advance_frame` will emit next.

        Lets a fixed-cadence host loop (``Application``) step its simulation by
        the *recorded* frame duration during playback instead of wall-clock time,
        so anything time-dependent -- the fixed-step accumulator, tweens,
        ``WaitForSeconds`` -- reproduces.

        Returns:
            The next frame's delta, or None if playback is not running or the
            replay is exhausted.
        """
        if self._state != ReplayState.PLAYING or not self._data:
            return None
        if self._current_frame_index >= len(self._data.frames):
            return None
        return self._data.frames[self._current_frame_index].delta_time

    def _emit_frame(self, frame: InputFrame) -> None:
        """Dispatch one frame's events to every registered handler."""
        for event in frame.events:
            for handler in self._event_handlers:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")

    def _finish_if_exhausted(self) -> None:
        """Drop to IDLE once the last frame has been consumed."""
        if self._data and self._current_frame_index >= len(self._data.frames):
            if self._state != ReplayState.IDLE:
                logger.info("Replay playback complete")
            self._state = ReplayState.IDLE

    def advance_frame(self) -> InputFrame | None:
        """Consume exactly one recorded frame and return it.

        The frame-stepping playback model: one call per host frame, paired with
        :meth:`peek_delta` so the host advances its clock by the recorded delta.

        Returns:
            The frame consumed, or None if at end or not playing.
        """
        if self._state != ReplayState.PLAYING or not self._data:
            return None

        if self._current_frame_index >= len(self._data.frames):
            self._finish_if_exhausted()
            return None

        frame = self._data.frames[self._current_frame_index]
        self._current_frame_index += 1
        self._elapsed_time += frame.delta_time
        self._emit_frame(frame)
        self._finish_if_exhausted()
        return frame

    def update(self, delta_time: float) -> list[InputFrame]:
        """Consume every frame whose timestamp has been reached this update.

        The wall-clock playback model, for a host that drives the player from
        its own variable-rate loop rather than one-frame-at-a-time. Honours
        :attr:`playback_speed`. Shares event dispatch and end-of-replay handling
        with :meth:`advance_frame`.

        Args:
            delta_time: Time since the last update, in seconds.

        Returns:
            The frames consumed this update, in order.
        """
        if self._state != ReplayState.PLAYING or not self._data:
            return []

        self._elapsed_time += delta_time * self._playback_speed

        frames_to_process: list[InputFrame] = []
        while self._current_frame_index < len(self._data.frames):
            frame = self._data.frames[self._current_frame_index]
            if frame.timestamp > self._elapsed_time:
                break
            frames_to_process.append(frame)
            self._current_frame_index += 1
            self._emit_frame(frame)

        self._finish_if_exhausted()
        return frames_to_process

    def get_current_frame_data(self) -> InputFrame | None:
        """Get the current frame data without advancing.

        Returns:
            Current frame data, or None if not available.
        """
        if not self._data or self._current_frame_index >= len(self._data.frames):
            return None

        return self._data.frames[self._current_frame_index]

    def is_finished(self) -> bool:
        """Check if playback has finished.

        Returns:
            True if playback is complete.
        """
        if not self._data:
            return True

        return self._current_frame_index >= len(self._data.frames)
