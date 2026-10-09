"""`ModernGLImGuiRenderer.register_texture`: showing a foreign texture.

What this unlocks is the standard editor arrangement -- the scene rendered
into a framebuffer and displayed inside a dockable panel. It did not work
before, and failed silently: `_textures` was populated only by
`_service_texture_requests` from ImGui's own atlas requests, so a draw
command carrying any other id hit the `continue` in `render()` and the
image simply did not appear.

The ownership rule is the fiddly part and is what most of these assert. A
framebuffer's colour attachment belongs to its `FramebufferManager`; if
`release()` freed it along with the atlas, the manager's own release would
be a double free landing on whatever moderngl had reused the name for.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("imgui_bundle")
pytest.importorskip("moderngl")

from imgui_bundle import imgui  # noqa: E402

from pyguara.editor.renderer import ModernGLImGuiRenderer  # noqa: E402


@pytest.fixture
def renderer(isolated_gl_ctx: Any) -> Any:
    """A renderer on a context of this test's own, with an ImGui context.

    `ModernGLImGuiRenderer.__init__` writes to `imgui.get_io()`, so a
    context has to be current before it is built.
    """
    context = imgui.create_context()
    imgui.set_current_context(context)
    renderer = ModernGLImGuiRenderer(isolated_gl_ctx)
    yield renderer
    renderer.release()
    imgui.destroy_context(context)


class TestRegisterTexture:
    """Minting ids for textures ImGui did not ask for."""

    def test_returns_a_nonzero_id(self, renderer: Any, isolated_gl_ctx: Any) -> None:
        texture = isolated_gl_ctx.texture((4, 4), 4)
        try:
            assert renderer.register_texture(texture) != 0
        finally:
            texture.release()

    def test_the_texture_becomes_resolvable(
        self, renderer: Any, isolated_gl_ctx: Any
    ) -> None:
        """The draw loop looks the id up in `_textures`; it must be there."""
        texture = isolated_gl_ctx.texture((4, 4), 4)
        try:
            texture_id = renderer.register_texture(texture)
            assert renderer._textures[texture_id] is texture
        finally:
            texture.release()

    def test_registering_twice_returns_the_same_id(
        self, renderer: Any, isolated_gl_ctx: Any
    ) -> None:
        """A viewport panel registers its framebuffer every frame.

        Minting a fresh id per call would grow `_textures` without bound
        for as long as the editor is open.
        """
        texture = isolated_gl_ctx.texture((4, 4), 4)
        try:
            first = renderer.register_texture(texture)
            second = renderer.register_texture(texture)
            assert first == second
            assert len(renderer._textures) == 1
        finally:
            texture.release()

    def test_distinct_textures_get_distinct_ids(
        self, renderer: Any, isolated_gl_ctx: Any
    ) -> None:
        a = isolated_gl_ctx.texture((4, 4), 4)
        b = isolated_gl_ctx.texture((4, 4), 4)
        try:
            assert renderer.register_texture(a) != renderer.register_texture(b)
        finally:
            a.release()
            b.release()

    def test_ids_do_not_collide_with_imgui_minted_ones(
        self, renderer: Any, isolated_gl_ctx: Any
    ) -> None:
        """Both draw from `_next_texture_id`, so the counter must be shared."""
        texture = isolated_gl_ctx.texture((4, 4), 4)
        try:
            texture_id = renderer.register_texture(texture)
            assert texture_id not in {
                other for other in renderer._textures if other != texture_id
            }
            assert renderer._next_texture_id > texture_id
        finally:
            texture.release()


class TestOwnership:
    """A registered texture is borrowed, not adopted."""

    def test_release_does_not_free_a_registered_texture(
        self, isolated_gl_ctx: Any
    ) -> None:
        """The whole point of tracking foreign ids separately.

        Asserted by using the texture after the renderer is gone: moderngl
        raises on a released object, so a successful write proves it is
        still alive.
        """
        context = imgui.create_context()
        imgui.set_current_context(context)
        renderer = ModernGLImGuiRenderer(isolated_gl_ctx)
        texture = isolated_gl_ctx.texture((4, 4), 4)
        try:
            renderer.register_texture(texture)
            renderer.release()

            texture.write(b"\x00" * (4 * 4 * 4))
        finally:
            texture.release()
            imgui.destroy_context(context)

    def test_release_clears_the_foreign_bookkeeping(
        self, renderer: Any, isolated_gl_ctx: Any
    ) -> None:
        texture = isolated_gl_ctx.texture((4, 4), 4)
        try:
            renderer.register_texture(texture)
            renderer.release()
            assert renderer._textures == {}
            assert renderer._foreign_texture_ids == set()
        finally:
            texture.release()

    def test_unregister_drops_the_id_without_freeing(
        self, renderer: Any, isolated_gl_ctx: Any
    ) -> None:
        """Called when the owner is about to release the texture."""
        texture = isolated_gl_ctx.texture((4, 4), 4)
        try:
            texture_id = renderer.register_texture(texture)
            renderer.unregister_texture(texture_id)

            assert texture_id not in renderer._textures
            texture.write(b"\x00" * (4 * 4 * 4))
        finally:
            texture.release()

    def test_unregister_ignores_unknown_ids(self, renderer: Any) -> None:
        renderer.unregister_texture(9999)

    def test_unregister_after_a_re_register_yields_a_fresh_id(
        self, renderer: Any, isolated_gl_ctx: Any
    ) -> None:
        """So the idempotence cache cannot strand a stale mapping."""
        texture = isolated_gl_ctx.texture((4, 4), 4)
        try:
            first = renderer.register_texture(texture)
            renderer.unregister_texture(first)
            second = renderer.register_texture(texture)
            assert second != first
            assert renderer._textures[second] is texture
        finally:
            texture.release()
