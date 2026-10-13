"""Putting Studio into a running application.

```python
from pyguara.application.bootstrap import create_application
from pyguara.studio import attach_studio

app = create_application()
studio = attach_studio(app.container)
app.run(MyScene("game", dispatcher))
```

Opt-in, like `attach_editor` and for the same reason: a shipped game
should not pay for an ImGui context and an operation registry it never
shows. `attach_studio` builds on `attach_editor` rather than replacing
it -- the context lifecycle, the input routing and the render pass are
already right there, and Studio adds panels and a session to them.

**The session is bound to a world, and the world changes.** Each scene
owns its own `EntityManager`, so a session built at attach time would be
editing the world of whichever scene happened to be active -- usually
none, since `attach_studio` runs before `app.run()`. `StudioAttachment`
therefore rebuilds the session on each scene switch, which is also the
only correct answer for the undo history: one that spanned a scene switch
would be reverting commands into a world that never saw them applied.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.log import get_logger
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.studio.agent.journal import Journal
from pyguara.studio.ops.builtin import default_registry
from pyguara.studio.ops.registry import OperationRegistry
from pyguara.studio.session import ApprovalMode, StudioSession

logger = get_logger(__name__)

DEFAULT_LAYOUT_REGIONS: dict[str, tuple[str, ...]] = {
    "left": ("Hierarchy",),
    "right": ("Inspector", "Components"),
    "bottom": ("History", "Journal", "Commands"),
    "top": ("Play",),
    "centre": ("Viewport",),
}
"""Where Studio's panels open, by window title.

The arrangement every editor converges on, for the reason they converge:
the hierarchy is a list you scan down one side, the inspector is a column
of fields opposite it, and the thing you are actually working on gets the
middle. History, the journal and the palette share the bottom as tabs --
all three are consulted rather than watched.

Applied once. A developer who drags a panel elsewhere keeps it there;
without any layout at all every window opens at the same default
position, stacked on top of the others.

Plain titles rather than a `DockLayout` so that **importing this module
does not import Dear ImGui**. `pyguara/studio/__init__.py` imports this
one, and `pyguara.studio.ops` goes through that `__init__`, so a module-
level `from pyguara.editor.layer import DockLayout` here made the
dependency-free JSON-lines transport need ImGui after all -- which is
precisely the coupling the MCP extra was kept out of.
"""


def default_layout() -> Any:
    """Build the default `DockLayout`.

    Imports ImGui, so it is called only from a path that already needs it.

    Returns:
        The layout.
    """
    from pyguara.editor.layer import DockLayout

    return DockLayout(
        left=DEFAULT_LAYOUT_REGIONS["left"],
        right=DEFAULT_LAYOUT_REGIONS["right"],
        bottom=DEFAULT_LAYOUT_REGIONS["bottom"],
        top=DEFAULT_LAYOUT_REGIONS["top"],
        centre=DEFAULT_LAYOUT_REGIONS["centre"],
    )


EDITOR_BACKGROUND = (0.10, 0.10, 0.12)
"""What the screen is cleared to behind the panels.

Dark and neutral, so the dockspace reads as chrome rather than as part of
whatever the game happens to be showing.
"""

VIEWPORT_SOURCE_DEFAULT = "world"
"""Which framebuffer the viewport shows when `FinalPass` does not say.

