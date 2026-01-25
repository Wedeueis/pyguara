"""Tests for the replay system."""

import tempfile
from pathlib import Path

import pytest

from pyguara.replay.player import ReplayPlayer
from pyguara.replay.recorder import ReplayRecorder
from pyguara.replay.serializer import ReplaySerializer, load_replay, save_replay
from pyguara.replay.types import (
    InputEventType,
    InputFrame,
    RecordedInputEvent,
    ReplayData,
    ReplayMetadata,
)


class TestRecordedInputEvent:
    """Tests for RecordedInputEvent."""

    def test_create_event(self):
        """Test creating an input event."""
        event = RecordedInputEvent(
            event_type=InputEventType.KEY_DOWN,
            device="keyboard",
            code=32,
            value=1.0,
        )
        assert event.event_type == InputEventType.KEY_DOWN
        assert event.device == "keyboard"
        assert event.code == 32
        assert event.value == 1.0

    def test_event_to_dict(self):
        """Test converting event to dict."""
        event = RecordedInputEvent(
            event_type=InputEventType.MOUSE_DOWN,
            device="mouse",
            code=1,
            position=(100.0, 200.0),
        )
        data = event.to_dict()
        assert data["event_type"] == "MOUSE_DOWN"
        assert data["device"] == "mouse"
        assert data["position"] == [100.0, 200.0]

    def test_event_from_dict(self):
        """Test creating event from dict."""
        data = {
            "event_type": "KEY_UP",
            "device": "keyboard",
            "code": 65,
            "value": 0.0,
        }
        event = RecordedInputEvent.from_dict(data)
        assert event.event_type == InputEventType.KEY_UP
        assert event.code == 65


class TestInputFrame:
    """Tests for InputFrame."""

    def test_create_frame(self):
        """Test creating an input frame."""
        frame = InputFrame(frame_id=1, timestamp=0.016, delta_time=0.016)
        assert frame.frame_id == 1
        assert frame.timestamp == 0.016
        assert frame.events == []

    def test_frame_with_events(self):
        """Test frame with events."""
        frame = InputFrame(
            frame_id=1,
            timestamp=0.016,
            events=[
                RecordedInputEvent(
                    event_type=InputEventType.KEY_DOWN,
                    device="keyboard",
                    code=32,
                )
            ],
        )
        assert len(frame.events) == 1

    def test_frame_roundtrip(self):
        """Test frame dict conversion roundtrip."""
        frame = InputFrame(
            frame_id=5,
            timestamp=0.1,
            delta_time=0.016,
            events=[
                RecordedInputEvent(
                    event_type=InputEventType.KEY_DOWN,
                    device="keyboard",
                    code=32,
                )
            ],
        )
        data = frame.to_dict()
        restored = InputFrame.from_dict(data)

        assert restored.frame_id == 5
        assert restored.timestamp == 0.1
        assert len(restored.events) == 1


class TestReplayRecorder:
    """Tests for ReplayRecorder."""

    def test_start_recording(self):
        """Test starting a recording."""
        recorder = ReplayRecorder()
        seed = recorder.start_recording(seed=12345, scene_name="test")

        assert recorder.is_recording
        assert seed == 12345
        assert recorder.seed == 12345

    def test_start_recording_generates_seed(self):
        """Test that seed is generated if not provided."""
        recorder = ReplayRecorder()
        seed = recorder.start_recording()

        assert recorder.is_recording
        assert seed > 0

    def test_stop_recording(self):
        """Test stopping a recording."""
        recorder = ReplayRecorder()
        recorder.start_recording()

        data = recorder.stop_recording()

        assert not recorder.is_recording
        assert data is not None
        assert data.metadata.seed == recorder.seed

    def test_record_frames(self):
        """Test recording input frames."""
        recorder = ReplayRecorder()
        recorder.start_recording(seed=12345)

        # Record frame 1
        recorder.begin_frame(0, 0.0, 0.0)
        recorder.record_key_down(32)
        recorder.end_frame()

        # Record frame 2
        recorder.begin_frame(1, 0.016, 0.016)
        recorder.record_key_up(32)
        recorder.end_frame()

        data = recorder.stop_recording()

        assert data.metadata.frame_count == 2
        assert len(data.frames) == 2
        assert len(data.frames[0].events) == 1
        assert data.frames[0].events[0].event_type == InputEventType.KEY_DOWN

    def test_record_mouse_events(self):
        """Test recording mouse events."""
        recorder = ReplayRecorder()
        recorder.start_recording()

        recorder.begin_frame(0, 0.0, 0.0)
        recorder.record_mouse_down(1, (100.0, 200.0))
        recorder.record_mouse_move((150.0, 250.0))
        recorder.record_mouse_up(1, (150.0, 250.0))
        recorder.end_frame()

        data = recorder.stop_recording()

        assert len(data.frames[0].events) == 3
        assert data.frames[0].events[0].position == (100.0, 200.0)

    def test_record_action(self):
        """Test recording action events."""
        recorder = ReplayRecorder()
        recorder.start_recording()

        recorder.begin_frame(0, 0.0, 0.0)
        recorder.record_action("jump", 1.0)
        recorder.end_frame()

        data = recorder.stop_recording()

        assert data.frames[0].events[0].event_type == InputEventType.ACTION
        assert data.frames[0].events[0].action == "jump"


