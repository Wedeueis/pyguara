"""`WgpuImGuiRenderer.register_texture`: showing a framebuffer in a panel.

What this unlocks is the standard editor arrangement -- the scene rendered
into a framebuffer and displayed inside a dockable panel. Under ModernGL it
first did not work, and failed silently: the renderer's texture table was
populated only from ImGui's own atlas requests, so a draw command carrying
any other id was skipped and the image simply did not appear.

The ownership rule is the fiddly part and is what most of these assert. A
framebuffer belongs to its `FramebufferManager`; if `release()` freed it
along with the atlas, the manager's own release would free it a second
time.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.studio.wgpu_renderer import WgpuImGuiRenderer  # noqa: E402


@pytest.fixture
def buffers(wgpu_frame: Any) -> Iterator[tuple[Any, Any]]:
    """A frame and a framebuffer manager on it, to register buffers from."""
    from pyguara.graphics.pipeline.device import WgpuDevice
    from pyguara.graphics.pipeline.framebuffer import FramebufferManager

    frame = wgpu_frame(16, 16)
    manager = FramebufferManager(WgpuDevice(frame), 16, 16)
    yield frame, manager
    manager.release_all()


@pytest.fixture
def renderer(buffers: tuple[Any, Any]) -> Iterator[WgpuImGuiRenderer]:
    """A renderer with an ImGui context current, as its `__init__` needs."""
    context = imgui.create_context()
    imgui.set_current_context(context)
    renderer = WgpuImGuiRenderer(buffers[0])
    yield renderer
    renderer.release()
    imgui.destroy_context(context)


def _alive(frame: Any, buffer: Any) -> bool:
    """Whether a buffer still exists: clear it and read it back."""
    buffer.clear_rgba((0.0, 0.0, 0.0, 1.0))
    frame.gpu.end_frame()
    return len(buffer.read_rgba()) == buffer.width * buffer.height * 4


class TestRegisterTexture:
    """Minting ids for textures ImGui did not ask for."""

    def test_returns_a_nonzero_id(self, renderer: Any, buffers: Any) -> None:
        assert renderer.register_texture(buffers[1].get_or_create("a")) != 0

    def test_the_texture_becomes_resolvable(self, renderer: Any, buffers: Any) -> None:
        """The draw loop looks the id up in `_textures`; it must be there."""
        buffer = buffers[1].get_or_create("a")

        texture_id = renderer.register_texture(buffer)

        assert renderer._textures[texture_id] == (1, buffer.target)

    def test_registering_twice_returns_the_same_id(
        self, renderer: Any, buffers: Any
    ) -> None:
        """A viewport panel registers its framebuffer every frame.

        Minting a fresh id per call would grow `_textures` without bound
        for as long as the editor is open.
        """
        buffer = buffers[1].get_or_create("a")

        first = renderer.register_texture(buffer)
        second = renderer.register_texture(buffer)

        assert first == second
        assert len(renderer._textures) == 1

    def test_distinct_textures_get_distinct_ids(
        self, renderer: Any, buffers: Any
    ) -> None:
        a = buffers[1].get_or_create("a")
        b = buffers[1].get_or_create("b")

        assert renderer.register_texture(a) != renderer.register_texture(b)

    def test_ids_do_not_collide_with_imgui_minted_ones(
        self, renderer: Any, buffers: Any
    ) -> None:
        """Both draw from `_next_texture_id`, so the counter must be shared."""
        texture_id = renderer.register_texture(buffers[1].get_or_create("a"))

        assert renderer._next_texture_id > texture_id

    def test_something_that_is_not_a_framebuffer_is_refused(
        self, renderer: Any
    ) -> None:
        with pytest.raises(TypeError, match="not a wgpu framebuffer"):
            renderer.register_texture(object())


class TestOwnership:
    """A registered framebuffer is borrowed, not adopted."""

    def test_release_does_not_free_a_registered_texture(
        self, renderer: Any, buffers: Any
    ) -> None:
        """The whole point of tracking foreign ids separately."""
        frame, manager = buffers
        buffer = manager.get_or_create("a")
        renderer.register_texture(buffer)

        renderer.release()

        assert _alive(frame, buffer)

    def test_release_clears_the_foreign_bookkeeping(
        self, renderer: Any, buffers: Any
    ) -> None:
        renderer.register_texture(buffers[1].get_or_create("a"))

        renderer.release()

        assert renderer._textures == {}
        assert renderer._foreign_texture_ids == set()

    def test_unregister_drops_the_id_without_freeing(
        self, renderer: Any, buffers: Any
    ) -> None:
        """Called when the owner is about to release the framebuffer."""
        frame, manager = buffers
        buffer = manager.get_or_create("a")
        texture_id = renderer.register_texture(buffer)

        renderer.unregister_texture(texture_id)

        assert texture_id not in renderer._textures
        assert _alive(frame, buffer)

    def test_unregister_ignores_unknown_ids(self, renderer: Any) -> None:
        renderer.unregister_texture(9999)

    def test_unregister_after_a_re_register_yields_a_fresh_id(
        self, renderer: Any, buffers: Any
    ) -> None:
        """So the idempotence cache cannot strand a stale mapping."""
        buffer = buffers[1].get_or_create("a")
        first = renderer.register_texture(buffer)
        renderer.unregister_texture(first)

        second = renderer.register_texture(buffer)

        assert second != first
        assert renderer._textures[second] == (1, buffer.target)
