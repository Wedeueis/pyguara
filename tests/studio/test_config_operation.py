"""The `config` operation, its command, and the manager behind them.

The configuration is edited through the same session as the scene, so
what is checked here is what that buys: a refused value comes back with
its reason, an accepted one is on the history and undoes, and nothing
is written to disk until `save` is asked for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyguara.common.types import Color
from pyguara.config.manager import ConfigManager
from pyguara.config.types import LogLevel, RenderingBackend
from pyguara.ecs.manager import EntityManager
from pyguara.studio.commands.base import EditError
from pyguara.studio.commands.config import SetConfigSetting
from pyguara.studio.ops.registry import OperationRegistry
from pyguara.studio.session import ApprovalMode, EditorMode, StudioSession


@dataclass
class BalanceConfig:
    """A section a game registers."""

    drop_rate: float = 0.25
    waves: int = 3


@pytest.fixture
def manager(tmp_path: Path) -> ConfigManager:
    """A configuration at its defaults, with one game-defined section."""
    manager = ConfigManager(file_path=tmp_path / "game_config.json")
    manager.register_section("balance", BalanceConfig)
    return manager


@pytest.fixture
def session(populated: EntityManager, core_registry, manager) -> StudioSession:
    """A session that can reach the configuration."""
    return StudioSession(
        populated, component_registry=core_registry, config_manager=manager
    )


def call(ops: OperationRegistry, session: StudioSession, **arguments: object):
    """Invoke `config` and return the `OperationResult`."""
    return ops.invoke(session, "config", dict(arguments))


class TestGet:
    """Reading the configuration."""

    def test_it_reports_every_section(self, ops, session, manager) -> None:
        result = call(ops, session, operation="get")
        assert result.ok, result.error
        assert list(result.result["sections"]) == manager.config.section_names()
        assert "balance" in result.result["sections"]

    def test_a_setting_carries_type_value_and_default(self, ops, session) -> None:
        manager = session.config_manager
        manager.update_setting("physics", "substeps", 6)
        substeps = call(ops, session, operation="get", section="physics").result[
            "sections"
        ]["physics"]["substeps"]
        assert substeps["type"] == "int"
        assert substeps["value"] == 6
        assert substeps["default"] == 4

    def test_an_enum_lists_its_member_names(self, ops, session) -> None:
        backend = call(ops, session, operation="get", section="display").result[
            "sections"
        ]["display"]["backend"]
        assert set(backend["values"]) == set(RenderingBackend.__members__)

    def test_one_section_can_be_asked_for(self, ops, session) -> None:
        result = call(ops, session, operation="get", section="audio")
        assert list(result.result["sections"]) == ["audio"]

    def test_an_unknown_section_names_the_real_ones(self, ops, session) -> None:
        result = call(ops, session, operation="get", section="fisics")
        assert not result.ok
        assert "physics" in result.error

    def test_a_pinned_setting_says_which_profile(self, ops, session, manager) -> None:
        manager.define_profile("hard", {"physics": {"substeps": 9}})
        manager.push_profile("hard")
        result = call(ops, session, operation="get", section="physics").result
        assert result["active_profiles"] == ["hard"]
        assert result["sections"]["physics"]["substeps"]["pinned_by"] == "hard"

    def test_the_result_is_json(self, ops, session) -> None:
        json.dumps(call(ops, session, operation="get").result)


class TestSet:
    """Changing one setting."""

    def test_it_writes_the_live_config(self, ops, session, manager) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=8,
        )
        assert result.ok, result.error
        assert manager.config.physics.substeps == 8
        assert result.result["value"] == 8

    def test_it_undoes_and_redoes(self, ops, session, manager) -> None:
        call(
            ops,
            session,
            operation="set",
            section="audio",
            setting="master_volume",
            value=0.5,
        )
        session.undo()
        assert manager.config.audio.master_volume == 1.0
        session.redo()
        assert manager.config.audio.master_volume == 0.5

    def test_a_fraction_is_expressible(self, ops, session, manager) -> None:
        """The retired editor stepped by 1.0 and could not write this."""
        result = call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="penetration_recovery",
            value=0.016,
        )
        assert result.ok, result.error
        assert manager.config.physics.penetration_recovery == 0.016

    def test_an_enum_takes_a_member_name(self, ops, session, manager) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="debug",
            setting="log_level",
            value="DEBUG",
        )
        assert result.ok, result.error
        assert manager.config.debug.log_level is LogLevel.DEBUG

    def test_an_unknown_enum_member_names_the_valid_ones(self, ops, session) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="debug",
            setting="log_level",
            value="LOUD",
        )
        assert not result.ok
        assert "DEBUG" in result.error

    def test_a_colour_takes_its_channels(self, ops, session, manager) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="display",
            setting="default_color",
            value={"r": 10, "g": 20, "b": 30, "a": 255},
        )
        assert result.ok, result.error
        assert manager.config.display.default_color == Color(10, 20, 30)
        session.undo()
        assert manager.config.display.default_color == Color(0, 0, 0)

    def test_an_optional_setting_takes_a_value_and_null(
        self, ops, session, manager
    ) -> None:
        assert call(
            ops,
            session,
            operation="set",
            section="debug",
            setting="rng_seed",
            value=7,
        ).ok
        assert manager.config.debug.rng_seed == 7
        assert call(
            ops,
            session,
            operation="set",
            section="debug",
            setting="rng_seed",
            value=None,
        ).ok
        assert manager.config.debug.rng_seed is None

    def test_null_is_refused_where_the_setting_is_not_optional(
        self, ops, session, manager
    ) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=None,
        )
        assert not result.ok
        assert manager.config.physics.substeps == 4

    def test_a_wrong_type_is_refused_and_nothing_changes(
        self, ops, session, manager
    ) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value="many",
        )
        assert not result.ok
        assert manager.config.physics.substeps == 4
        assert not session.stack.can_undo

    def test_a_value_the_validator_blocks_carries_its_reason(
        self, ops, session, manager
    ) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="display",
            setting="screen_width",
            value=-5,
        )
        assert not result.ok
        assert "screen_width" in result.error
        assert manager.config.display.screen_width == 1200

    def test_a_misspelt_setting_gets_the_near_miss(self, ops, session) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substep",
            value=2,
        )
        assert not result.ok
        assert "Did you mean substeps" in result.error

    def test_a_game_section_is_editable(self, ops, session, manager) -> None:
        result = call(
            ops,
            session,
            operation="set",
            section="balance",
            setting="drop_rate",
            value=0.5,
        )
        assert result.ok, result.error
        assert manager.section(BalanceConfig).drop_rate == 0.5

    def test_a_pinned_setting_is_refused(self, ops, session, manager) -> None:
        manager.define_profile("hard", {"physics": {"substeps": 9}})
        manager.push_profile("hard")
        result = call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=2,
        )
        assert not result.ok
        assert "'hard'" in result.error
        assert manager.config.physics.substeps == 9

    def test_plan_mode_reports_and_changes_nothing(self, ops, session, manager) -> None:
        session.set_approval_mode(ApprovalMode.PLAN)
        result = call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=8,
        )
        assert result.ok, result.error
        assert result.result["status"] == "planned"
        assert manager.config.physics.substeps == 4

    def test_it_is_refused_while_the_game_plays(self, ops, session, manager) -> None:
        session.set_mode(EditorMode.PLAY)
        result = call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=8,
        )
        assert not result.ok
        assert manager.config.physics.substeps == 4

    def test_coalesced_edits_are_one_history_entry(self, ops, session, manager) -> None:
        for volume in (0.9, 0.8, 0.7):
            call(
                ops,
                session,
                operation="set",
                section="audio",
                setting="master_volume",
                value=volume,
                coalesce=True,
            )
        assert len(session.stack.undo_labels) == 1
        session.undo()
        assert manager.config.audio.master_volume == 1.0

    def test_the_edit_is_journaled(self, ops, session) -> None:
        call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=8,
        )
        entry = session.journal.entries[-1]
        assert entry.action == "config"
        assert entry.detail["from"] == 4 and entry.detail["to"] == 8


class TestSave:
    """Writing the file."""

    def test_nothing_reaches_disk_until_asked(self, ops, session, manager) -> None:
        call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=8,
        )
        assert not manager.file_path.exists()

    def test_save_writes_the_edited_value(self, ops, session, manager) -> None:
        call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=8,
        )
        result = call(ops, session, operation="save")
        assert result.ok, result.error
        assert result.result["saved"] == str(manager.file_path)
        written = json.loads(manager.file_path.read_text(encoding="utf-8"))
        assert written["physics"]["substeps"] == 8

    def test_save_keeps_the_history(self, ops, session) -> None:
        call(
            ops,
            session,
            operation="set",
            section="physics",
            setting="substeps",
            value=8,
        )
        call(ops, session, operation="save")
        assert session.stack.can_undo

    def test_save_under_a_profile_writes_the_values_underneath(
        self, ops, session, manager
    ) -> None:
        """A profile is for a while; the file is the next launch."""
        manager.define_profile("hard", {"physics": {"substeps": 9}})
        manager.push_profile("hard")
        result = call(ops, session, operation="save")
        assert result.ok, result.error
        written = json.loads(manager.file_path.read_text(encoding="utf-8"))
        assert written["physics"]["substeps"] == 4
        assert manager.config.physics.substeps == 9

    def test_a_failed_write_is_an_error(self, ops, session, manager, tmp_path) -> None:
        """A path under a regular file cannot be created."""
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        manager._file_path = blocker / "game_config.json"
        result = call(ops, session, operation="save")
        assert not result.ok
        assert "failed" in result.error


class TestTheOperationItself:
    """The edges of the dispatch."""

    def test_an_unknown_verb_names_the_valid_ones(self, ops, session) -> None:
        result = call(ops, session, operation="reset")
        assert not result.ok
        assert "get, set, save" in result.error

    def test_a_session_without_a_configuration_says_so(
        self, ops, populated, core_registry
    ) -> None:
        bare = StudioSession(populated, component_registry=core_registry)
        result = call(ops, bare, operation="get")
        assert not result.ok
        assert "config_manager" in result.error


class TestSetConfigSetting:
    """The command on its own."""

    def test_a_refused_value_raises_before_writing(
        self, manager: ConfigManager, world: EntityManager
    ) -> None:
        command = SetConfigSetting(manager, "display", "screen_width", -5)
        with pytest.raises(EditError):
            command.apply(world)
        assert not command.applied
        assert manager.config.display.screen_width == 1200

    def test_revert_raises_when_a_profile_took_the_setting(
        self, manager: ConfigManager, world: EntityManager
    ) -> None:
        """A revert that silently did nothing would report an undo that
        did not happen."""
        command = SetConfigSetting(manager, "physics", "substeps", 8)
        command.apply(world)
        manager.define_profile("hard", {"physics": {"substeps": 9}})
        manager.push_profile("hard")
        with pytest.raises(EditError, match="hard"):
            command.revert(world)

    def test_the_captured_colour_is_not_the_live_one(
        self, manager: ConfigManager, world: EntityManager
    ) -> None:
        live = manager.config.display.default_color
        command = SetConfigSetting(manager, "display", "default_color", Color(1, 2, 3))
        command.apply(world)
        assert command._previous == live
        assert command._previous is not live
