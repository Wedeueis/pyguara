"""Tests for the replay system."""

import gzip
import os
import tempfile
from datetime import datetime
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

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


class TestEventDictRoundtrip:
    """to_dict/from_dict for the fields the old suite never exercised."""

    def test_position_and_modifiers_survive_a_roundtrip(self):
        event = RecordedInputEvent(
            event_type=InputEventType.MOUSE_DOWN,
            device="mouse",
            code=1,
            position=(10.0, 20.0),
            modifiers=[1, 64],
        )
        restored = RecordedInputEvent.from_dict(event.to_dict())
        assert restored.position == (10.0, 20.0)
        assert restored.modifiers == [1, 64]

    def test_origin_position_is_not_dropped_as_falsy(self):
        # (0.0, 0.0) is a real recorded position, not "no position".
        event = RecordedInputEvent(
            event_type=InputEventType.MOUSE_MOVE,
            device="mouse",
            code=0,
            position=(0.0, 0.0),
        )
        assert RecordedInputEvent.from_dict(event.to_dict()).position == (0.0, 0.0)

    def test_missing_optional_fields_default_cleanly(self):
        event = RecordedInputEvent.from_dict(
            {"event_type": "KEY_DOWN", "device": "keyboard", "code": 32}
        )
        assert event.position is None
        assert event.modifiers == []


class TestSerializerFormat:
    """The extension/compression contract and version gate (uniform-setup gaps)."""

    @pytest.fixture
    def replay(self):
        return ReplayData(
            metadata=ReplayMetadata(version=1, seed=5, frame_count=2),
            frames=[InputFrame(i, i * 0.016, 0.016, []) for i in range(2)],
        )

    def test_compress_true_to_an_explicit_replay_path_stays_loadable(
        self, replay, tmp_path
    ):
        # The old suite only ever saved to an extensionless path, so this
        # (the default compress=True + a caller-supplied ".replay") slipped
        # through as a gzip stream named ".replay" that load() then rejected.
        path = str(tmp_path / "run.replay")
        assert ReplaySerializer().save(replay, path, compress=True)
        assert Path(path).read_bytes()[:1] == b"{"  # plain JSON, not gzip magic
        assert ReplaySerializer().load(path) is not None

    def test_gz_extension_forces_compression_even_with_compress_false(
        self, replay, tmp_path
    ):
        path = str(tmp_path / "run.replay.gz")
        assert ReplaySerializer().save(replay, path, compress=False)
        with gzip.open(path, "rt", encoding="utf-8") as f:
            assert f.read().startswith("{")

    def test_load_refuses_a_newer_format_version(self, replay, tmp_path):
        replay.metadata.version = ReplaySerializer.SUPPORTED_VERSION + 1
        path = str(tmp_path / "future")
        ReplaySerializer().save(replay, path, compress=False)
        assert ReplaySerializer().load(path + ".replay") is None

    def test_load_of_truncated_json_returns_none(self, tmp_path):
        path = tmp_path / "broken.replay"
        path.write_text('{"metadata": {"seed": 1}, "frames": [')
        assert ReplaySerializer().load(str(path)) is None

    def test_get_metadata_reads_a_large_multiframe_replay(self, tmp_path):
        big = ReplayData(
            metadata=ReplayMetadata(
                version=1, seed=4242, start_scene="lvl", frame_count=500
            ),
            frames=[
                InputFrame(
                    i,
                    i * 0.016,
                    0.016,
                    [
                        RecordedInputEvent(
                            InputEventType.KEY_DOWN, "keyboard", 32 + (i % 20)
                        )
                    ],
                )
                for i in range(500)
            ],
        )
        path = str(tmp_path / "big")
        ReplaySerializer().save(big, path, compress=False)
        assert Path(path + ".replay").stat().st_size > 20_000
        meta = ReplaySerializer().get_metadata(path + ".replay")
        assert meta is not None and meta["seed"] == 4242

    def test_get_metadata_on_compressed_and_missing(self, replay, tmp_path):
        path = str(tmp_path / "c")
        ReplaySerializer().save(replay, path, compress=True)
        assert ReplaySerializer().get_metadata(path + ".replay.gz")["seed"] == 5
        assert ReplaySerializer().get_metadata(str(tmp_path / "nope.replay")) is None


