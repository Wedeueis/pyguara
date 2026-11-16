"""Why the configuration refuses a value, and what it accepts as None.

`update_setting()` answers with a bool and a log line. `check_setting()`
gives the reason to a caller that has someone to show it to, and must
leave the configuration exactly as it found it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyguara.config.manager import ConfigManager


@pytest.fixture
def manager(tmp_path: Path) -> ConfigManager:
    """A configuration at its defaults."""
    return ConfigManager(file_path=tmp_path / "game_config.json")


class TestCheckSetting:
    """The manager says why it would refuse, and changes nothing."""

    def test_an_acceptable_value_has_no_reason(self, manager: ConfigManager) -> None:
        assert manager.check_setting("physics", "substeps", 8) is None
        assert manager.config.physics.substeps == 4

    def test_a_wrong_type_is_named(self, manager: ConfigManager) -> None:
        reason = manager.check_setting("physics", "substeps", "many")
        assert reason is not None and "expected int" in reason

    def test_an_unknown_setting_is_named(self, manager: ConfigManager) -> None:
        reason = manager.check_setting("physics", "nope", 1)
        assert reason is not None and "physics.nope" in reason

    def test_a_value_the_validator_blocks_is_left_unwritten(
        self, manager: ConfigManager
    ) -> None:
        reason = manager.check_setting("display", "screen_width", -5)
        assert reason is not None
        assert manager.config.display.screen_width == 1200

    def test_update_setting_refuses_what_check_setting_refuses(
        self, manager: ConfigManager
    ) -> None:
        assert manager.update_setting("display", "screen_width", -5) is False
        assert manager.config.display.screen_width == 1200

    def test_an_optional_setting_goes_back_to_none(
        self, manager: ConfigManager
    ) -> None:
        """Judged by its current value alone, a seed once set could never
        be cleared."""
        assert manager.update_setting("debug", "rng_seed", 7)
        assert manager.update_setting("debug", "rng_seed", None)
        assert manager.config.debug.rng_seed is None

    def test_a_setting_holding_none_still_has_a_type(
        self, manager: ConfigManager
    ) -> None:
        reason = manager.check_setting("debug", "rng_seed", "seven")
        assert reason is not None and "expected int" in reason
        assert manager.check_setting("debug", "rng_seed", True) is not None

    def test_none_is_refused_where_it_is_not_declared(
        self, manager: ConfigManager
    ) -> None:
        assert manager.check_setting("physics", "substeps", None) is not None

    def test_a_pinned_setting_names_its_profile(self, manager: ConfigManager) -> None:
        manager.define_profile("hard", {"physics": {"substeps": 9}})
        assert manager.push_profile("hard")
        assert manager.pinned_by("physics", "substeps") == "hard"
        reason = manager.check_setting("physics", "substeps", 2)
        assert reason is not None and "'hard'" in reason
