"""Game-defined config sections: registration, loading, overrides, validation."""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum

import pytest

from pyguara.common.types import Color
from pyguara.config.manager import ConfigManager
from pyguara.config.sections import SectionRegistryError
from pyguara.config.types import GameConfig, PhysicsConfig
from pyguara.config.validation import ValidationIssue, ValidationSeverity
from pyguara.log import get_logger


class Difficulty(Enum):
    """A game-defined enum, to prove enums are not an engine-only trick."""

    EASY = "easy"
    HARD = "hard"


@dataclass
class BalanceConfig:
    """The shape of section a game actually registers."""

    enemy_hp_scale: float = 1.0
    drop_rate: float = 0.25
    boss_waves: int = 3
    permadeath: bool = False
    difficulty: Difficulty = Difficulty.EASY
    accent: Color = field(default_factory=lambda: Color(10, 20, 30))


@dataclass
class CheckedConfig:
    """A section that carries its own rules (`ValidatableSection`)."""

    drop_rate: float = 0.25

    def validate(self) -> list[ValidationIssue]:
        """Refuse a drop rate outside 0..1."""
        if 0.0 <= self.drop_rate <= 1.0:
            return []
        return [
            ValidationIssue(
                ValidationSeverity.ERROR,
                "wrong-on-purpose",
                "drop_rate",
                f"drop_rate must be within 0..1, got {self.drop_rate}.",
            )
        ]


@dataclass
class ExplodingConfig:
    """A section whose own rule is buggy."""

    value: int = 1

    def validate(self) -> list[ValidationIssue]:
        """Raise, as a game's half-written rule eventually will."""
        raise RuntimeError("the game's rule is broken")


def _write(path, **sections):
    """Write a config document containing only the given sections."""
    path.write_text(json.dumps(sections))
    return path


# -- Registration --


def test_a_registered_section_is_usable_before_load():
    """Registering installs the declared defaults immediately, so a game
    whose config file does not exist yet still reads real values."""
    manager = ConfigManager()
    manager.register_section("balance", BalanceConfig)

    assert manager.section(BalanceConfig).drop_rate == 0.25
    assert manager.config.get_section("balance") is manager.section(BalanceConfig)


def test_a_reserved_name_is_refused():
    manager = ConfigManager()

    for name in ("display", "physics", "version", "custom", "profiles"):
        with pytest.raises(SectionRegistryError, match="reserved"):
            manager.register_section(name, BalanceConfig)


def test_re_registering_the_same_type_is_allowed_but_a_different_one_is_not():
    manager = ConfigManager()
    manager.register_section("balance", BalanceConfig)
    manager.register_section("balance", BalanceConfig)  # idempotent

    with pytest.raises(SectionRegistryError, match="already registered"):
        manager.register_section("balance", CheckedConfig)


def test_a_section_needing_constructor_arguments_is_refused():
    """Those defaults are what a missing file falls back to; without them
    there is nothing to fall back to."""

    @dataclass
    class NoDefaults:
        required: int

    manager = ConfigManager()
    with pytest.raises(SectionRegistryError, match="required"):
        manager.register_section("broken", NoDefaults)


def test_a_non_dataclass_is_refused():
    manager = ConfigManager()
    with pytest.raises(SectionRegistryError, match="dataclass"):
        manager.register_section("balance", dict)


def test_registering_after_load_raises_rather_than_discarding_file_values(tmp_path):
    """The file's `balance` block is already gone by then -- handing the game
    its defaults instead, silently, is the failure this prevents."""
    path = _write(tmp_path / "c.json", balance={"drop_rate": 0.9})
    manager = ConfigManager(file_path=path)
    manager.load()

    with pytest.raises(RuntimeError, match="after load"):
        manager.register_section("balance", BalanceConfig)


# -- Loading and saving --


def test_a_registered_section_round_trips_through_the_file(tmp_path):
    path = tmp_path / "c.json"
    manager = ConfigManager(file_path=path)
    manager.register_section("balance", BalanceConfig)
    manager.load()

    balance = manager.section(BalanceConfig)
    balance.drop_rate = 0.8
    balance.difficulty = Difficulty.HARD
    balance.accent = Color(1, 2, 3)
    assert manager.save()

    reloaded = ConfigManager(file_path=path)
    reloaded.register_section("balance", BalanceConfig)
    reloaded.load()

    restored = reloaded.section(BalanceConfig)
    assert restored.drop_rate == 0.8
    assert restored.difficulty is Difficulty.HARD
    assert restored.accent == Color(1, 2, 3)


def test_a_game_section_is_written_at_the_top_level(tmp_path):
    """Not nested under "custom": in the file a game's section must look no
    different from the engine's, or hand-editing it is a special case."""
    path = tmp_path / "c.json"
    manager = ConfigManager(file_path=path)
    manager.register_section("balance", BalanceConfig)
    manager.save()

    document = json.loads(path.read_text())
    assert "custom" not in document
    assert document["balance"]["drop_rate"] == 0.25


