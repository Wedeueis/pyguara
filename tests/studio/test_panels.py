"""Studio's session panels, over real ImGui frames.

These four read session state rather than the scene: the edit history, the
action journal with its approval queue, the component schema browser, and
the command palette. The palette is the one that matters most
architecturally -- it is a person calling the same operations an agent
calls, through the same registry, which is why the registry exists at all
rather than a pile of panel methods.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.common.components import Transform  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.editor.panels.base import EditorPanel, PanelContext  # noqa: E402
from pyguara.editor.selection import Selection  # noqa: E402
from pyguara.studio.agent.journal import Actor  # noqa: E402
from pyguara.studio.commands.entity import SetEnabled, SetField  # noqa: E402
from pyguara.studio.ops.registry import OperationRegistry  # noqa: E402
from pyguara.studio.panels.history import HistoryPanel  # noqa: E402
from pyguara.studio.panels.journal import JournalPanel  # noqa: E402
from pyguara.studio.panels.palette import (  # noqa: E402
    MAX_RESULT_CHARS,
    CommandPalette,
)
from pyguara.studio.panels.schema import SchemaPanel  # noqa: E402
from pyguara.studio.session import ApprovalMode, StudioSession  # noqa: E402


@pytest.fixture
def gui() -> Iterator[None]:
    """An ImGui context with no renderer and no GL."""
    context = imgui.create_context()
    imgui.set_current_context(context)
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1280, 720)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.set_ini_filename("")
    yield
    imgui.destroy_context(context)


@pytest.fixture
def context(populated: EntityManager) -> PanelContext:
    """A panel context over the populated world."""
    selection = Selection()
    selection.select("root")
    return PanelContext(entity_manager=populated, selection=selection)


def draw(panel: EditorPanel, context: PanelContext, *, frames: int = 2) -> int:
    """Draw a panel for several frames and return the vertex count.

    More than one frame because an ImGui window has no content region on
    its first, so a single-frame test would exercise almost nothing.
    """
    total = 0
    for _ in range(frames):
        imgui.new_frame()
        imgui.set_next_window_pos(imgui.ImVec2(0, 0))
        imgui.set_next_window_size(imgui.ImVec2(600, 500))
        panel.draw(context)
        imgui.render()
        total = imgui.get_draw_data().total_vtx_count
    return total


class TestHistoryPanel:
    """The edit history as a rewindable list."""

    def test_it_draws_with_an_empty_history(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        assert draw(HistoryPanel(session), context) > 0

    def test_it_draws_with_entries(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        session.apply(SetField("root", Transform, "rotation", 1.0))
        assert draw(HistoryPanel(session), context) > 0

    def test_identical_labels_do_not_share_an_id(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        """Two edits to the same field read identically; without a pushed
        id, clicking either would act on the first."""
        for value in (1.0, 2.0, 3.0):
            session.apply(SetField("root", Transform, "rotation", value))
        assert session.stack.undo_labels.count("Set Transform.rotation on root") == 3
        assert draw(HistoryPanel(session), context) > 0

    def test_entries_are_listed_oldest_first(
        self, gui: None, session: StudioSession
    ) -> None:
        """So the index a user clicks stays put as new edits arrive at the
        end. A newest-first list renumbers everything on every edit."""
        session.apply(SetEnabled("root", False))
        session.apply(SetEnabled("child_a", False))
        assert session.stack.undo_labels == (
            "Disable root",
            "Disable child_a",
        )

    def test_undo_to_is_tolerant_of_a_moved_history(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        """Another panel, or an agent, may have undone something between
        the click and the call."""
        panel = HistoryPanel(session)
        session.apply(SetEnabled("root", False))
        session.stack.clear()
        panel._undo_to(5)


class TestJournalPanel:
    """The action record and the approval queue."""

    def test_it_draws_when_empty(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        assert draw(JournalPanel(session), context) > 0

    def test_it_draws_entries(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        session.apply(SetEnabled("root", False), actor=Actor.AGENT)
        assert draw(JournalPanel(session), context) > 0

    def test_it_draws_failures(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        session.journal.record(Actor.AGENT, "boom", ok=False, error="no")
        assert draw(JournalPanel(session), context) > 0

    def test_the_failures_filter_narrows_the_list(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        """How a person finds the moment something went wrong without
        reading every entry of an agent run."""
        session.apply(SetEnabled("root", False), actor=Actor.AGENT)
        session.journal.record(Actor.AGENT, "boom", ok=False, error="no")

        panel = JournalPanel(session)
        panel._failures_only = True
        assert draw(panel, context) > 0
        assert len(session.journal.failures()) == 1

    def test_it_draws_the_pending_queue(
        self, gui: None, populated: EntityManager, core_registry, context: PanelContext
    ) -> None:
        asking = StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.ASK,
        )
        asking.apply(SetField("root", Transform, "rotation", 1.0))

        assert draw(JournalPanel(asking), context) > 0
        assert len(asking.pending) == 1

    def test_approving_through_the_panel_applies_the_edit(
        self, gui: None, populated: EntityManager, core_registry
    ) -> None:
        asking = StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.ASK,
        )
        outcome = asking.apply(SetEnabled("root", False))
        assert outcome.pending_id is not None

        JournalPanel(asking)._approve(outcome.pending_id)

        assert populated.is_entity_enabled("root") is False

    def test_approving_a_stale_edit_does_not_raise(
        self, gui: None, populated: EntityManager, core_registry
    ) -> None:
        """A refused approval is the intended behaviour, not an error to
        take the frame down with."""
        asking = StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.ASK,
        )
        JournalPanel(asking)._approve("nonexistent")

    def test_rejecting_through_the_panel_discards_the_edit(
        self, gui: None, populated: EntityManager, core_registry
    ) -> None:
        asking = StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.ASK,
        )
        outcome = asking.apply(SetEnabled("root", False))
        assert outcome.pending_id is not None

        JournalPanel(asking)._reject(outcome.pending_id)

        assert populated.is_entity_enabled("root") is True
        assert asking.pending == ()

    def test_rejecting_an_unknown_edit_does_not_raise(
        self, gui: None, session: StudioSession
    ) -> None:
        JournalPanel(session)._reject("nonexistent")

    def test_the_diff_summary_handles_every_section(
        self, gui: None, session: StudioSession, context: PanelContext
    ) -> None:
        """A reviewer needs what moved; a wall of JSON is how a review
        becomes a rubber stamp."""
        panel = JournalPanel(session)
        imgui.new_frame()
        imgui.begin("t")
        panel._draw_diff(
            {
                "changed": True,
                "added": ["a"],
                "removed": ["b"],
                "tags_changed": ["c"],
                "enabled_changed": ["d"],
                "reparented": ["e"],
                "components_added": [{"entity": "a", "component": "Tag"}],
                "components_removed": [{"entity": "b", "component": "Tag"}],
                "fields": [
                    {
                        "entity": "a",
                        "component": "Transform",
                        "field": "rotation",
                        "before": 0,
                        "after": 1,
                    }
                ],
            }
        )
        panel._draw_diff({"changed": False})
        imgui.end()
        imgui.render()


class TestSchemaPanel:
    """The component reference."""

    def test_it_lists_every_registered_component(
        self, gui: None, core_registry, context: PanelContext
    ) -> None:
        panel = SchemaPanel(core_registry)
        assert draw(panel, context) > 0
        assert len(panel._resolve_schemas()) == len(core_registry.list_components())

    def test_the_schemas_are_cached_between_frames(
        self, gui: None, core_registry, context: PanelContext
    ) -> None:
        """`describe_registry` calls `get_type_hints` per component, which
        is far too slow to run every frame."""
        panel = SchemaPanel(core_registry)
        first = panel._resolve_schemas()
        assert panel._resolve_schemas() is first

    def test_a_newly_registered_component_invalidates_the_cache(
        self, gui: None, core_registry, context: PanelContext
    ) -> None:
        """A game registers its own components after bootstrap."""
        from dataclasses import dataclass

        from pyguara.ecs.component import BaseComponent

        @dataclass
        class Late(BaseComponent):
            """A component registered after the panel was built."""

            value: int = 0

            def __post_init__(self) -> None:
                BaseComponent.__init__(self)

        panel = SchemaPanel(core_registry)
        panel._resolve_schemas()
        core_registry.register(Late)

        assert "Late" in panel._resolve_schemas()

    def test_the_filter_narrows_the_list(
        self, gui: None, core_registry, context: PanelContext
    ) -> None:
        panel = SchemaPanel(core_registry)
        panel._filter = "transf"
        assert draw(panel, context) > 0

    def test_a_filter_matching_nothing_draws(
        self, gui: None, core_registry, context: PanelContext
    ) -> None:
        panel = SchemaPanel(core_registry)
        panel._filter = "zzzzzzzz"
        assert draw(panel, context) > 0

    def test_it_is_hidden_by_default(self, gui: None, core_registry) -> None:
        """A reference, consulted rather than watched."""
        assert SchemaPanel(core_registry).visible is False


class TestCommandPalette:
    """A person calling the operations an agent calls."""

    def test_it_draws(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        assert draw(CommandPalette(session, ops), context) > 0

    def test_selecting_an_operation_prefills_the_selection(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        """Covers most of what a palette is used for, without pretending
        to generate a form."""
        palette = CommandPalette(session, ops)
        palette._select("get_entity", context)

        assert palette.selected == "get_entity"
        assert '"entity_id": "root"' in palette._arguments

    def test_an_operation_without_an_entity_argument_prefills_nothing(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._select("scene_summary", context)
        assert palette._arguments.strip() == "{}"

    def test_running_an_operation_produces_a_result(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._select("scene_summary", context)
        palette._run()

        assert palette._result is not None
        assert palette._result.ok is True

    def test_running_an_edit_goes_through_the_session(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
        populated: EntityManager,
    ) -> None:
        """The palette is not a second mutation path -- it is the same
        registry, so the edit is undoable and journaled like any other."""
        palette = CommandPalette(session, ops)
        palette._select("set_enabled", context)
        palette._arguments = '{"entity_id": "root", "enabled": false}'
        palette._run()

        assert populated.is_entity_enabled("root") is False
        assert session.stack.can_undo is True

    def test_a_palette_edit_is_attributed_to_the_human(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._select("set_enabled", context)
        palette._arguments = '{"entity_id": "root", "enabled": false}'
        palette._run()

        assert session.journal.entries[-1].actor is Actor.HUMAN

    def test_invalid_json_is_reported_in_the_panel(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        """Rather than sent to the registry, where it would come back as a
        less specific complaint about the argument shape."""
        palette = CommandPalette(session, ops)
        palette._select("scene_summary", context)
        palette._arguments = "{not json"
        palette._run()

        assert palette._argument_error is not None
        assert "Not valid JSON" in palette._argument_error
        assert palette._result is None

    def test_a_json_array_is_refused(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._select("scene_summary", context)
        palette._arguments = "[1, 2]"
        palette._run()

        assert palette._argument_error is not None
        assert "must be a JSON object" in palette._argument_error

    def test_empty_arguments_mean_an_empty_object(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._select("scene_summary", context)
        palette._arguments = "   "
        palette._run()

        assert palette._result is not None
        assert palette._result.ok is True

    def test_a_failed_operation_shows_its_error(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._select("get_entity", context)
        palette._arguments = '{"entity_id": "nope"}'
        palette._run()

        assert palette._result is not None
        assert palette._result.ok is False
        assert draw(palette, context) > 0

    def test_a_large_result_is_truncated(
        self, gui: None, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """`scene_tree` on a real scene is far larger than a panel, and
        rendering all of it costs a frame to produce something nobody
        reads."""
        rendered = CommandPalette._render({"items": ["x" * 100] * 200})
        assert len(rendered) < MAX_RESULT_CHARS + 100
        assert "truncated" in rendered

    def test_a_small_result_is_not_truncated(self) -> None:
        assert "truncated" not in CommandPalette._render({"a": 1})

    def test_the_filter_narrows_the_list(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._filter = "entity"
        assert draw(palette, context) > 0

    def test_a_filter_matching_nothing_draws(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._filter = "zzzzzzzz"
        assert draw(palette, context) > 0

    def test_spaces_in_the_filter_match_underscores(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        """Nobody types `set_field` when hunting for "set field"."""
        palette = CommandPalette(session, ops)
        palette._filter = "set field"
        assert draw(palette, context) > 0

    def test_a_removed_operation_deselects_cleanly(
        self,
        gui: None,
        session: StudioSession,
        ops: OperationRegistry,
        context: PanelContext,
    ) -> None:
        palette = CommandPalette(session, ops)
        palette._select("scene_summary", context)
        palette._selected = "gone"
        draw(palette, context)
        assert palette.selected is None

    def test_it_is_hidden_by_default(
        self, gui: None, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """Summoned, not watched."""
        assert CommandPalette(session, ops).visible is False