class TestReplayPlayer:
    """Tests for ReplayPlayer."""

    @pytest.fixture
    def sample_replay(self):
        """Create sample replay data."""
        return ReplayData(
            metadata=ReplayMetadata(version=1, seed=12345, frame_count=3),
            frames=[
                InputFrame(
                    frame_id=0,
                    timestamp=0.0,
                    events=[
                        RecordedInputEvent(
                            event_type=InputEventType.KEY_DOWN,
                            device="keyboard",
                            code=32,
                        )
                    ],
                ),
                InputFrame(frame_id=1, timestamp=0.016, events=[]),
                InputFrame(
                    frame_id=2,
                    timestamp=0.032,
                    events=[
                        RecordedInputEvent(
                            event_type=InputEventType.KEY_UP,
                            device="keyboard",
                            code=32,
                        )
                    ],
                ),
            ],
        )

    def test_load_replay(self, sample_replay):
        """Test loading replay data."""
        player = ReplayPlayer()
        player.load(sample_replay)

        assert player.total_frames == 3
        assert player.seed == 12345

    def test_start_playback(self, sample_replay):
        """Test starting playback."""
        player = ReplayPlayer(sample_replay)
        result = player.start_playback()

        assert result is True
        assert player.is_playing
        assert player.current_frame == 0

    def test_advance_frame(self, sample_replay):
        """Test advancing frames."""
        player = ReplayPlayer(sample_replay)
        player.start_playback()

        frame = player.advance_frame()
        assert frame is not None
        assert frame.frame_id == 0
        assert player.current_frame == 1

        frame = player.advance_frame()
        assert frame.frame_id == 1

    def test_playback_complete(self, sample_replay):
        """Test playback completion."""
        player = ReplayPlayer(sample_replay)
        player.start_playback()

        # Advance through all frames
        while not player.is_finished():
            player.advance_frame()

        assert not player.is_playing
        assert player.is_finished()

    def test_event_handler(self, sample_replay):
        """Test event handler callback."""
        player = ReplayPlayer(sample_replay)
        events_received = []

        def handler(event):
            events_received.append(event)

        player.add_event_handler(handler)
        player.start_playback()

        # Advance through all frames
        while not player.is_finished():
            player.advance_frame()

        assert len(events_received) == 2  # KEY_DOWN and KEY_UP

    def test_pause_resume(self, sample_replay):
        """Test pause and resume."""
        player = ReplayPlayer(sample_replay)
        player.start_playback()

        player.pause_playback()
        assert player.is_paused

        player.resume_playback()
        assert player.is_playing

    def test_seek(self, sample_replay):
        """Test seeking to frame."""
        player = ReplayPlayer(sample_replay)
        player.start_playback()

        result = player.seek_to_frame(2)
        assert result is True
        assert player.current_frame == 2


class TestReplaySerializer:
    """Tests for ReplaySerializer."""

    @pytest.fixture
    def sample_replay(self):
        """Create sample replay data."""
        return ReplayData(
            metadata=ReplayMetadata(
                version=1,
                seed=12345,
                start_scene="test_scene",
                frame_count=2,
            ),
            frames=[
                InputFrame(
                    frame_id=0,
                    timestamp=0.0,
                    events=[
                        RecordedInputEvent(
                            event_type=InputEventType.KEY_DOWN,
                            device="keyboard",
                            code=32,
                        )
                    ],
                ),
                InputFrame(frame_id=1, timestamp=0.016, events=[]),
            ],
        )

    def test_save_and_load_compressed(self, sample_replay):
        """Test saving and loading compressed replay."""
        serializer = ReplaySerializer()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name

        try:
            # Save
            result = serializer.save(sample_replay, path, compress=True)
            assert result is True

            # Load
            loaded = serializer.load(path + ".replay.gz")
            assert loaded is not None
            assert loaded.metadata.seed == 12345
            assert len(loaded.frames) == 2

        finally:
            Path(path + ".replay.gz").unlink(missing_ok=True)

    def test_save_and_load_uncompressed(self, sample_replay):
        """Test saving and loading uncompressed replay."""
        serializer = ReplaySerializer()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name

        try:
            # Save
            result = serializer.save(sample_replay, path, compress=False)
            assert result is True

            # Load
            loaded = serializer.load(path + ".replay")
            assert loaded is not None
            assert loaded.metadata.seed == 12345

        finally:
            Path(path + ".replay").unlink(missing_ok=True)

    def test_convenience_functions(self, sample_replay):
        """Test save_replay and load_replay convenience functions."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name

        try:
            # Save
            result = save_replay(sample_replay, path)
            assert result is True

            # Load
            loaded = load_replay(path + ".replay.gz")
            assert loaded is not None
            assert loaded.metadata.seed == sample_replay.metadata.seed

        finally:
            Path(path + ".replay.gz").unlink(missing_ok=True)

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file."""
        serializer = ReplaySerializer()
        result = serializer.load("/nonexistent/path.replay")
        assert result is None


class TestDeterminism:
    """Tests for deterministic replay."""

    def test_record_playback_matches(self):
        """Test that playback produces same events as recording."""
        # Record
        recorder = ReplayRecorder()
        recorder.start_recording(seed=42)

        recorder.begin_frame(0, 0.0, 0.016)
        recorder.record_key_down(32)
        recorder.record_action("jump")
        recorder.end_frame()

        recorder.begin_frame(1, 0.016, 0.016)
        recorder.record_key_up(32)
        recorder.end_frame()

        recorded_data = recorder.stop_recording()

        # Playback
        player = ReplayPlayer(recorded_data)
        playback_events = []

        def handler(event):
            playback_events.append(event)

        player.add_event_handler(handler)
        player.start_playback()

        while not player.is_finished():
            player.advance_frame()

        # Verify
        assert len(playback_events) == 3  # KEY_DOWN, ACTION, KEY_UP
        assert playback_events[0].event_type == InputEventType.KEY_DOWN
        assert playback_events[1].event_type == InputEventType.ACTION
        assert playback_events[2].event_type == InputEventType.KEY_UP
