"""Opt-in wiring that puts the editor into a running application.

Not done by `create_application()`: the editor is a development surface,
and a shipped game should not pay for an ImGui context it never shows. A
game or tool asks for it explicitly.
"""

from __future__ import annotations

from typing import cast

from pyguara.di.container import DIContainer
from pyguara.editor.availability import IMGUI_AVAILABLE, IMGUI_IMPORT_ERROR
from pyguara.editor.panels.base import EditorPanel
from pyguara.log import get_logger

logger = get_logger(__name__)


def attach_editor(
    container: DIContainer,
    *,
    panels: list[EditorPanel] | None = None,
) -> object | None:
    """Add the ImGui editor to the container's render graph.

    The editor is ModernGL-only by construction: it draws through the GL
    context the render graph owns, and the Pygame backend has none -- its
    `PygameRenderGraph` is a stub whose `ctx` is `None`, and the window it
    opens is a software surface (`pygame_window.py` actively strips
    `pygame.OPENGL` to keep it one). On that backend this returns `None`
    rather than half-installing, and the `pyguara/tools` overlay remains
    the dev surface there.

    Args:
        container: The engine container. Must already have a `RenderGraph`
            registered, which `create_application()` does for the ModernGL
            backend.
        panels: Panels for the layer. Defaults to Hierarchy and Inspector.

    The returned layer's teardown is owned by the pass that is installed
    into the graph, so `RenderGraph.release()` -- which
    `Application.shutdown()` calls -- releases the editor too. Releasing it
    by hand as well is harmless.

    Returns:
        The `EditorLayer`, registered in the container so game code can
        reach it, or `None` when the editor cannot run here -- ImGui
        missing, or a backend with no GL context. The reason is logged.
    """
    if not IMGUI_AVAILABLE:
        logger.warning(
            "Editor not attached: Dear ImGui is not installed "
            f"({IMGUI_IMPORT_ERROR}). Install the dev extra to enable it."
        )
        return None

    # Imported here, not at module scope, so importing this module on an
    # install without ImGui does not itself raise -- the check above is
    # meant to be reachable.
    from pyguara.editor.imgui_pass import ImGuiPass
    from pyguara.editor.layer import EditorLayer
    from pyguara.editor.renderer import ModernGLImGuiRenderer
    from pyguara.graphics.pipeline.graph import RenderGraph

    # Typed `object`: the container is declared to return a `RenderGraph`,
    # but the Pygame backend registers its non-subclass stub under the same
    # key, so the isinstance check below is a real runtime branch rather
    # than the dead code the declared type would make it.
    candidate: object
    try:
        # cast through `object` so the isinstance below stays a live branch:
        # the container is *declared* to return a `RenderGraph`, and without
        # this mypy calls the stub case dead code.
        candidate = cast(object, container.get(RenderGraph))
    except Exception as exc:
        logger.warning(f"Editor not attached: no RenderGraph registered ({exc}).")
        return None

    # The same test `Application` uses to tell the real graph from Pygame's
    # stub, which is registered under the same key but is not a subclass.
    if not isinstance(candidate, RenderGraph):
        logger.info(
            "Editor not attached: this backend has no GL render graph "
            f"({type(candidate).__name__}). The editor is ModernGL-only; "
            "use the pyguara/tools overlay on the Pygame backend."
        )
        return None

    # A real `RenderGraph` is constructed with a context and exposes it
    # non-optionally, so there is nothing further to guard here.
    ctx = candidate.ctx

    # The graph's own dimensions, not `ctx.screen.size`: `ctx.screen` is
    # `None` on a standalone (offscreen) context, which is what the GL
    # tests and `tools/agent_view.py --gl` run on. The graph knows its size
    # either way, and `graph.resize()` already forwards changes to every
    # pass's `on_resize()`.
    width = candidate.fbo_manager.width
    height = candidate.fbo_manager.height
    layer = EditorLayer(
        container,
        renderer_factory=lambda: ModernGLImGuiRenderer(ctx),
        panels=panels,
    )
    # Appended, so it runs after `final` has blitted the scene to the
    # screen and the editor lands on top of the finished frame.
    candidate.add_pass(ImGuiPass(layer, width, height))
    container.register_instance(EditorLayer, layer)

    logger.info(f"Editor attached: {len(layer.panels)} panel(s) over ModernGL.")
    return layer