class TestRecorderMetadata:
    """Recorder stamps and the recording-state guards."""

    def test_engine_version_is_the_package_version_not_a_placeholder(self):
        recorder = ReplayRecorder()
        recorder.start_recording(seed=1)
        data = recorder.stop_recording()
        assert data.metadata.engine_version != "0.0.0"
        assert data.metadata.engine_version == ReplayRecorder._ENGINE_VERSION

    def test_recorded_at_is_timezone_aware_iso(self):
        recorder = ReplayRecorder()
        recorder.start_recording(seed=1)
        stamp = recorder.stop_recording().metadata.recorded_at
        assert datetime.fromisoformat(stamp).tzinfo is not None

    def test_double_start_recording_raises(self):
        recorder = ReplayRecorder()
        recorder.start_recording(seed=1)
        with pytest.raises(RuntimeError):
            recorder.start_recording(seed=2)

    def test_event_recorded_between_frames_is_dropped(self):
        recorder = ReplayRecorder()
        recorder.start_recording(seed=1)
        recorder.record_key_down(32)  # no begin_frame -> nowhere to go
        recorder.begin_frame(0, 0.0, 0.016)
        recorder.record_key_up(32)
        recorder.end_frame()
        data = recorder.stop_recording()
        assert [e.event_type for e in data.frames[0].events] == [InputEventType.KEY_UP]

    def test_gamepad_and_modifier_helpers_record_what_they_are_given(self):
        recorder = ReplayRecorder()
        recorder.start_recording(seed=1)
        recorder.begin_frame(0, 0.0, 0.016)
        recorder.record_key_down(32, modifiers=[1])
        recorder.record_gamepad_button(3, pressed=True)
        recorder.record_gamepad_axis(1, 0.75)
        recorder.end_frame()
        events = recorder.stop_recording().frames[0].events
        assert events[0].modifiers == [1]
        assert events[1].event_type == InputEventType.GAMEPAD_BUTTON_DOWN
        assert events[2].event_type == InputEventType.GAMEPAD_AXIS
        assert events[2].value == 0.75


class TestReplayPlayerTimeline:
    """The wall-clock update() model and peek_delta() -- untested before."""

    def _replay(self):
        return ReplayData(
            metadata=ReplayMetadata(seed=1, frame_count=3),
            frames=[
                InputFrame(
                    0,
                    0.0,
                    0.1,
                    [RecordedInputEvent(InputEventType.KEY_DOWN, "keyboard", 1)],
                ),
                InputFrame(1, 0.1, 0.1, []),
                InputFrame(
                    2,
                    0.2,
                    0.1,
                    [RecordedInputEvent(InputEventType.KEY_UP, "keyboard", 1)],
                ),
            ],
        )

    def test_update_consumes_frames_as_elapsed_time_crosses_their_timestamp(self):
        player = ReplayPlayer(self._replay())
        player.start_playback()

        assert [f.frame_id for f in player.update(0.05)] == [0]  # only ts<=0.05
        assert [f.frame_id for f in player.update(0.10)] == [1]  # elapsed 0.15
        assert [f.frame_id for f in player.update(0.10)] == [2]  # elapsed 0.25
        assert player.is_finished()
        assert not player.is_playing

    def test_update_respects_playback_speed(self):
        player = ReplayPlayer(self._replay())
        player.playback_speed = 4.0
        player.start_playback()
        # 0.05 real * 4 = 0.20 elapsed -> frames 0,1,2 all due at once.
        assert [f.frame_id for f in player.update(0.05)] == [0, 1, 2]

    def test_peek_delta_reports_the_next_frame_then_none_at_end(self):
        player = ReplayPlayer(self._replay())
        assert player.peek_delta() is None  # not playing yet
        player.start_playback()
        assert player.peek_delta() == pytest.approx(0.1)
        while player.advance_frame() is not None:
            pass
        assert player.peek_delta() is None

    def test_seek_out_of_range_is_rejected_without_moving(self):
        player = ReplayPlayer(self._replay())
        player.start_playback()
        player.advance_frame()
        assert player.seek_to_frame(99) is False
        assert player.seek_to_frame(-1) is False
        assert player.current_frame == 1

    def test_a_raising_event_handler_does_not_stop_playback(self):
        player = ReplayPlayer(self._replay())
        seen = []
        player.add_event_handler(lambda _e: (_ for _ in ()).throw(RuntimeError("boom")))
        player.add_event_handler(seen.append)
        player.start_playback()
        while not player.is_finished():
            player.advance_frame()
        assert len(seen) == 2  # both KEY_DOWN and KEY_UP still reached handler 2


