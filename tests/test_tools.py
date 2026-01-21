"""Tests for developer tools system."""

import pytest
from unittest.mock import MagicMock, create_autospec
from typing import Any

import pygame

from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool
from pyguara.tools.manager import ToolManager


class MockTool(Tool):
    """Concrete implementation of Tool for testing."""

    def __init__(
        self, name: str, container: DIContainer, consume_events: bool = False
    ) -> None:
        super().__init__(name, container)
        self.update_called = False
        self.render_called = False
        self.event_processed = False
        self._consume_events = consume_events

    def update(self, dt: float) -> None:
        self.update_called = True
        self.last_dt = dt

    def render(self, renderer: UIRenderer) -> None:
        self.render_called = True

    def process_event(self, event: Any) -> bool:
        self.event_processed = True
        return self._consume_events


@pytest.fixture
def container() -> DIContainer:
    """Create a DI container for testing."""
    return DIContainer()


@pytest.fixture
def mock_renderer() -> MagicMock:
    """Create a mock UI renderer."""
    return create_autospec(UIRenderer)


class TestToolBase:
    """Test the Tool base class."""

    def test_tool_creation(self, container: DIContainer) -> None:
        """Tool can be instantiated with name and container."""
        tool = MockTool("test_tool", container)
        assert tool.name == "test_tool"
        assert tool._container is container

    def test_tool_default_state(self, container: DIContainer) -> None:
        """Tool starts visible and active by default."""
        tool = MockTool("test", container)
        assert tool.is_visible is True
        assert tool.is_active is True

    def test_tool_show_hide(self, container: DIContainer) -> None:
        """Tool visibility can be controlled."""
        tool = MockTool("test", container)

        tool.hide()
        assert tool.is_visible is False

        tool.show()
        assert tool.is_visible is True

    def test_tool_toggle(self, container: DIContainer) -> None:
        """Tool toggle flips visibility."""
        tool = MockTool("test", container)
        assert tool.is_visible is True

        tool.toggle()
        assert tool.is_visible is False

        tool.toggle()
        assert tool.is_visible is True

    def test_tool_update_called(self, container: DIContainer) -> None:
        """Tool update method receives delta time."""
        tool = MockTool("test", container)
        tool.update(0.016)

        assert tool.update_called is True
        assert tool.last_dt == 0.016

    def test_tool_render_called(
        self, container: DIContainer, mock_renderer: MagicMock
    ) -> None:
        """Tool render method is called."""
        tool = MockTool("test", container)
        tool.render(mock_renderer)

        assert tool.render_called is True

    def test_tool_process_event_default(self, container: DIContainer) -> None:
        """Tool process_event returns False by default (doesn't consume)."""
        tool = MockTool("test", container, consume_events=False)
        event = MagicMock()

        result = tool.process_event(event)

        assert result is False
        assert tool.event_processed is True


