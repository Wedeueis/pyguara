"""`Application` re-binds the world buffer before every stacked scene draws.

Scenes draw immediately into whatever framebuffer is bound. A scene lower
in the stack that executes a render-graph pass itself leaves that pass's
output bound; the scene above then drew its whole frame into it instead of
"world", and nothing it drew ever reached the screen. That is how
`quintal_cerrado`'s garden, pushed over its title screen, showed an empty
backdrop where the plot should be.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pyguara.application.application import Application


def test_the_world_buffer_is_rebound_before_each_scene() -> None:
    app = Application.__new__(Application)
    world_fbo = MagicMock(name="world_fbo")
    graph = MagicMock()
    graph.fbo_manager.get_or_create.return_value = world_fbo
    graph.passes = []
    app._render_graph = graph
    app._scene_manager = MagicMock()
    app._config_manager = MagicMock()
    app._world_renderer = MagicMock()
    app._ui_renderer = MagicMock()
    app._ui_manager = MagicMock()
    app._window = MagicMock()

    app._render_with_graph(1.0)

    graph.fbo_manager.get_or_create.assert_called_with("world")
    _, kwargs = app._scene_manager.render.call_args
    assert kwargs["before_each"] == world_fbo.bind
