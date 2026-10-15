"""Scenarios for `attach_studio`, run in a subprocess by `test_attach.py`.

A separate process because `attach_studio` needs a real SDL window with a
GL context, and the suite's session-scoped `gl_ctx` fixture already holds
a standalone EGL context current. Creating the second one in the same
process fails with `EGL_BAD_ACCESS` -- the "silently steals current"
hazard `tests/conftest.py` documents on `isolated_gl_ctx`, met from the
other direction.

Run as `python -m tests.studio._attach_scenarios <name>`. Each scenario
raises on failure and prints nothing on success, so the exit code is the
result and stderr is the explanation.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "offscreen"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from pyguara.application.bootstrap import create_application  # noqa: E402
from pyguara.common.components import Transform  # noqa: E402
from pyguara.config.types import RenderingBackend  # noqa: E402
from pyguara.studio.attach import StudioAttachment, attach_studio  # noqa: E402


def _project_root() -> Path:
    """Return a throwaway directory to attach Studio against.

    Not the repository. Studio keeps the panel arrangement in
    `<project_root>/.pyguara/`, and a test that wrote it into the checkout
    would be the surprise the editor's settings are deliberately opt-in to
    avoid. Nothing here reads the project's own files.

    Returns:
        A fresh temporary directory, cleaned up with the process.
    """
    return Path(tempfile.mkdtemp(prefix="pyguara-studio-scenario-"))


def _configure(config: object) -> None:
    """Select the ModernGL backend with vsync off."""
    config.display.backend = RenderingBackend.MODERNGL  # type: ignore[attr-defined]
    config.display.vsync = False  # type: ignore[attr-defined]


def _application() -> object:
    """Build a ModernGL application."""
    return create_application(configure=_configure)


def _scene(app: object) -> object:
    """Build a real demo scene."""
    from games.guara_falcao.scenes import GameScene

    return GameScene(app._event_dispatcher)  # type: ignore[attr-defined]


def attaches() -> None:
    """It attaches, registers itself, and has no session before a scene."""
    app = _application()
    try:
        attachment = attach_studio(app.container, project_root=_project_root())
        assert attachment is not None, "attach_studio declined"
        assert isinstance(app.container.get(StudioAttachment), StudioAttachment)

        # `attach_studio` runs before `app.run()`, so there is genuinely no
        # world yet.
        assert attachment.session is None, "a session opened with no scene"
        assert [p.title for p in attachment.layer.panels] == [
            "Hierarchy",
            "Inspector",
        ], "Studio's panels installed before a session existed"
    finally:
        app.shutdown()


def session_follows_the_scene() -> None:
    """A session opens over the active scene, and the panels install."""
    app = _application()
    try:
        attachment = attach_studio(app.container, project_root=_project_root())
        assert attachment is not None
        scene = _scene(app)
        app.begin(scene)

        session = attachment.session
        assert session is not None, "no session after a scene became active"
        assert session.scene_name == scene.name
        assert session.world is scene.entity_manager, (
            "the session is bound to a different world than the scene's"
        )
        assert session.journal is attachment.journal, (
            "the journal must outlive a session, so the record is continuous "
            "across a scene switch"
        )

        # Stable while the scene is: rebuilding per access would throw away
        # the undo history.
        assert attachment.session is session

        titles = [p.title for p in attachment.layer.panels]
        for expected in (
            "Viewport",
            "History",
            "Journal",
            "Components",
            "Commands",
        ):
            assert expected in titles, f"{expected} panel was not installed"

        installed = len(attachment.layer.panels)
        assert attachment.session is session
        assert len(attachment.layer.panels) == installed, (
            "panels were installed more than once"
        )
    finally:
        app.shutdown()


def frames_and_operations() -> None:
    """Frames step, the viewport gets a texture, and operations apply."""
    app = _application()
    try:
        attachment = attach_studio(app.container, project_root=_project_root())
        assert attachment is not None
        app.begin(_scene(app))

        for _ in range(5):
            assert app.step() is True, "the frame loop stopped early"

        frame = attachment._frame_texture()
        assert frame is not None, "the viewport got no frame texture"
        texture_id, width, height = frame
        assert texture_id > 0 and width > 0 and height > 0

        # Idempotent: a viewport registers its framebuffer every frame, and
        # a fresh id each time would grow the table without bound.
        app.step()
        assert attachment._frame_texture() == frame

        session = attachment.session
        assert session is not None
        target = next(
            entity.id for entity in session.world.get_entities_with(Transform)
        )
        result = attachment.operations.invoke(
            session,
            "set_field",
            {
                "entity_id": target,
                "component": "Transform",
                "field": "rotation",
                "value": 0.5,
            },
        )
        assert result.ok, f"set_field failed: {result.error}"

        entity = session.world.get_entity(target)
        assert entity is not None
        assert entity.get_component(Transform).rotation == 0.5

        session.undo()
        assert entity.get_component(Transform).rotation == 0.0, (
            "undo did not restore the rotation"
        )
    finally:
        app.shutdown()


def panels_install_under_the_real_loop() -> None:
    """The panels appear without anyone asking for the session.

    The bug this exists for: every other scenario, and every test,
    reached for `attachment.session` by hand -- which is what installs
    the panels. Under `app.run()`, the only way a game actually starts,
    nothing does, so Studio attached, logged that it had, and drew the
    base editor's two panels for ever.

    This scenario therefore touches `.session` nowhere.
    """
    app = _application()
    try:
        attachment = attach_studio(app.container, project_root=_project_root())
        assert attachment is not None
        app.begin(_scene(app))

        # Exactly what `app.run()` does, and nothing else.
        for _ in range(10):
            app.step()

        titles = [panel.title for panel in attachment.layer.panels]
        for expected in (
            "Viewport",
            "Play",
            "History",
            "Journal",
            "Components",
            "Commands",
        ):
            assert expected in titles, (
                f"{expected} was never installed. Studio's panels install "
                f"when its session first resolves, and nothing resolves it "
                f"under the real frame loop unless a frame hook does. "
                f"Installed: {titles}"
            )
    finally:
        app.shutdown()


def studio_owns_the_screen() -> None:
    """The game is drawn inside the viewport, not behind the panels.

    Three things together, and all three were wrong before: the final blit
    still copied the frame to the screen, so the game appeared twice;
    `UIRenderer.present()` composited the HUD onto the screen, so it landed
    over the panels; and the dockspace left its middle empty for a game
    that is now inside a panel.
    """
    from pyguara.graphics.pipeline.graph import RenderGraph
    from pyguara.graphics.protocols import UIRenderer

    app = _application()
    try:
        graph = app.container.get(RenderGraph)
        renderer = app.container.get(UIRenderer)  # type: ignore[type-abstract]
        original_present = renderer.present

        attachment = attach_studio(app.container, project_root=_project_root())
        assert attachment is not None
        app.begin(_scene(app))
        app.step()

        final_pass = graph.get_pass("final")
        assert final_pass is not None
        assert not final_pass.enabled, (
            "the final blit still runs, so the game is drawn full-screen "
            "behind the panels as well as inside the Viewport"
        )

        imgui_pass = graph.get_pass("imgui")
        assert imgui_pass is not None
        assert imgui_pass.after_ui, (
            "the editor runs mid-chain, so the game's HUD composites over its panels"
        )

        assert not attachment.layer.passthrough_centre, (
            "the dockspace still passes through to a game that is now inside a panel"
        )

        assert renderer.present is not original_present, (
            "the game's UI still composites to the screen rather than into "
            "the buffer the Viewport shows"
        )

        # And it all goes back, so a game can detach Studio.
        attachment.release_screen()
        assert final_pass.enabled
        assert attachment.layer.passthrough_centre
        # Compared by equality, not identity: a bound method is a fresh
        # object on every attribute access, so `is` never holds even when
        # the renderer has been restored exactly.
        assert renderer.present == original_present
        assert "present" not in vars(renderer), (
            "an instance attribute was left behind rather than removed"
        )
    finally:
        app.shutdown()


def the_layout_follows_the_window() -> None:
    """Resizing resizes the framebuffers the viewport reads.

    Maximising used to leave the editor drawing into the old window's
    bounds, with the rest of the screen black, because nothing told the
    render graph the window had changed.
    """
    app = _application()
    try:
        attachment = attach_studio(app.container, project_root=_project_root())
        assert attachment is not None
        app.begin(_scene(app))
        for _ in range(3):
            app.step()

        frame = attachment._frame_texture()
        assert frame is not None
        _, width, height = frame

        # The window keeps its shape, so with `keep_aspect` the game
        # renders at the configured resolution and is scaled up: what has
        # to follow the window is the graph's idea of how big the window
        # is, which is what the editor's own chrome is laid out against.
        app._resize_render_output(width * 2, height * 2)
        for _ in range(3):
            app.step()

        graph = app._render_graph
        assert graph.window_size == (width * 2, height * 2), (
            f"the graph still thinks the window is {graph.window_size} "
            f"after a resize to {(width * 2, height * 2)}"
        )
        assert graph.screen_rect == (0, 0, width * 2, height * 2), (
            "a window of the configured shape must get no bars"
        )

        # And with it off, the framebuffer itself follows the window --
        # the original symptom, where it stayed put for the life of the
        # process and the editor drew into a corner of the screen.
        app._config_manager.config.display.keep_aspect = False
        app._resize_render_output(width * 2, height * 2)
        for _ in range(3):
            app.step()

        resized = attachment._frame_texture()
        assert resized is not None
        assert resized[1] == width * 2, (
            f"the framebuffer stayed {resized[1]} wide after a resize to {width * 2}"
        )
        assert resized[2] == height * 2
    finally:
        app.shutdown()


def the_menus_are_studios_own() -> None:
    """Studio replaces the editor's lone panel menu with its full bar.

    And every menu's items draw. A menu is easy to get wrong in a way no
    smoke test catches, because the items only run while the popup is
    open -- so each one is opened here and a frame built with it open.
    """
    from imgui_bundle import imgui

    app = _application()
    try:
        attachment = attach_studio(app.container, project_root=_project_root())
        assert attachment is not None
        app.begin(_scene(app))
        for _ in range(5):
            app.step()

        layer = attachment.layer
        titles = [title for title, _ in layer.menus]
        assert titles == [
            "Scene",
            "Edit",
            "Entity",
            "View",
            "Run",
            "Agent",
            "Help",
        ], titles

        # Draw each menu's items for real. `begin_menu` needs a menu bar
        # to sit in, so one is opened on a window of its own -- the same
        # context ImGui's main menu bar gives them.
        imgui.set_current_context(layer._context)
        for title, draw_items in layer.menus:
            layer.build_frame(1280, 720, dt=1 / 60)
            imgui.new_frame()
            imgui.begin("##menutest", None, imgui.WindowFlags_.menu_bar.value)
            if imgui.begin_menu_bar():
                if imgui.begin_menu(title, True):
                    draw_items()
                    imgui.end_menu()
                imgui.end_menu_bar()
            imgui.end()
            imgui.render()
    finally:
        app.shutdown()


def the_editor_gets_the_whole_window() -> None:
    """The editor is not letterboxed with the game.

    `ctx.screen.viewport` is where the *game's* frame goes: with
    `keep_aspect` the graph narrows it, and the editor's pass used to
    inherit it -- every panel squeezed into the letterbox while ImGui laid
    them out for the whole window. On the 2000x876 window this was
    reported from that is a horizontal scale of 0.73, and an ultrawide
    display makes it worse.
    """
    app = _application()
    try:
        attachment = attach_studio(app.container, project_root=_project_root())
        assert attachment is not None
        app.begin(_scene(app))
        for _ in range(5):
            app.step()

        display = app._config_manager.config.display
        display.keep_aspect = True
        # Deliberately not the configured shape, so there are bars.
        window = (display.screen_width + 700, display.screen_height)
        app._resize_render_output(*window)

        graph = app._render_graph
        assert graph.screen_rect[2:] != window, "nothing was letterboxed"

        seen: list[tuple[int, int, int, int]] = []
        imgui_pass = graph.get_pass("imgui")
        original = imgui_pass._layer.render

        def record(width: int, height: int, dt: float | None = None) -> None:
            ctx = graph.ctx
            if ctx.screen is not None:
                seen.append(tuple(ctx.screen.viewport))
            original(width, height, dt)

        imgui_pass._layer.render = record
        try:
            for _ in range(3):
                app.step()
        finally:
            imgui_pass._layer.render = original

        assert seen, "the editor never drew"
        for viewport in seen:
            assert viewport == (0, 0, *window), (
                f"the editor drew under {viewport} rather than the whole "
                f"window {window}; it is being squeezed into the game's "
                f"letterbox {graph.screen_rect}"
            )

        # And put back, because the game's UI composites after the graph
        # and belongs inside the frame rather than on the bars.
        assert tuple(graph.ctx.screen.viewport) == graph.screen_rect
    finally:
        app.shutdown()


SCENARIOS = {
    "attaches": attaches,
    "session_follows_the_scene": session_follows_the_scene,
    "frames_and_operations": frames_and_operations,
    "panels_install_under_the_real_loop": (panels_install_under_the_real_loop),
    "studio_owns_the_screen": studio_owns_the_screen,
    "the_layout_follows_the_window": the_layout_follows_the_window,
    "the_menus_are_studios_own": the_menus_are_studios_own,
    "the_editor_gets_the_whole_window": the_editor_gets_the_whole_window,
}


def main(argv: list[str]) -> int:
    """Run one scenario by name.

    Args:
        argv: Command-line arguments; the first is the scenario name.

    Returns:
        0 on success, 2 for an unknown name. An assertion failure
        propagates, so pytest sees the traceback on stderr.
    """
    if len(argv) != 1 or argv[0] not in SCENARIOS:
        print(f"usage: {sys.argv[0]} <{'|'.join(SCENARIOS)}>", file=sys.stderr)
        return 2
    SCENARIOS[argv[0]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
