from unittest.mock import MagicMock, patch
from pyguara.application.sandbox import SandboxApplication
from pyguara.editor.layer import EditorTool
from pyguara.di.container import DIContainer
from pyguara.graphics.window import Window

def test_editor_tool_registration():
    """Verify that EditorTool is registered in SandboxApplication."""
    # Setup Mock Container
    container = MagicMock()
    container.get.return_value = MagicMock()
    container.get(Window).is_open = True
    
    # SandboxApplication calls _initialize_tools in __init__
    app = SandboxApplication(container)
    
    # Check if EditorTool is in tool manager
    tool_manager = app._tool_manager
    assert tool_manager is not None
    assert tool_manager.get_tool("Editor") is not None

def test_editor_tool_logic():
    """Verify EditorTool methods."""
    container = MagicMock()
    tool = EditorTool(container)
    
    assert tool.name == "Editor"
    assert hasattr(tool, "render")
    assert hasattr(tool, "process_event")