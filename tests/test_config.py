from unittest.mock import mock_open, patch

import pytest

from pyguara.common.types import Color
from pyguara.config.manager import ConfigManager
from pyguara.config.types import GameConfig, PhysicsConfig, RenderingBackend
from pyguara.config.validation import ConfigValidator, ValidationSeverity
from pyguara.log.types import LogLevel

SAMPLE_CONFIG_JSON = """
{
    "display": {
        "screen_width": 1920,
        "screen_height": 1080,
        "fullscreen": true
    },
    "audio": {
        "master_volume": 0.5
    }
}
"""


def test_defaults():
    manager = ConfigManager()
    cfg = manager.config
    # Verify defaults from dataclass
    assert cfg.display.screen_width == 1200
    assert cfg.audio.master_volume == 1.0


def test_load_valid_config():
    manager = ConfigManager()

    # Path.exists must also report true for load() to read the mocked file.
    with (
        patch("builtins.open", mock_open(read_data=SAMPLE_CONFIG_JSON)),
        patch("pathlib.Path.exists", return_value=True),
    ):
        success = manager.load()

    assert success
    assert manager.config.display.screen_width == 1920
    assert manager.config.display.fullscreen is True
    assert manager.config.audio.master_volume == 0.5


def test_load_missing_file_creates_default():
    manager = ConfigManager()

    # A missing file makes load() fall through to save(), which opens for write.
    with (
        patch("pathlib.Path.exists", return_value=False),
        patch("builtins.open", mock_open()) as mocked_file,
    ):
        success = manager.load()

    assert success
    # Should have written defaults
    mocked_file.assert_called_with(manager._file_path, "w", encoding="utf-8")


def test_update_setting_fires_event(event_dispatcher):
    manager = ConfigManager(event_dispatcher=event_dispatcher)

    events = []
    # Using string name for event because we might not have imported it
    from pyguara.config.events import OnConfigurationChanged

    event_dispatcher.subscribe(OnConfigurationChanged, lambda e: events.append(e))

    success = manager.update_setting("display", "screen_width", 800)

    assert success
    assert manager.config.display.screen_width == 800
    assert len(events) == 1
    assert events[0].section == "display"
    assert events[0].setting == "screen_width"
    assert events[0].new_value == 800


def test_invalid_setting_update():
    manager = ConfigManager()
    # Non-existent section
    assert not manager.update_setting("bad_section", "val", 1)
    # Non-existent setting
    assert not manager.update_setting("display", "bad_setting", 1)


# -- Round-tripping through a real file --


def test_color_survives_a_save_load_round_trip(tmp_path):
    """`asdict()` turns Color into a plain dict and from_dict fed it straight
    back to WindowConfig, so `default_color` came back as a dict and every
    reader of it broke on attribute access."""
    path = tmp_path / "game_config.json"
    writer = ConfigManager(file_path=path)
    writer.config.display.default_color = Color(10, 20, 30, 40)
    writer.save()

    reader = ConfigManager(file_path=path)
    reader.load()

    assert reader.config.display.default_color == Color(10, 20, 30, 40)
    assert isinstance(reader.config.display.default_color, Color)


def test_second_launch_loads_a_usable_default_color(tmp_path):
    """The failing path was the ordinary one: a first run finds no config file
    and writes defaults, and the second run reads them back. `default_color`
    then reached the window backend as a dict."""
    path = tmp_path / "game_config.json"

    ConfigManager(file_path=path).load()  # first launch writes defaults
    second = ConfigManager(file_path=path)
    second.load()

    assert second.config.display.default_color.r == 0


def test_enums_survive_a_round_trip(tmp_path):
    path = tmp_path / "c.json"
    writer = ConfigManager(file_path=path)
    writer.config.display.backend = RenderingBackend.MODERNGL
    writer.config.debug.log_level = LogLevel.DEBUG
    writer.save()

    reader = ConfigManager(file_path=path)
    reader.load()

    assert reader.config.display.backend is RenderingBackend.MODERNGL
    assert reader.config.debug.log_level is LogLevel.DEBUG


def test_every_field_survives_a_round_trip(tmp_path):
    """Guards the whole surface, so a newly added field cannot quietly fail to
    round-trip the way default_color did."""
    path = tmp_path / "c.json"
    original = ConfigManager(file_path=path)
    original.config.display.screen_width = 1920
    original.config.audio.sfx_volume = 0.25
    original.config.input.gamepad_deadzone = 0.4
    original.config.physics.gravity_y = 900.0
    original.config.debug.show_fps = True
    original.save()

    restored = ConfigManager(file_path=path)
    restored.load()

    assert restored.config == original.config


# -- from_dict --


