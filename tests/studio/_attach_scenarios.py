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
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "offscreen"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from pyguara.application.bootstrap import create_application  # noqa: E402
from pyguara.common.components import Transform  # noqa: E402
from pyguara.config.types import RenderingBackend  # noqa: E402
from pyguara.studio.attach import StudioAttachment, attach_studio  # noqa: E402


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
        attachment = attach_studio(app.container, project_root=Path.cwd())
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
        attachment = attach_studio(app.container, project_root=Path.cwd())
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
        attachment = attach_studio(app.container, project_root=Path.cwd())
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
        attachment = attach_studio(app.container, project_root=Path.cwd())
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


SCENARIOS = {
    "attaches": attaches,
    "session_follows_the_scene": session_follows_the_scene,
    "frames_and_operations": frames_and_operations,
    "panels_install_under_the_real_loop": (panels_install_under_the_real_loop),
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
