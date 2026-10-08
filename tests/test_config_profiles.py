"""Layered config profiles: push, peel off, and what each layer owns."""

import json
import logging
from dataclasses import dataclass

import pytest

from pyguara.common.types import Color
from pyguara.config.events import OnConfigurationChanged
from pyguara.config.manager import ConfigManager
from pyguara.log import get_logger


@dataclass
class BalanceConfig:
    """A game-defined section, to prove profiles are not engine-only."""

    enemy_hp_scale: float = 1.0
    permadeath: bool = False


HARD = {"balance": {"enemy_hp_scale": 2.5, "permadeath": True}}
QUIET = {"audio": {"master_volume": 0.2, "music_volume": 0.0}}


def _manager(tmp_path, **kwargs):
    """A loaded manager with a `balance` section registered."""
    path = tmp_path / "c.json"
    path.write_text(json.dumps(kwargs.pop("document", {})))
    manager = ConfigManager(file_path=path, **kwargs)
    manager.register_section("balance", BalanceConfig)
    manager.load()
    return manager


# -- Push and pop --


def test_a_pushed_profile_applies_every_override(tmp_path):
    manager = _manager(tmp_path)
    assert manager.push_profile("hard", HARD)

    balance = manager.section(BalanceConfig)
    assert balance.enemy_hp_scale == 2.5
    assert balance.permadeath is True
    assert manager.active_profiles == ("hard",)


def test_popping_restores_exactly_what_was_underneath(tmp_path):
    """The reason a profile is not just a batch of assignments: the previous
    value is gone the moment plain assignment overwrites it."""
    manager = _manager(tmp_path)
    manager.update_setting("balance", "enemy_hp_scale", 1.3)

    manager.push_profile("hard", HARD)
    assert manager.pop_profile()

    assert manager.section(BalanceConfig).enemy_hp_scale == 1.3
    assert manager.section(BalanceConfig).permadeath is False
    assert manager.active_profiles == ()


def test_the_later_layer_wins_where_two_set_the_same_setting(tmp_path):
    manager = _manager(tmp_path)
    manager.push_profile("a", {"audio": {"master_volume": 0.5}})
    manager.push_profile("b", {"audio": {"master_volume": 0.1}})

    assert manager.config.audio.master_volume == 0.1

    manager.pop_profile("b")
    assert manager.config.audio.master_volume == 0.5


def test_a_layer_can_be_peeled_from_the_middle_of_the_stack(tmp_path):
    """Run modifiers are independent: dropping one must not require dropping
    everything pushed after it."""
    manager = _manager(tmp_path)
    manager.push_profile("hard", HARD)
    manager.push_profile("quiet", QUIET)

    assert manager.pop_profile("hard")

    assert manager.active_profiles == ("quiet",)
    assert manager.section(BalanceConfig).enemy_hp_scale == 1.0
    assert manager.config.audio.master_volume == 0.2


def test_clear_profiles_returns_to_the_base(tmp_path):
    manager = _manager(tmp_path)
    manager.push_profile("hard", HARD)
    manager.push_profile("quiet", QUIET)

    assert manager.clear_profiles()

    assert manager.active_profiles == ()
    assert manager.config.audio.master_volume == 1.0
    assert manager.section(BalanceConfig).permadeath is False
    assert not manager.clear_profiles()


def test_popping_nothing_is_not_an_error(tmp_path):
    assert _manager(tmp_path).pop_profile() is False


def test_pushing_the_same_profile_twice_is_refused(tmp_path, caplog):
    manager = _manager(tmp_path)
    manager.push_profile("hard", HARD)

    with caplog.at_level(logging.WARNING):
        manager = ConfigManager(logger=get_logger("test.profiles"))
        manager.push_profile("hard", QUIET)
        assert not manager.push_profile("hard", QUIET)

    assert "already active" in caplog.text