def test_from_dict_does_not_mutate_its_input():
    raw = {"debug": {"log_level": "DEBUG"}}

    GameConfig.from_dict(raw)

    assert raw == {"debug": {"log_level": "DEBUG"}}


def test_unknown_keys_are_ignored_and_reported(caplog):
    """A typo'd key was dropped in silence, so the setting simply never took
    effect and nothing said why."""
    import logging

    with caplog.at_level(logging.WARNING):
        config = GameConfig.from_dict(
            {"display": {"screen_widht": 1920, "fps_target": 144}}
        )

    assert config.display.screen_width == 1200
    assert config.display.fps_target == 144
    assert "screen_widht" in caplog.text


def test_absent_sections_keep_their_defaults():
    config = GameConfig.from_dict({"audio": {"master_volume": 0.5}})

    assert config.audio.master_volume == 0.5
    assert config.display.screen_width == 1200
    assert config.physics.fixed_timestep_hz == 60


def test_an_unparseable_enum_value_falls_back_and_warns(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        config = GameConfig.from_dict({"display": {"backend": "vulkan"}})

    assert config.display.backend is RenderingBackend.PYGAME
    assert "vulkan" in caplog.text


def test_log_level_accepts_both_a_name_and_a_number():
    assert GameConfig.from_dict({"debug": {"log_level": "DEBUG"}}).debug.log_level is (
        LogLevel.DEBUG
    )
    assert GameConfig.from_dict({"debug": {"log_level": 10}}).debug.log_level is (
        LogLevel.DEBUG
    )


# -- update_setting type enforcement --


def test_update_setting_rejects_the_wrong_type():
    """The old check only warned and then assigned anyway, so screen_width
    could be left holding the string "not a number"."""
    manager = ConfigManager()

    assert not manager.update_setting("display", "screen_width", "not a number")
    assert manager.config.display.screen_width == 1200


def test_update_setting_rejects_a_bool_for_an_int_field():
    """isinstance(True, int) is True, so a bare isinstance check let a bool
    through into fps_target."""
    manager = ConfigManager()

    assert not manager.update_setting("display", "fps_target", True)
    assert manager.config.display.fps_target == 60


def test_update_setting_accepts_an_int_where_a_float_is_declared():
    manager = ConfigManager()

    assert manager.update_setting("audio", "master_volume", 1)
    assert manager.config.audio.master_volume == 1


def test_update_setting_accepts_a_matching_bool():
    manager = ConfigManager()

    assert manager.update_setting("display", "fullscreen", True)
    assert manager.config.display.fullscreen is True


# -- update_setting validation --


def test_update_setting_rejects_a_value_the_validator_refuses():
    """The validator only ever ran on load, so update_setting could put the
    config into a state load() would have rejected."""
    manager = ConfigManager()

    assert not manager.update_setting("audio", "master_volume", 99.0)
    assert manager.config.audio.master_volume == 1.0


def test_a_rejected_update_dispatches_no_event(event_dispatcher):
    from pyguara.config.events import OnConfigurationChanged

    events = []
    event_dispatcher.subscribe(OnConfigurationChanged, lambda e: events.append(e))
    manager = ConfigManager(event_dispatcher=event_dispatcher)

    manager.update_setting("audio", "master_volume", 99.0)
    manager.update_setting("display", "screen_width", "wide")

    assert events == []


def test_update_setting_allows_a_merely_suboptimal_value():
    """A WARNING is advice, not a veto: a low frame target is legal."""
    manager = ConfigManager()

    assert manager.update_setting("display", "fps_target", 20)
    assert manager.config.display.fps_target == 20


# -- Validation rules --


def test_a_zero_fixed_timestep_is_reported_as_critical():
    """Application.run() divides by fixed_timestep_hz on startup, and nothing
    checked it, so a zero in a config file crashed with a bare
    ZeroDivisionError naming neither the setting nor the file."""
    config = GameConfig()
    config.physics.fixed_timestep_hz = 0

    issues = ConfigValidator().validate(config)

    assert any(
        i.setting == "fixed_timestep_hz" and i.severity is ValidationSeverity.CRITICAL
        for i in issues
    )


def test_fixed_dt_raises_a_named_error_rather_than_dividing_by_zero():
    with pytest.raises(ValueError, match="fixed_timestep_hz must be positive"):
        _ = PhysicsConfig(fixed_timestep_hz=0).fixed_dt


def test_all_three_volumes_are_validated():
    config = GameConfig()
    config.audio.master_volume = 2.0
    config.audio.sfx_volume = -1.0
    config.audio.music_volume = 0.5

    settings = {i.setting for i in ConfigValidator().validate(config)}

    assert settings == {"master_volume", "sfx_volume"}


def test_screen_height_and_deadzone_are_validated():
    config = GameConfig()
    config.display.screen_height = 10
    config.input.gamepad_deadzone = 1.5

    settings = {i.setting for i in ConfigValidator().validate(config)}

    assert "screen_height" in settings
    assert "gamepad_deadzone" in settings


def test_a_negative_sleep_time_threshold_is_rejected():
    """PymunkEngine raises on a negative threshold; the validator should say
    so with the setting named, not leave it to a bare ValueError on boot."""
    config = GameConfig()
    config.physics.sleep_time_threshold = -1.0

    issues = ConfigValidator().validate(config)

    assert any(
        i.setting == "sleep_time_threshold" and i.severity is ValidationSeverity.ERROR
        for i in issues
    )


def test_a_zero_substeps_is_reported_as_critical():
    """PymunkEngine raises on substeps < 1; without validation that surfaces
    as an unnamed ValueError at startup."""
    config = GameConfig()
    config.physics.substeps = 0

    issues = ConfigValidator().validate(config)

    assert any(
        i.setting == "substeps" and i.severity is ValidationSeverity.CRITICAL
        for i in issues
    )


def test_a_sound_default_config_produces_no_issues():
    assert ConfigValidator().validate(GameConfig()) == []


# -- Severity reaches the log --


def test_load_reports_issues_at_their_own_severity(tmp_path, caplog):
    """Every issue was logged as a warning, so ERROR and CRITICAL problems sat
    among the merely suboptimal ones."""
    import json
    import logging

    from pyguara.log import get_logger

    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {"display": {"screen_width": 10}, "physics": {"fixed_timestep_hz": 0}}
        )
    )

    with caplog.at_level(logging.WARNING):
        ConfigManager(logger=get_logger("test.config"), file_path=path).load()

    levels = {r.levelname for r in caplog.records}
    assert "ERROR" in levels
    assert "CRITICAL" in levels


