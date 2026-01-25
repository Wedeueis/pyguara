"""Replay recorder for capturing input events.

Records input events frame-by-frame for later playback.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Optional

from pyguara.replay.types import (
    InputEventType,
    InputFrame,
    RecordedInputEvent,
    ReplayData,
    ReplayMetadata,
    ReplayState,
)

logger = logging.getLogger(__name__)


class ReplayRecorder:
    """Records input events for deterministic replay.

    Captures all input events during gameplay and stores them in frames
    that can be saved and played back later.

    Example:
        recorder = ReplayRecorder()
        recorder.start_recording(seed=12345, scene_name="main")

        # In game loop
        recorder.begin_frame(frame_id, timestamp, delta_time)
        recorder.record_event(event)
        recorder.end_frame()

        # When done
        replay_data = recorder.stop_recording()
    """

    # Current replay format version
    FORMAT_VERSION = 1

    def __init__(self, engine_version: str = "0.0.0") -> None:
        """Initialize the recorder.

        Args:
            engine_version: Version string of the engine.
        """
        self._engine_version = engine_version
        self._state = ReplayState.IDLE
        self._data: Optional[ReplayData] = None
        self._current_frame: Optional[InputFrame] = None
        self._start_time: float = 0.0
        self._seed: int = 0

    @property
    def state(self) -> ReplayState:
        """Get current recorder state."""
        return self._state

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._state == ReplayState.RECORDING

    @property
    def frame_count(self) -> int:
        """Get number of recorded frames."""
        if self._data:
            return len(self._data.frames)
        return 0

    @property
    def seed(self) -> int:
        """Get the random seed being used."""
        return self._seed

    def start_recording(
        self,
        seed: Optional[int] = None,
        scene_name: str = "",
        description: str = "",
    ) -> int:
        """Start recording input.

        Args:
            seed: Random seed to use. Generates one if not provided.
            scene_name: Name of the starting scene.
            description: Optional description for the replay.

        Returns:
            The seed being used for this recording.

        Raises:
            RuntimeError: If already recording.
        """
        if self._state == ReplayState.RECORDING:
            raise RuntimeError("Already recording")

        # Generate seed if not provided
        self._seed = seed if seed is not None else random.randint(0, 2**32 - 1)

        # Initialize data structure
        self._data = ReplayData(
            metadata=ReplayMetadata(
                version=self.FORMAT_VERSION,
                seed=self._seed,
                start_scene=scene_name,
                engine_version=self._engine_version,
                recorded_at=datetime.now().isoformat(),
                description=description,
            )
        )

        self._start_time = time.perf_counter()
        self._state = ReplayState.RECORDING

        logger.info(f"Started recording with seed {self._seed}")
        return self._seed

    def stop_recording(self) -> Optional[ReplayData]:
        """Stop recording and return the replay data.

        Returns:
            The recorded replay data, or None if not recording.
        """
        if self._state != ReplayState.RECORDING:
            logger.warning("Not recording, nothing to stop")
            return None

        # Finalize metadata
        if self._data:
            elapsed = time.perf_counter() - self._start_time
            self._data.metadata.duration = elapsed
            self._data.metadata.frame_count = len(self._data.frames)

        self._state = ReplayState.IDLE
        result = self._data
        self._current_frame = None

        logger.info(
            f"Stopped recording: {result.metadata.frame_count if result else 0} frames"
        )
        return result

    def begin_frame(
        self, frame_id: int, timestamp: float, delta_time: float = 0.0
    ) -> None:
        """Begin recording a new frame.

        Must be called at the start of each game frame.

        Args:
            frame_id: Sequential frame number.
            timestamp: Time in seconds from start of recording.
            delta_time: Time since previous frame.
        """
        if self._state != ReplayState.RECORDING:
            return

        self._current_frame = InputFrame(
            frame_id=frame_id,
            timestamp=timestamp,
            delta_time=delta_time,
        )

    def end_frame(self) -> None:
        """End the current frame and save it.

        Must be called at the end of each game frame.
        """
        if self._state != ReplayState.RECORDING or not self._current_frame:
            return

        if self._data:
            self._data.frames.append(self._current_frame)
        self._current_frame = None

    def record_event(self, event: RecordedInputEvent) -> None:
        """Record an input event in the current frame.

        Args:
            event: The input event to record.
        """
        if self._state != ReplayState.RECORDING or not self._current_frame:
            return

        self._current_frame.events.append(event)

    def record_key_down(self, code: int) -> None:
        """Record a keyboard key press.

        Args:
            code: Key code.
        """
        self.record_event(
            RecordedInputEvent(
                event_type=InputEventType.KEY_DOWN,
                device="keyboard",
                code=code,
                value=1.0,
            )
        )

    def record_key_up(self, code: int) -> None:
        """Record a keyboard key release.

        Args:
            code: Key code.
        """
        self.record_event(
            RecordedInputEvent(
                event_type=InputEventType.KEY_UP,
                device="keyboard",
                code=code,
                value=0.0,
            )
        )

    def record_mouse_down(self, button: int, position: tuple[float, float]) -> None:
        """Record a mouse button press.

        Args:
            button: Mouse button code.
            position: Mouse position at time of press.
        """
        self.record_event(
            RecordedInputEvent(
                event_type=InputEventType.MOUSE_DOWN,
                device="mouse",
                code=button,
                value=1.0,
                position=position,
            )
        )

    def record_mouse_up(self, button: int, position: tuple[float, float]) -> None:
        """Record a mouse button release.

        Args:
            button: Mouse button code.
            position: Mouse position at time of release.
        """
        self.record_event(
            RecordedInputEvent(
                event_type=InputEventType.MOUSE_UP,
                device="mouse",
                code=button,
                value=0.0,
                position=position,
            )
        )

    def record_mouse_move(self, position: tuple[float, float]) -> None:
        """Record a mouse movement.

        Args:
            position: New mouse position.
        """
        self.record_event(
            RecordedInputEvent(
                event_type=InputEventType.MOUSE_MOVE,
                device="mouse",
                code=0,
                value=0.0,
                position=position,
            )
        )

    def record_gamepad_button(self, button: int, pressed: bool) -> None:
        """Record a gamepad button event.

        Args:
            button: Button code.
            pressed: True if pressed, False if released.
        """
        self.record_event(
            RecordedInputEvent(
                event_type=(
                    InputEventType.GAMEPAD_BUTTON_DOWN
                    if pressed
                    else InputEventType.GAMEPAD_BUTTON_UP
                ),
                device="gamepad",
                code=button,
                value=1.0 if pressed else 0.0,
            )
        )

    def record_gamepad_axis(self, axis: int, value: float) -> None:
        """Record a gamepad axis movement.

        Args:
            axis: Axis index.
            value: Axis value (-1.0 to 1.0).
        """
        self.record_event(
            RecordedInputEvent(
                event_type=InputEventType.GAMEPAD_AXIS,
                device="gamepad",
                code=axis,
                value=value,
            )
        )

    def record_action(self, action_name: str, value: float = 1.0) -> None:
        """Record a high-level action event.

        Args:
            action_name: Name of the action.
            value: Action value (1.0 for triggered, 0.0 for released).
        """
        self.record_event(
            RecordedInputEvent(
                event_type=InputEventType.ACTION,
                device="action",
                code=0,
                value=value,
                action=action_name,
            )
        )

    def get_data(self) -> Optional[ReplayData]:
        """Get the current replay data without stopping.

        Returns:
            Copy of current replay data, or None if not recording.
        """
        return self._data