def test_popping_an_inactive_profile_is_reported(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        manager = ConfigManager(logger=get_logger("test.profiles"))
        assert not manager.pop_profile("nope")

    assert "not active" in caplog.text


# -- Rejection is all-or-nothing --


def test_a_profile_naming_an_unknown_setting_applies_nothing(tmp_path, caplog):
    """Half a difficulty preset is worse than none of it -- and a typo that
    silently skips one line is an hour of someone's afternoon."""
    manager = _manager(tmp_path, logger=get_logger("test.profiles"))

    with caplog.at_level(logging.ERROR):
        applied = manager.push_profile(
            "typo", {"audio": {"master_volume": 0.3, "mastre_volume": 0.9}}
        )

    assert not applied
    assert manager.config.audio.master_volume == 1.0
    assert manager.active_profiles == ()
    assert "mastre_volume" in caplog.text


def test_a_profile_naming_an_unknown_section_is_refused(tmp_path, caplog):
    manager = _manager(tmp_path, logger=get_logger("test.profiles"))

    with caplog.at_level(logging.ERROR):
        assert not manager.push_profile("x", {"blance": {"permadeath": True}})

    assert "no section 'blance'" in caplog.text


def test_a_profile_with_a_wrong_typed_value_is_refused(tmp_path, caplog):
    manager = _manager(tmp_path, logger=get_logger("test.profiles"))

    with caplog.at_level(logging.ERROR):
        assert not manager.push_profile("x", {"display": {"fps_target": "fast"}})

    assert manager.config.display.fps_target == 60
    assert "expects int" in caplog.text


def test_a_profile_the_validator_refuses_applies_nothing(tmp_path, caplog):
    manager = _manager(tmp_path, logger=get_logger("test.profiles"))

    with caplog.at_level(logging.ERROR):
        applied = manager.push_profile(
            "broken", {"display": {"fullscreen": True, "fps_target": 0}}
        )

    assert not applied
    assert manager.config.display.fps_target == 60
    assert manager.config.display.fullscreen is False
    assert manager.active_profiles == ()


def test_an_already_unsound_config_does_not_block_every_push(tmp_path):
    """Refusing every profile because the loaded file is bad would be a
    cascade with no way out."""
    manager = _manager(tmp_path, document={"audio": {"master_volume": 9.0}})

    assert manager.push_profile("hard", HARD)
    assert manager.section(BalanceConfig).permadeath is True


def test_an_unknown_profile_name_lists_the_known_ones(tmp_path, caplog):
    manager = _manager(tmp_path, logger=get_logger("test.profiles"))
    manager.define_profile("hard", HARD)

    with caplog.at_level(logging.ERROR):
        assert not manager.push_profile("harrd")

    assert "Defined profiles: hard" in caplog.text


# -- Definitions --


def test_profiles_are_authorable_in_the_config_file(tmp_path):
    manager = _manager(tmp_path, document={"profiles": {"hard": HARD, "quiet": QUIET}})

    assert manager.available_profiles == ("hard", "quiet")
    assert manager.push_profile("hard")
    assert manager.section(BalanceConfig).enemy_hp_scale == 2.5


def test_a_defined_profile_survives_a_save_load_round_trip(tmp_path):
    path = tmp_path / "c.json"
    manager = ConfigManager(file_path=path)
    manager.register_section("balance", BalanceConfig)
    manager.load()
    manager.define_profile("hard", HARD)
    assert manager.save()

    reloaded = ConfigManager(file_path=path)
    reloaded.register_section("balance", BalanceConfig)
    reloaded.load()

    assert reloaded.available_profiles == ("hard",)
    assert reloaded.push_profile("hard")
    assert reloaded.section(BalanceConfig).permadeath is True


def test_defining_a_bad_profile_raises_rather_than_waiting_for_the_push(tmp_path):
    """A definition written in code is a programmer error, unlike one read
    from a file."""
    manager = _manager(tmp_path)

    with pytest.raises(ValueError, match="mastre_volume"):
        manager.define_profile("typo", {"audio": {"mastre_volume": 0.5}})


def test_defining_does_not_apply_anything(tmp_path):
    manager = _manager(tmp_path)
    manager.define_profile("hard", HARD)

    assert manager.section(BalanceConfig).enemy_hp_scale == 1.0
    assert manager.active_profiles == ()


# -- Interaction with update_setting --


def test_an_active_profile_owns_the_settings_it_sets(tmp_path, caplog):
    """A run modifier the options menu can switch off is not a modifier."""
    manager = _manager(tmp_path, logger=get_logger("test.profiles"))
    manager.push_profile("hard", HARD)

    with caplog.at_level(logging.WARNING):
        assert not manager.update_setting("balance", "permadeath", False)

    assert manager.section(BalanceConfig).permadeath is True
    assert "'hard'" in caplog.text


def test_a_setting_no_profile_claims_is_still_writable(tmp_path):
    manager = _manager(tmp_path)
    manager.push_profile("hard", HARD)

    assert manager.update_setting("display", "fps_target", 144)
    assert manager.config.display.fps_target == 144


def test_an_update_survives_a_push_and_pop_of_an_unrelated_profile(tmp_path):
    """`update_setting` writes through to the base layer, or re-applying the
    stack would silently revert the player's own choice."""
    manager = _manager(tmp_path)
    manager.update_setting("display", "fps_target", 144)

    manager.push_profile("quiet", QUIET)
    manager.pop_profile()

    assert manager.config.display.fps_target == 144


def test_a_rejected_update_does_not_poison_the_base(tmp_path):
    manager = _manager(tmp_path)
    assert not manager.update_setting("audio", "master_volume", 9.0)

    manager.push_profile("quiet", QUIET)
    manager.pop_profile()

    assert manager.config.audio.master_volume == 1.0


def test_a_load_drops_every_active_profile(tmp_path):
    """The stack's values referred to a config that no longer exists."""
    manager = _manager(tmp_path)
    manager.push_profile("hard", HARD)

    manager.load()

    assert manager.active_profiles == ()
    assert manager.section(BalanceConfig).enemy_hp_scale == 1.0


# -- Identity and events --


def test_the_live_config_object_is_mutated_in_place(tmp_path):
    """The engine caches `manager.config` and its sections widely; handing
    out a replacement would leave every holder on the old one."""
    manager = _manager(tmp_path)
    config, audio = manager.config, manager.config.audio

    manager.push_profile("quiet", QUIET)

    assert manager.config is config
    assert manager.config.audio is audio
    assert audio.master_volume == 0.2


def test_a_push_publishes_one_event_per_changed_setting(tmp_path, event_dispatcher):
    seen = []
    event_dispatcher.subscribe(OnConfigurationChanged, seen.append)

    manager = _manager(tmp_path, event_dispatcher=event_dispatcher)
    manager.push_profile("quiet", QUIET)

    changed = {(e.section, e.setting, e.new_value) for e in seen}
    assert changed == {
        ("audio", "master_volume", 0.2),
        ("audio", "music_volume", 0.0),
    }
    assert all(e.profile == "quiet" for e in seen)


def test_an_event_names_the_profile_so_a_layer_is_not_a_player_edit(
    tmp_path, event_dispatcher
):
    seen = []
    event_dispatcher.subscribe(OnConfigurationChanged, seen.append)

    manager = _manager(tmp_path, event_dispatcher=event_dispatcher)
    manager.update_setting("display", "fps_target", 144)
    manager.push_profile("quiet", QUIET)
    manager.pop_profile()

    assert seen[0].profile is None
    assert {e.profile for e in seen[1:]} == {"quiet"}


def test_a_refused_push_publishes_nothing(tmp_path, event_dispatcher):
    seen = []
    event_dispatcher.subscribe(OnConfigurationChanged, seen.append)

    manager = _manager(tmp_path, event_dispatcher=event_dispatcher)
    manager.push_profile("broken", {"physics": {"substeps": 0}})

    assert seen == []


def test_a_mutable_value_is_not_shared_with_the_base_snapshot(tmp_path):
    """A `Color` mutated in place would otherwise rewrite the base that a
    pop is supposed to restore."""
    manager = _manager(tmp_path)
    manager.push_profile("tint", {"display": {"default_color": Color(9, 9, 9)}})

    manager.config.display.default_color.r = 200
    manager.pop_profile()

    assert manager.config.display.default_color == Color(0, 0, 0)
