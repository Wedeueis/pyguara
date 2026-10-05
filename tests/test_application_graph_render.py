"""`Application`'s frame loop: world-buffer rebinding and the overlay hook.

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
from pyguara.application.sandbox import SandboxApplication


def _bare_app(app: Application, *, graph: MagicMock | None) -> Application:
    """Wire the collaborators the render path touches, nothing more."""
    app._render_graph = graph
    app._scene_manager = MagicMock()
    app._config_manager = MagicMock()
    app._world_renderer = MagicMock()
    app._ui_renderer = MagicMock()
    app._ui_manager = MagicMock()
    app._window = MagicMock()
    # `_render()` reads these to compute the interpolation alpha.
    app._accumulator = 0.0
    app._fixed_dt = 1.0 / 60.0
    return app


def _graph_with(*passes: MagicMock) -> MagicMock:
    """A render graph whose pass list is exactly `passes`."""
    graph = MagicMock()
    graph.fbo_manager.get_or_create.return_value = MagicMock(name="world_fbo")
    graph.passes = list(passes)
    return graph


def _a_pass(name: str, *, enabled: bool = True) -> MagicMock:
    """A render pass that records whether it executed."""
    render_pass = MagicMock(name=f"pass:{name}")
    render_pass.name = name
    render_pass.enabled = enabled
    return render_pass


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


class TestOverlayHook:
    """The seam `SandboxApplication` uses instead of restating the frame loop.

    It used to override `_render()` wholesale, which dropped the render graph
    and the game's `UIManager` from every sandbox frame.
    """

    def test_the_base_application_draws_no_overlays(self) -> None:
        """Nothing by default -- a plain game pays nothing for the hook."""
        app = _bare_app(Application.__new__(Application), graph=None)
        app._render_overlays()  # must not raise, and must do nothing

    def test_overlays_draw_after_the_game_ui_on_the_graph_path(self) -> None:
        order: list[str] = []
        app = _bare_app(Application.__new__(Application), graph=_graph_with())
        app._ui_manager.render.side_effect = lambda _r: order.append("game-ui")
        app._ui_renderer.present.side_effect = lambda: order.append("present")
        app._render_overlays = lambda: order.append("overlays")  # type: ignore[method-assign]

        app._render_with_graph(1.0)

        assert order == ["game-ui", "overlays", "present"]

    def test_overlays_draw_after_the_game_ui_on_the_direct_path(self) -> None:
        """Both paths, or an overlay appears on one backend only."""
        order: list[str] = []
        app = _bare_app(Application.__new__(Application), graph=None)
        app._ui_manager.render.side_effect = lambda _r: order.append("game-ui")
        app._ui_renderer.present.side_effect = lambda: order.append("present")
        app._render_overlays = lambda: order.append("overlays")  # type: ignore[method-assign]

        app._render_direct(1.0)

        assert order == ["game-ui", "overlays", "present"]

    def test_overlays_draw_before_the_renderer_presents(self) -> None:
        """An overlay drawn after `present()` is composited into nothing on a
        GL backend."""
        app = _bare_app(Application.__new__(Application), graph=None)
        presented: list[bool] = []
        app._ui_renderer.present.side_effect = lambda: presented.append(True)
        app._render_overlays = lambda: presented.append(False)  # type: ignore[method-assign]

        app._render_direct(1.0)

        assert presented == [False, True]


class TestSandboxUsesTheInheritedFrameLoop:
    """The three things `SandboxApplication._render` used to get wrong.

    Every test here enters through `_render()`, the real frame-loop entry
    point. Calling `_render_with_graph()` directly would pass even on the
    buggy code -- the bug was never that the graph path was broken, it was
    that the sandbox's own `_render()` never routed to it.
    """

    def test_it_no_longer_overrides_the_frame_loop(self) -> None:
        assert "_render" not in vars(SandboxApplication)

    def test_the_sandbox_executes_render_graph_passes(self) -> None:
        """The headline bug: it executed none, so on the ModernGL backend the
        sandbox skipped lighting, compositing, post-processing and `final`."""
        light = _a_pass("light")
        final = _a_pass("final")
        app = _bare_app(
            SandboxApplication.__new__(SandboxApplication),
            graph=_graph_with(light, final),
        )
        app._tool_manager = MagicMock()

        app._render()

        light.execute.assert_called_once()
        final.execute.assert_called_once()

    def test_the_sandbox_renders_the_games_own_ui(self) -> None:
        """Second bug: it called `ToolManager.render()` but never
        `UIManager.render()`, so no game UI widget drew under the sandbox."""
        app = _bare_app(
            SandboxApplication.__new__(SandboxApplication), graph=_graph_with()
        )
        app._tool_manager = MagicMock()

        app._render()

        app._ui_manager.render.assert_called_once_with(app._ui_renderer)

    def test_the_tool_overlay_still_draws_on_top(self) -> None:
        order: list[str] = []
        app = _bare_app(
            SandboxApplication.__new__(SandboxApplication), graph=_graph_with()
        )
        app._tool_manager = MagicMock()
        app._ui_manager.render.side_effect = lambda _r: order.append("game-ui")
        app._tool_manager.render.side_effect = lambda _r: order.append("tools")

        app._render()

        assert order == ["game-ui", "tools"]

    def test_no_tool_manager_is_not_an_error(self) -> None:
        """`_tool_manager` is None until `_initialize_tools()` runs."""
        app = _bare_app(
            SandboxApplication.__new__(SandboxApplication), graph=_graph_with()
        )
        app._tool_manager = None

        app._render()

        app._ui_manager.render.assert_called_once()

    def test_a_disabled_pass_is_still_skipped(self) -> None:
        skipped = _a_pass("post", enabled=False)
        app = _bare_app(
            SandboxApplication.__new__(SandboxApplication), graph=_graph_with(skipped)
        )
        app._tool_manager = MagicMock()

        app._render()

        skipped.execute.assert_not_called()
