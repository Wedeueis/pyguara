"""Replay player for playback of recorded input.

Plays back recorded input events for deterministic replay.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from pyguara.replay.types import (
    InputFrame,
    RecordedInputEvent,
    ReplayData,
    ReplayState,
)

logger = logging.getLogger(__name__)

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

    def __init__(self, replay_data: Optional[ReplayData] = None) -> None:
        """Initialize the player.

        Args:
            replay_data: Optional replay data to load immediately.
        """
        self._data: Optional[ReplayData] = replay_data
        self._state = ReplayState.IDLE
        self._current_frame_index: int = 0
        self._event_handlers: List[EventCallback] = []
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

    def get_frame_events(self, frame_id: int) -> List[RecordedInputEvent]:
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

    def advance_frame(self) -> Optional[InputFrame]:
        """Advance to the next frame and return its data.

        Returns:
            The next frame, or None if at end or not playing.
        """
        if self._state != ReplayState.PLAYING or not self._data:
            return None

        if self._current_frame_index >= len(self._data.frames):
            # End of replay
            self._state = ReplayState.IDLE
            logger.info("Replay playback complete")
            return None

        frame = self._data.frames[self._current_frame_index]
        self._current_frame_index += 1

        # Dispatch events to handlers
        for event in frame.events:
            for handler in self._event_handlers:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")

        # Check if we've reached the end
        if self._current_frame_index >= len(self._data.frames):
            self._state = ReplayState.IDLE
            logger.info("Replay playback complete")

        return frame

    def update(self, delta_time: float) -> List[InputFrame]:
        """Update playback based on elapsed time.

        This method should be called each game frame. It returns all frames
        that should be processed based on the elapsed time.

        Args:
            delta_time: Time since last update in seconds.

        Returns:
            List of frames to process this update.
        """
        if self._state != ReplayState.PLAYING or not self._data:
            return []

        # Apply playback speed
        adjusted_dt = delta_time * self._playback_speed
        self._elapsed_time += adjusted_dt

        frames_to_process: List[InputFrame] = []

        # Process all frames up to current time
        while self._current_frame_index < len(self._data.frames):
            frame = self._data.frames[self._current_frame_index]

            if frame.timestamp <= self._elapsed_time:
                frames_to_process.append(frame)
                self._current_frame_index += 1

                # Dispatch events
                for event in frame.events:
                    for handler in self._event_handlers:
                        try:
                            handler(event)
                        except Exception as e:
                            logger.error(f"Event handler error: {e}")
            else:
                break

        # Check if replay finished
        if self._current_frame_index >= len(self._data.frames):
            self._state = ReplayState.IDLE
            logger.info("Replay playback complete")

        return frames_to_process

    def get_current_frame_data(self) -> Optional[InputFrame]:
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