class TestReplayInputWiring:
    """Recorder <-> InputManager: gamepad capture and full raw-stream replay."""

    @pytest.fixture
    def app(self):
        from pyguara.application.bootstrap import create_headless_application

        application = create_headless_application()
        yield application
        application.shutdown()

    def test_gamepad_button_and_axis_are_captured_when_recording(self, app):
        from pyguara.input.events import GamepadAxisEvent, GamepadButtonEvent
        from pyguara.input.gamepad import GamepadAxis, GamepadButton

        recorder = ReplayRecorder()
        recorder.start_recording(seed=1)
        app._input_manager.attach_recorder(recorder)
        recorder.begin_frame(0, 0.0, 0.016)
        app._input_manager._on_gamepad_button(
            GamepadButtonEvent(controller_id=0, button=GamepadButton.A, is_pressed=True)
        )
        app._input_manager._on_gamepad_axis(
            GamepadAxisEvent(controller_id=0, axis=GamepadAxis.LEFT_STICK_X, value=0.8)
        )
        recorder.end_frame()
        events = recorder.stop_recording().frames[0].events
        assert [e.device for e in events] == ["gamepad", "gamepad"]
        assert events[0].event_type == InputEventType.GAMEPAD_BUTTON_DOWN
        assert events[1].event_type == InputEventType.GAMEPAD_AXIS
        assert events[1].value == pytest.approx(0.8)

    def test_replayed_mouse_event_restores_position_and_dispatches_onmouse(self, app):
        from pyguara.input.events import OnMouseEvent

        seen: list[OnMouseEvent] = []
        app._event_dispatcher.subscribe(OnMouseEvent, seen.append)
        app._input_manager.process_replayed_event(
            RecordedInputEvent(
                InputEventType.MOUSE_DOWN, "mouse", 1, 1.0, position=(320.0, 240.0)
            )
        )
        app._input_manager.process_replayed_event(
            RecordedInputEvent(
                InputEventType.MOUSE_MOVE, "mouse", 0, 0.0, position=(5.0, 6.0)
            )
        )
        assert seen[0].position == (320, 240) and seen[0].is_down
        assert seen[1].position == (5, 6) and seen[1].is_motion

    def test_replayed_key_event_carries_modifiers_on_onrawkey(self, app):
        from pyguara.input.events import OnRawKeyEvent

        seen: list[OnRawKeyEvent] = []
        app._event_dispatcher.subscribe(OnRawKeyEvent, seen.append)
        app._input_manager.process_replayed_event(
            RecordedInputEvent(
                InputEventType.KEY_DOWN, "keyboard", 97, 1.0, modifiers=[64]
            )
        )
        assert seen[0].key_code == 97
        assert seen[0].is_down
        assert 64 in seen[0].modifiers