def test_file_values_beat_the_declared_defaults(tmp_path):
    path = _write(tmp_path / "c.json", balance={"boss_waves": 9})
    manager = ConfigManager(file_path=path)
    manager.register_section("balance", BalanceConfig)
    manager.load()

    assert manager.section(BalanceConfig).boss_waves == 9
    assert manager.section(BalanceConfig).drop_rate == 0.25


def test_an_unregistered_section_is_reported_by_name(tmp_path, caplog):
    """The usual cause is `register_section()` running after `load()`, which
    is otherwise completely silent."""
    path = _write(tmp_path / "c.json", balance={"drop_rate": 0.9})

    with caplog.at_level(logging.WARNING):
        ConfigManager(file_path=path).load()

    assert "balance" in caplog.text
    assert "register_section" in caplog.text


def test_a_section_that_is_not_an_object_keeps_its_defaults(tmp_path, caplog):
    path = _write(tmp_path / "c.json", balance=[1, 2, 3])
    manager = ConfigManager(file_path=path)
    manager.register_section("balance", BalanceConfig)

    with caplog.at_level(logging.WARNING):
        assert manager.load()

    assert manager.section(BalanceConfig).drop_rate == 0.25
    assert "should be an object" in caplog.text


def test_enums_anywhere_survive_to_dict_without_a_special_case(tmp_path):
    """`to_dict` used to hand-fix `display.backend` alone; a game's own enum
    field made `json.dump` raise."""
    manager = ConfigManager(file_path=tmp_path / "c.json")
    manager.register_section("balance", BalanceConfig)
    manager.section(BalanceConfig).difficulty = Difficulty.HARD

    document = manager.config.to_dict()
    assert document["balance"]["difficulty"] == "hard"
    json.dumps(document)  # would raise on a bare Enum


# -- Typed lookup --


def test_section_finds_engine_sections_too():
    manager = ConfigManager()
    assert manager.section(PhysicsConfig) is manager.config.physics


def test_section_names_an_absent_type_and_what_to_do():
    manager = ConfigManager()
    with pytest.raises(KeyError, match="register_section"):
        manager.section(BalanceConfig)


def test_section_names_list_engine_sections_first():
    manager = ConfigManager()
    manager.register_section("balance", BalanceConfig)

    assert manager.config.section_names() == [
        "display",
        "audio",
        "input",
        "physics",
        "debug",
        "balance",
    ]


# -- update_setting --


def test_update_setting_reaches_a_game_section(event_dispatcher):
    from pyguara.config.events import OnConfigurationChanged

    seen = []
    event_dispatcher.subscribe(OnConfigurationChanged, seen.append)

    manager = ConfigManager(event_dispatcher=event_dispatcher)
    manager.register_section("balance", BalanceConfig)

    assert manager.update_setting("balance", "boss_waves", 7)
    assert manager.section(BalanceConfig).boss_waves == 7
    assert seen[0].section == "balance"
    assert seen[0].old_value == 3


def test_update_setting_type_checks_a_game_section():
    manager = ConfigManager()
    manager.register_section("balance", BalanceConfig)

    assert not manager.update_setting("balance", "boss_waves", "many")
    assert not manager.update_setting("balance", "boss_waves", True)
    assert manager.section(BalanceConfig).boss_waves == 3


def test_update_setting_rejects_an_unknown_game_setting():
    manager = ConfigManager()
    manager.register_section("balance", BalanceConfig)

    assert not manager.update_setting("balance", "nope", 1)


# -- Validation --


def test_a_sections_own_rules_are_reported_under_its_registered_name():
    manager = ConfigManager()
    manager.register_section("checked", CheckedConfig)
    manager.section(CheckedConfig).drop_rate = 5.0

    issues = manager.validate()

    assert [i.section for i in issues] == ["checked"]
    assert issues[0].setting == "drop_rate"
    assert issues[0].severity is ValidationSeverity.ERROR


def test_a_section_without_rules_is_simply_unchecked():
    manager = ConfigManager()
    manager.register_section("balance", BalanceConfig)
    manager.section(BalanceConfig).drop_rate = -99.0

    assert manager.validate() == []


def test_update_setting_is_blocked_by_a_sections_own_rule():
    manager = ConfigManager()
    manager.register_section("checked", CheckedConfig)

    assert not manager.update_setting("checked", "drop_rate", 5.0)
    assert manager.section(CheckedConfig).drop_rate == 0.25
    assert manager.update_setting("checked", "drop_rate", 0.5)


def test_a_rule_that_raises_becomes_one_error_rather_than_a_crash(caplog):
    """A buggy rule in a game's config must not take down the startup path
    that was trying to report every other problem."""
    manager = ConfigManager()
    manager.register_section("boom", ExplodingConfig)

    with caplog.at_level(logging.ERROR):
        issues = manager.validate()

    assert len(issues) == 1
    assert issues[0].section == "boom"
    assert issues[0].severity is ValidationSeverity.ERROR
    assert "RuntimeError" in issues[0].message


# -- Environment overrides --


