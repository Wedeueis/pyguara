from unittest.mock import patch, mock_open
from pyguara.config.manager import ConfigManager

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

    with patch("builtins.open", mock_open(read_data=SAMPLE_CONFIG_JSON)):
        # We also need to mock Path.exists to true
        with patch("pathlib.Path.exists", return_value=True):
            success = manager.load()

    assert success
    assert manager.config.display.screen_width == 1920
    assert manager.config.display.fullscreen is True
    assert manager.config.audio.master_volume == 0.5


def test_load_missing_file_creates_default():
    manager = ConfigManager()

    with patch("pathlib.Path.exists", return_value=False):
        # Should call save() which uses open('w')
        with patch("builtins.open", mock_open()) as mocked_file:
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