`FinalPass.input_fbo_name` is the authority -- it names the buffer the
finished frame was composed into -- and this is the fallback for a graph
that has no final pass, which is what the offscreen capture tooling runs
with.
"""


class StudioAttachment:
    """Studio installed into one application.

    Holds the pieces that outlive a scene -- the operation registry, the
    journal, the editor layer -- and rebuilds the ones that do not.
    """

    def __init__(
        self,
        container: DIContainer,
        *,
        layer: Any,
        operations: OperationRegistry,
        journal: Journal,
        project_root: Path,
        approval_mode: ApprovalMode,
    ) -> None:
        """Initialize the attachment.

        Args:
            container: The engine container.
            layer: The `EditorLayer` Studio's panels are drawn by.
            operations: The operation registry the palette and any agent
                front end share.
            journal: Where actions are recorded, across scene switches.
            project_root: The project directory, for `project_overview`.
            approval_mode: How edits requested by an agent are handled.
        """
        self._container = container
        self._layer = layer
        self._operations = operations
        self._journal = journal
        self._project_root = project_root
        self._approval_mode = approval_mode
        self._session: StudioSession | None = None
        self._panels_installed = False
        self._screen_taken = False
        self._final_was_enabled = True
        self._ui_present_patched = False

    @property
    def layer(self) -> Any:
        """The editor layer Studio's panels are drawn by."""
        return self._layer

    @property
    def operations(self) -> OperationRegistry:
        """The operation registry the palette and agents share."""
        return self._operations

    @property
    def journal(self) -> Journal:
        """The action record, which outlives a scene switch."""
        return self._journal

    @property
    def session(self) -> StudioSession | None:
        """The session over the active scene's world, or None.

        None until a scene is active. Resolved lazily rather than at
        attach time, because `attach_studio` is called before `app.run()`
        and there is genuinely no world yet.
        """
        world = self._active_world()
        if world is None:
            return None
        if self._session is None or self._session.world is not world:
            self._session = self._open_session(world)
            self._install_panels()
        return self._session

    def _open_session(self, world: EntityManager) -> StudioSession:
        """Build a session over `world`.

        Args:
            world: The active scene's world.

        Returns:
            The session, sharing the attachment's journal so the record is
            continuous across scene switches.
        """
        scene_name = None
        try:
            from pyguara.scene.manager import SceneManager

            scene = self._container.get(SceneManager).current_scene
            scene_name = scene.name if scene is not None else None
        except Exception:  # pragma: no cover - a container with no manager
            pass

        logger.info(f"Studio session opened over scene '{scene_name}'.")
        return StudioSession(
            world,
            scene_name=scene_name,
            project_root=self._project_root,
            component_registry=self._resolve_registry(),
            journal=self._journal,
            approval_mode=self._approval_mode,
        )

    def _install_panels(self) -> None:
        """Add Studio's panels to the layer, once.

        Deferred until a session exists, because every one of them needs
        it. Done once rather than per scene switch: the panels read the
        session through this attachment, so they survive it being
        replaced.
        """
        if self._panels_installed:
            return
        self._panels_installed = True

        from pyguara.studio.panels.history import HistoryPanel
        from pyguara.studio.panels.journal import JournalPanel
        from pyguara.studio.panels.palette import CommandPalette
        from pyguara.studio.panels.play import PlayControlsPanel
        from pyguara.studio.panels.schema import SchemaPanel
        from pyguara.studio.viewport.gizmo import TransformGizmo
        from pyguara.studio.viewport.panel import ViewportPanel

        session = self._session
        if session is None:  # pragma: no cover - called with one in hand
            return

        gizmo = TransformGizmo(session)
        viewport = ViewportPanel(
            camera_provider=self._active_camera,
            texture_provider=self._frame_texture,
            physics_provider=self._physics_engine,
            overlays=[gizmo],
        )

        panels: list[Any] = [
            viewport,
            HistoryPanel(session),
            JournalPanel(session),
            SchemaPanel(self._resolve_registry()),
            CommandPalette(session, self._operations),
        ]
        application = self._application()
        if application is not None:
            panels.insert(1, PlayControlsPanel(application))
        for panel in panels:
            self._layer.add_panel(panel)

        self._layer.set_default_layout(default_layout())
        logger.info("Studio panels installed.")

    def take_over_screen(self) -> None:
        """Make the editor the only thing on screen, with the game inside it.

        Three changes, which together are the difference between an editor
        and panels floating over a running game:

        1. **The final blit is disabled.** `FinalPass` copies the composed
           frame to the default framebuffer, so without this the game is
           drawn twice -- full-screen behind the panels, and again inside
           the Viewport panel, which shows the same buffer as an image.
        2. **The game's UI is redirected into that buffer.** `UIRenderer.
           present()` composites the HUD onto the *screen*, so it landed on
           top of the editor's panels. Bound to the viewport's source
           buffer instead, it lands where it belongs: inside the viewport,
           over the game it annotates. The same redirect
           `tools/agent_view.py` uses to capture a frame with its UI.
        3. **The dockspace stops passing through.** With nothing behind it
           worth seeing, an empty middle is just a hole.

        Reversed by `release_screen()`, so a game can detach Studio and get
        its own window back.
        """
        if self._screen_taken:
            return
        self._screen_taken = True

        graph = self._graph()
        if graph is None:
            # No GL graph: `attach_editor` would already have declined, so
            # this is unreachable in practice and harmless if reached.
            return

        final_pass = graph.get_pass("final")
        if final_pass is not None:
            self._final_was_enabled = final_pass.enabled
            final_pass.enabled = False

        imgui_pass = graph.get_pass("imgui")
        if imgui_pass is not None and hasattr(imgui_pass, "set_clear_colour"):
            imgui_pass.set_clear_colour(EDITOR_BACKGROUND)

        self._layer.passthrough_centre = False
        self._redirect_game_ui()
        self._warn_if_not_resizable()

    def release_screen(self) -> None:
        """Give the screen back to the game.

        Safe to call when it was never taken.
        """
        if not self._screen_taken:
            return
        self._screen_taken = False

        graph = self._graph()
        if graph is not None:
            final_pass = graph.get_pass("final")
            if final_pass is not None:
                final_pass.enabled = self._final_was_enabled
            imgui_pass = graph.get_pass("imgui")
            if imgui_pass is not None and hasattr(imgui_pass, "set_clear_colour"):
                imgui_pass.set_clear_colour(None)

        self._layer.passthrough_centre = True
        self._restore_game_ui()

    def _warn_if_not_resizable(self) -> None:
        """Say so when the window cannot be resized, and how to fix it.

        SDL emits no resize event at all for a fixed-size window, and a
        window manager may still let the frame be maximised -- WSLg does.
        The engine then carries on rendering at the starting resolution
        into a corner of a much larger window, with no event to tell it
        otherwise. That looks like a broken editor and is a one-line
        configuration fix, so it is worth saying out loud.

        The flag cannot be added to a live window: SDL honours it at
        creation, and `pygame.Window.resizable` does not take on a window
        the display module opened. Reopening would recreate the drawable
        and every GL object with it.
        """
        try:
            from pyguara.config.manager import ConfigManager

            display = self._container.get(ConfigManager).config.display
        except Exception as exc:  # pragma: no cover - a hand-built container
            logger.debug(f"Could not read the display config: {exc}")
            return

        if getattr(display, "resizable", False):
            return

        logger.warning(
            "The window is not resizable, so maximising it will leave the "
            "editor drawing at the starting resolution -- SDL sends no "
            "resize event for a fixed-size window. Set "
            "`config.display.resizable = True` in the bootstrap's "
            "`configure` hook, before the window is created."
        )

    def _redirect_game_ui(self) -> None:
        """Composite the game's UI into the viewport's buffer, not the screen.

        Wraps `UIRenderer.present` rather than changing it: the redirect is
        true only while Studio is attached, and a renderer that knew about
        editors would be the backend leakage this engine is built to avoid.
        """
        try:
            from pyguara.graphics.protocols import UIRenderer

            # Abstract by design: the container holds a backend
            # implementation registered under the protocol.
            renderer = self._container.get(UIRenderer)  # type: ignore[type-abstract]
        except Exception as exc:  # pragma: no cover - a container without one
            logger.debug(f"No UI renderer to redirect: {exc}")
            return

        original = renderer.present
        self._ui_present_patched = True

        def present_into_viewport() -> None:
            framebuffer = self._source_framebuffer()
            if framebuffer is not None:
                framebuffer.bind()
            original()

        renderer.present = present_into_viewport  # type: ignore[method-assign]

    def _restore_game_ui(self) -> None:
        """Put `UIRenderer.present` back.

        The instance attribute is *deleted* rather than reassigned, so the
        class's own method shows through again and the renderer is left
        exactly as it was found. Re-assigning the bound method that was
        captured would leave an instance attribute behind that merely
        looks right -- and since a bound method is a fresh object on every
        attribute access, nothing could tell the difference by identity.
        """
        if not self._ui_present_patched:
            return
        self._ui_present_patched = False
        try:
            from pyguara.graphics.protocols import UIRenderer

            # Abstract by design: the container holds a backend
            # implementation registered under the protocol.
            renderer = self._container.get(UIRenderer)  # type: ignore[type-abstract]
            del renderer.present
        except Exception as exc:  # pragma: no cover - a container without one
            logger.debug(f"Could not restore the UI renderer: {exc}")

    def _source_framebuffer(self) -> Any:
        """Return the buffer the finished frame is composed in, or None.

        Returns:
            The framebuffer `FinalPass` would blit from, which is what the
            Viewport panel shows.
        """
        graph = self._graph()
        if graph is None:
            return None
        manager = getattr(graph, "fbo_manager", None)
        if manager is None:
            return None

        name = VIEWPORT_SOURCE_DEFAULT
        final_pass = graph.get_pass("final")
        if final_pass is not None:
            name = getattr(final_pass, "input_fbo_name", name)
        return manager.get(name)

    def _graph(self) -> Any:
        """Return the real render graph, or None on a backend without one.

        Returns:
            The graph, or None -- the Pygame backend registers a stub
            under the same key.
        """
        try:
            from pyguara.graphics.pipeline.graph import RenderGraph

            graph = self._container.get(RenderGraph)
        except Exception:
            return None
        return graph if isinstance(graph, RenderGraph) else None

    # ----------------------------------------------------------------
    # Providers
    # ----------------------------------------------------------------

    def _active_world(self) -> EntityManager | None:
        """Return the active scene's world, or None.

        Resolved on each call rather than cached: each scene owns its own
        `EntityManager`, so the answer changes on every scene switch --
        the same reason `EditorLayer` re-resolves it per frame.

        Returns:
            The world, or None when no scene is active.
        """
        try:
            from pyguara.scene.manager import SceneManager

            scene = self._container.get(SceneManager).current_scene
        except Exception:  # pragma: no cover - a container with no manager
            return None
        return None if scene is None else scene.entity_manager

    def _active_camera(self) -> Any:
        """Return the active scene's camera, or None.

        Returns:
            The camera, or None when no scene is active or it has not
            resolved its dependencies yet -- `Scene.camera` is None until
            then.
        """
        try:
            from pyguara.scene.manager import SceneManager

            scene = self._container.get(SceneManager).current_scene
        except Exception:  # pragma: no cover - a container with no manager
            return None
        return None if scene is None else scene.camera

    def _application(self) -> Any:
        """Return the running application, or None.

        Returns:
            The application, or None when the container has none -- which
            is the case in a hand-built container, where the play
            controls simply are not offered.
        """
        try:
            from pyguara.application.application import Application

            return self._container.get(Application)
        except Exception:
            return None

    def _physics_engine(self) -> Any:
        """Return the physics engine, or None.

        Returns:
            The engine, for collider-accurate picking, or None when the
            container has none.
        """
        try:
            from pyguara.physics.protocols import IPhysicsEngine

            # Abstract by design: the container holds a backend
            # implementation registered under the protocol.
            return self._container.get(IPhysicsEngine)  # type: ignore[type-abstract]
        except Exception:
            return None

    def _frame_texture(self) -> tuple[int, int, int] | None:
        """Return the composed frame as `(texture_id, width, height)`.

        The buffer `FinalPass` composed into, registered with the ImGui
        renderer so a panel can draw it. The same buffer
        `tools/agent_view.py` reads for its captures, so the viewport and
        a headless capture show the same pixels.

        Returns:
            The frame, or None when there is nothing to show -- no GL
            graph, no such buffer, or a layer with no renderer, which is
            how the headless tests run.
        """
        try:
            from pyguara.graphics.pipeline.graph import RenderGraph

            graph = self._container.get(RenderGraph)
        except Exception:
            return None

        fbo_manager = getattr(graph, "fbo_manager", None)
        if fbo_manager is None:
            # The Pygame backend registers a stub under the same key.
            return None

        name = VIEWPORT_SOURCE_DEFAULT
        final_pass = graph.get_pass("final") if hasattr(graph, "get_pass") else None
        if final_pass is not None:
            name = getattr(final_pass, "input_fbo_name", name)

        framebuffer = fbo_manager.get(name)
        if framebuffer is None:
            return None

        texture_id = self._layer.register_texture(framebuffer.texture)
        if texture_id is None:
            return None
        return (texture_id, framebuffer.width, framebuffer.height)

    def _resolve_registry(self) -> ComponentRegistry:
        """Return the component registry, falling back to the global one.

        Returns:
            The registry. `create_application()` registers the global
            instance, so these are normally the same object.
        """
        try:
            return self._container.get(ComponentRegistry)
        except Exception:  # pragma: no cover - a hand-built container
            from pyguara.prefabs.registry import get_component_registry

            return get_component_registry()