def test_a_game_section_is_overridable_from_the_environment(tmp_path, monkeypatch):
    path = _write(tmp_path / "c.json", balance={"drop_rate": 0.1})
    monkeypatch.setenv("PYGUARA_BALANCE_DROP_RATE", "0.75")
    monkeypatch.setenv("PYGUARA_BALANCE_BOSS_WAVES", "11")
    monkeypatch.setenv("PYGUARA_BALANCE_PERMADEATH", "yes")
    monkeypatch.setenv("PYGUARA_BALANCE_DIFFICULTY", "hard")

    manager = ConfigManager(file_path=path)
    manager.register_section("balance", BalanceConfig)
    manager.load()

    balance = manager.section(BalanceConfig)
    assert balance.drop_rate == 0.75
    assert balance.boss_waves == 11
    assert balance.permadeath is True
    assert balance.difficulty is Difficulty.HARD


def test_the_generic_form_works_for_engine_sections(tmp_path, monkeypatch):
    path = _write(tmp_path / "c.json")
    monkeypatch.setenv("PYGUARA_DISPLAY_FPS_TARGET", "144")
    monkeypatch.setenv("PYGUARA_AUDIO_MUTED", "true")

    manager = ConfigManager(file_path=path)
    manager.load()

    assert manager.config.display.fps_target == 144
    assert manager.config.audio.muted is True


def test_the_explicit_field_name_beats_the_short_alias(tmp_path, monkeypatch):
    """Both name `display.screen_width`; the one that says so wins."""
    path = _write(tmp_path / "c.json")
    monkeypatch.setenv("PYGUARA_WINDOW_WIDTH", "1920")
    monkeypatch.setenv("PYGUARA_DISPLAY_SCREEN_WIDTH", "2560")

    manager = ConfigManager(file_path=path)
    manager.load()

    assert manager.config.display.screen_width == 2560


def test_a_known_section_with_an_unknown_field_is_reported(
    tmp_path, monkeypatch, caplog
):
    """A mistyped field under a real section is a typo worth naming, unlike a
    variable that names no section at all."""
    path = _write(tmp_path / "c.json")
    monkeypatch.setenv("PYGUARA_DISPLAY_FPS_TARGEET", "144")

    with caplog.at_level(logging.WARNING):
        manager = ConfigManager(logger=get_logger("test.env"), file_path=path)
        manager.load()

    assert "PYGUARA_DISPLAY_FPS_TARGEET" in caplog.text
    assert "fps_target" in caplog.text


def test_an_unrelated_pyguara_variable_is_left_alone(tmp_path, monkeypatch, caplog):
    """It belongs to something else -- another tool, or one of the aliases."""
    path = _write(tmp_path / "c.json")
    monkeypatch.setenv("PYGUARA_SOMETHING_ELSE", "x")

    with caplog.at_level(logging.WARNING):
        manager = ConfigManager(logger=get_logger("test.env"), file_path=path)
        manager.load()

    assert "PYGUARA_SOMETHING_ELSE" not in caplog.text


def test_an_unparseable_bool_is_reported_and_skipped(tmp_path, monkeypatch, caplog):
    path = _write(tmp_path / "c.json")
    monkeypatch.setenv("PYGUARA_AUDIO_MUTED", "maybe")

    with caplog.at_level(logging.WARNING):
        manager = ConfigManager(logger=get_logger("test.env"), file_path=path)
        manager.load()

    assert manager.config.audio.muted is False
    assert "PYGUARA_AUDIO_MUTED" in caplog.text


def test_a_colour_is_refused_from_the_environment_rather_than_half_parsed(
    tmp_path, monkeypatch, caplog
):
    """There is no documented syntax for one, and inventing one here would be
    worse than saying so."""
    path = _write(tmp_path / "c.json")
    monkeypatch.setenv("PYGUARA_DISPLAY_DEFAULT_COLOR", "255,0,0")

    with caplog.at_level(logging.WARNING):
        manager = ConfigManager(logger=get_logger("test.env"), file_path=path)
        manager.load()

    assert manager.config.display.default_color == Color(0, 0, 0)
    assert "config file instead" in caplog.text


def test_a_first_run_file_holds_defaults_not_this_launchs_environment(
    tmp_path, monkeypatch
):
    """The written file is the game's to edit; an override belongs to one
    launch. Baking it in made `PYGUARA_BACKEND` permanent -- and before this,
    a missing file skipped overrides entirely, so the first launch ignored
    them."""
    path = tmp_path / "c.json"
    monkeypatch.setenv("PYGUARA_DISPLAY_FPS_TARGET", "144")

    manager = ConfigManager(file_path=path)
    assert manager.load()

    assert manager.config.display.fps_target == 144
    assert json.loads(path.read_text())["display"]["fps_target"] == 60


def test_from_dict_still_works_without_a_registry():
    """`GameConfig.from_dict(data)` is public and predates the registry."""
    config = GameConfig.from_dict({"display": {"fps_target": 30}})

    assert config.display.fps_target == 30
    assert config.custom == {}
