"""The PyGuara editor: Dear ImGui panels over the engine's ModernGL context.

A development surface, attached explicitly:

```python
from pyguara.application.bootstrap import create_application
from pyguara.editor import attach_editor

app = create_application()
attach_editor(app.container)
app.run(MyScene("game", dispatcher))
```

ModernGL-only by design. It draws through the GL context the render graph
owns; the Pygame backend's window is a software surface with no context, so
`attach_editor()` declines there and the `pyguara/tools` overlay stays the
dev surface on that backend. The two are independent -- attaching the
editor changes nothing about `pyguara/tools`.

This is a **second**, deliberate attempt. The first `pyguara/editor` was
deleted in the subsystem audit because it had never executed: it imported
pyimgui's pygame integration, which needs PyOpenGL, which was a dependency
nowhere. See `availability.py` for what is different this time, and
`renderer.py` for why the draw data goes through `moderngl` instead.
"""

from pyguara.editor.attach import attach_editor
from pyguara.editor.availability import (
    IMGUI_AVAILABLE,
    IMGUI_IMPORT_ERROR,
    require_imgui,
)
from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.editor.selection import Selection

__all__ = [
    "IMGUI_AVAILABLE",
    "IMGUI_IMPORT_ERROR",
    "EditorPanel",
    "PanelContext",
    "Selection",
    "attach_editor",
    "require_imgui",
]