# -- Environment overrides --


def test_env_overrides_are_applied(tmp_path, monkeypatch):
    import json

    path = tmp_path / "c.json"
    path.write_text(json.dumps(GameConfig().to_dict()))
    monkeypatch.setenv("PYGUARA_WINDOW_WIDTH", "1920")
    monkeypatch.setenv("PYGUARA_BACKEND", "moderngl")
    monkeypatch.setenv("PYGUARA_LOG_LEVEL", "DEBUG")

    manager = ConfigManager(file_path=path)
    manager.load()

    assert manager.config.display.screen_width == 1920
    assert manager.config.display.backend is RenderingBackend.MODERNGL
    assert manager.config.debug.log_level is LogLevel.DEBUG


def test_an_invalid_env_override_is_reported_not_swallowed(
    tmp_path, monkeypatch, caplog
):
    """`except ValueError: pass` meant a typo in a launch script silently did
    nothing at all."""
    import json
    import logging

    from pyguara.log import get_logger

    path = tmp_path / "c.json"
    path.write_text(json.dumps(GameConfig().to_dict()))
    monkeypatch.setenv("PYGUARA_WINDOW_WIDTH", "not-an-int")

    with caplog.at_level(logging.WARNING):
        manager = ConfigManager(logger=get_logger("test.env"), file_path=path)
        manager.load()

    assert manager.config.display.screen_width == 1200
    assert "PYGUARA_WINDOW_WIDTH" in caplog.text


# -- Events --


def test_load_and_save_events_carry_a_real_timestamp(tmp_path, event_dispatcher):
    """These two events had no __post_init__ at all, so their timestamp was
    permanently 0.0."""
    import time

    from pyguara.config.events import OnConfigurationLoaded, OnConfigurationSaved

    seen = []
    event_dispatcher.subscribe(OnConfigurationLoaded, lambda e: seen.append(e))
    event_dispatcher.subscribe(OnConfigurationSaved, lambda e: seen.append(e))

    before = time.time()
    manager = ConfigManager(
        event_dispatcher=event_dispatcher, file_path=tmp_path / "c.json"
    )
    manager.save()
    manager.load()
    after = time.time()

    assert len(seen) == 2
    assert all(before <= e.timestamp <= after for e in seen)


# -- load() failure modes --


def test_load_returns_false_on_malformed_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ this is not json")

    manager = ConfigManager(file_path=path)

    assert not manager.load()
    assert manager.config.display.screen_width == 1200


def test_a_failed_load_leaves_the_previous_config_intact(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ nope")
    manager = ConfigManager(file_path=path)
    manager.update_setting("display", "screen_width", 800)

    manager.load()

    assert manager.config.display.screen_width == 800


def test_file_path_is_configurable(tmp_path):
    path = tmp_path / "nested" / "custom.json"
    manager = ConfigManager(file_path=path)

    assert manager.file_path == path
    assert manager.save()
    assert path.exists()