def attach_studio(
    container: DIContainer,
    *,
    project_root: Path | None = None,
    operations: OperationRegistry | None = None,
    journal_path: Path | None = None,
    approval_mode: ApprovalMode = ApprovalMode.AUTO,
) -> StudioAttachment | None:
    """Install Studio into the container's application.

    Args:
        container: The engine container, which must already have a
            `RenderGraph` -- `create_application()` provides one on the
            ModernGL backend.
        project_root: The project directory. Defaults to the working
            directory.
        operations: The operations to offer. Defaults to the built-in set.
        journal_path: A JSON Lines file to append the action record to.
            None keeps it in memory for the session.
        approval_mode: How edits requested by an agent are handled.

    Returns:
        The attachment, also registered in the container so game code and
        an agent front end can reach it, or None when Studio cannot run
        here -- ImGui missing, or a backend with no GL context. The reason
        is logged, matching `attach_editor`, which declines the same way
        rather than half-installing.
    """
    from pyguara.editor.attach import attach_editor

    layer = attach_editor(container)
    if layer is None:
        logger.info(
            "Studio not attached: the editor layer declined, so there is "
            "nothing to draw panels with. See the preceding message."
        )
        return None

    attachment = StudioAttachment(
        container,
        layer=layer,
        operations=operations if operations is not None else default_registry(),
        journal=Journal(journal_path),
        project_root=(project_root or Path.cwd()).resolve(),
        approval_mode=approval_mode,
    )
    container.register_instance(StudioAttachment, attachment)

    attachment.take_over_screen()

    # Resolved every frame, which is what actually installs the panels.
    #
    # The session is per-scene and built lazily, and `attach_studio` runs
    # *before* `app.run()`, so at this point there is no world and no
    # session. Without something asking again each frame, nothing ever
    # does: under `app.run()` -- the only way a game actually starts --
    # Studio attached, logged that it had, and drew the base editor's two
    # panels for ever. Resolving it here once was not enough, and every
    # test missed it by reaching for `attachment.session` by hand.
    # Through the attachment, whose `layer` is typed loosely:
    # `attach_editor` is declared to return `object | None`, since the
    # Pygame backend's stub is registered under the same key.
    attachment.layer.add_frame_hook(lambda: attachment.session)

    logger.info("Studio attached.")
    return attachment
