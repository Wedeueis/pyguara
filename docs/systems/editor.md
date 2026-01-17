# Editor & Tools

PyGuara includes a built-in developer overlay (`pyguara.editor` & `pyguara.tools`) powered by **Dear ImGui**.

## Tool Manager

The `ToolManager` coordinates all debug tools. It handles:
*   **Visibility**: Toggling the global overlay (Default: **F12**).
*   **Input**: Routing mouse/keyboard events to tools before the game, allowing UI interaction without triggering game actions.

## The Editor

The Editor is a comprehensive debugging suite featuring:

*   **Hierarchy Panel**: View the current scene's entity tree.
*   **Inspector Panel**: View and edit Components on selected entities in real-time.
    *   **Reflection**: Automatically generates UI for any `dataclass` component.
    *   **Live Editing**: Changes apply immediately to the running game.
*   **Assets Panel**: Browse project resources and spawn entities from data.
*   **Scene Serialization**: Save and Load scenes directly from the "File" menu.

## Creating Custom Tools

You can create custom debug tools by inheriting from `Tool`:

```python
from pyguara.tools.base import Tool
import imgui

class MyDebugTool(Tool):
    def __init__(self, container):
        super().__init__("My Tool", container)

    def render(self, renderer):
        imgui.begin("My Custom Window")
        imgui.text("Hello World")
        imgui.end()
```