class TestToolManager:
    """Test the ToolManager class."""

    def test_manager_creation(self, container: DIContainer) -> None:
        """ToolManager can be created."""
        manager = ToolManager(container)
        assert manager._container is container
        assert manager._tools == {}

    def test_register_tool(self, container: DIContainer) -> None:
        """Tools can be registered with the manager."""
        manager = ToolManager(container)
        tool = MockTool("test_tool", container)

        manager.register_tool(tool)

        assert "test_tool" in manager._tools
        assert manager._tools["test_tool"] is tool

    def test_register_tool_with_shortcut(self, container: DIContainer) -> None:
        """Tools can be registered with keyboard shortcuts."""
        manager = ToolManager(container)
        tool = MockTool("test_tool", container)

        manager.register_tool(tool, shortcut_key=pygame.K_F1)

        assert pygame.K_F1 in manager._shortcuts
        assert manager._shortcuts[pygame.K_F1] == "test_tool"

    def test_registered_tool_starts_hidden(self, container: DIContainer) -> None:
        """Registered tools start hidden by default."""
        manager = ToolManager(container)
        tool = MockTool("test_tool", container)
        tool.show()  # Ensure it's visible first

        manager.register_tool(tool)

        assert tool.is_visible is False

    def test_get_tool(self, container: DIContainer) -> None:
        """Tools can be retrieved by name."""
        manager = ToolManager(container)
        tool = MockTool("my_tool", container)
        manager.register_tool(tool)

        retrieved = manager.get_tool("my_tool")

        assert retrieved is tool

    def test_get_nonexistent_tool(self, container: DIContainer) -> None:
        """Getting nonexistent tool returns None."""
        manager = ToolManager(container)

        result = manager.get_tool("does_not_exist")

        assert result is None

    def test_update_active_tools(self, container: DIContainer) -> None:
        """Update calls update on active tools."""
        manager = ToolManager(container)
        tool = MockTool("active_tool", container)
        manager.register_tool(tool)

        manager.update(0.016)

        assert tool.update_called is True

    def test_update_skips_inactive_tools(self, container: DIContainer) -> None:
        """Update skips inactive tools."""
        manager = ToolManager(container)
        tool = MockTool("inactive_tool", container)
        tool._is_active = False
        manager.register_tool(tool)

        manager.update(0.016)

        assert tool.update_called is False

    def test_render_when_globally_visible(
        self, container: DIContainer, mock_renderer: MagicMock
    ) -> None:
        """Render calls render on visible tools when globally visible."""
        manager = ToolManager(container)
        tool = MockTool("visible_tool", container)
        manager.register_tool(tool)
        tool.show()
        manager._is_globally_visible = True

        manager.render(mock_renderer)

        assert tool.render_called is True

    def test_render_skipped_when_globally_hidden(
        self, container: DIContainer, mock_renderer: MagicMock
    ) -> None:
        """Render skips all tools when globally hidden."""
        manager = ToolManager(container)
        tool = MockTool("tool", container)
        manager.register_tool(tool)
        tool.show()
        manager._is_globally_visible = False

        manager.render(mock_renderer)

        assert tool.render_called is False

    def test_render_skips_hidden_tools(
        self, container: DIContainer, mock_renderer: MagicMock
    ) -> None:
        """Render skips individually hidden tools."""
        manager = ToolManager(container)
        tool = MockTool("hidden_tool", container)
        manager.register_tool(tool)
        tool.hide()
        manager._is_globally_visible = True

        manager.render(mock_renderer)

        assert tool.render_called is False

    def test_toggle_global_visibility(self, container: DIContainer) -> None:
        """Global visibility can be toggled."""
        manager = ToolManager(container)

        assert manager._is_globally_visible is False

        manager.toggle_global_visibility()
        assert manager._is_globally_visible is True

        manager.toggle_global_visibility()
        assert manager._is_globally_visible is False


class TestToolManagerEvents:
    """Test event handling in ToolManager."""

    def test_f12_toggles_global_visibility(self, container: DIContainer) -> None:
        """F12 key toggles global visibility."""
        manager = ToolManager(container)
        event = MagicMock()
        event.type = pygame.KEYDOWN
        event.key = pygame.K_F12

        assert manager._is_globally_visible is False

        result = manager.process_event(event)

        assert result is True
        assert manager._is_globally_visible is True

    def test_shortcut_toggles_tool_when_globally_visible(
        self, container: DIContainer
    ) -> None:
        """Shortcut key toggles tool when overlay is visible."""
        manager = ToolManager(container)
        tool = MockTool("test_tool", container)
        manager.register_tool(tool, shortcut_key=pygame.K_F1)
        manager._is_globally_visible = True

        event = MagicMock()
        event.type = pygame.KEYDOWN
        event.key = pygame.K_F1

        # Tool starts hidden after registration
        assert tool.is_visible is False

        result = manager.process_event(event)

        assert result is True
        assert tool.is_visible is True

    def test_shortcut_ignored_when_globally_hidden(
        self, container: DIContainer
    ) -> None:
        """Shortcut keys are ignored when global overlay is hidden."""
        manager = ToolManager(container)
        tool = MockTool("test_tool", container)
        manager.register_tool(tool, shortcut_key=pygame.K_F1)
        manager._is_globally_visible = False

        event = MagicMock()
        event.type = pygame.KEYDOWN
        event.key = pygame.K_F1

        result = manager.process_event(event)

        # Only F12 should work when globally hidden
        assert result is False

    def test_events_passed_to_tools_in_reverse_order(
        self, container: DIContainer
    ) -> None:
        """Events are passed to tools in reverse render order."""
        manager = ToolManager(container)
        manager._is_globally_visible = True

        tool1 = MockTool("tool1", container, consume_events=False)
        tool2 = MockTool("tool2", container, consume_events=True)  # Will consume

        manager.register_tool(tool1)
        manager.register_tool(tool2)
        tool1.show()
        tool2.show()

        event = MagicMock()
        event.type = pygame.MOUSEBUTTONDOWN

        result = manager.process_event(event)

        # tool2 was registered last, so it's checked first (reverse order)
        # It consumes the event, so tool1 shouldn't see it
        assert result is True
        assert tool2.event_processed is True
        assert tool1.event_processed is False

    def test_events_skipped_for_inactive_tools(self, container: DIContainer) -> None:
        """Events are skipped for inactive tools."""
        manager = ToolManager(container)
        manager._is_globally_visible = True

        tool = MockTool("inactive_tool", container, consume_events=True)
        manager.register_tool(tool)
        tool.show()
        tool._is_active = False

        event = MagicMock()
        event.type = pygame.MOUSEBUTTONDOWN

        result = manager.process_event(event)

        assert result is False
        assert tool.event_processed is False


class TestToolManagerRenderOrder:
    """Test render order behavior."""

    def test_tools_render_in_registration_order(
        self, container: DIContainer, mock_renderer: MagicMock
    ) -> None:
        """Tools are rendered in the order they were registered."""
        manager = ToolManager(container)
        manager._is_globally_visible = True

        render_order = []

        class OrderedTool(MockTool):
            def render(self, renderer: UIRenderer) -> None:
                render_order.append(self.name)

        tool1 = OrderedTool("first", container)
        tool2 = OrderedTool("second", container)
        tool3 = OrderedTool("third", container)

        manager.register_tool(tool1)
        manager.register_tool(tool2)
        manager.register_tool(tool3)

        tool1.show()
        tool2.show()
        tool3.show()

        manager.render(mock_renderer)

        assert render_order == ["first", "second", "third"]


class TestMultipleTools:
    """Test scenarios with multiple tools."""

    def test_register_multiple_tools(self, container: DIContainer) -> None:
        """Multiple tools can be registered."""
        manager = ToolManager(container)

        tools = [MockTool(f"tool_{i}", container) for i in range(5)]
        for tool in tools:
            manager.register_tool(tool)

        assert len(manager._tools) == 5
        assert len(manager._render_order) == 5

    def test_multiple_shortcuts(self, container: DIContainer) -> None:
        """Multiple tools can have different shortcuts."""
        manager = ToolManager(container)

        tool1 = MockTool("perf", container)
        tool2 = MockTool("inspector", container)
        tool3 = MockTool("events", container)

        manager.register_tool(tool1, pygame.K_F1)
        manager.register_tool(tool2, pygame.K_F2)
        manager.register_tool(tool3, pygame.K_F3)

        assert manager._shortcuts[pygame.K_F1] == "perf"
        assert manager._shortcuts[pygame.K_F2] == "inspector"
        assert manager._shortcuts[pygame.K_F3] == "events"

    def test_update_multiple_tools(self, container: DIContainer) -> None:
        """Update is called on all active tools."""
        manager = ToolManager(container)

        tools = [MockTool(f"tool_{i}", container) for i in range(3)]
        for tool in tools:
            manager.register_tool(tool)

        manager.update(0.016)

        assert all(tool.update_called for tool in tools)
