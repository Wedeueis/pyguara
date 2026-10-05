"""The editor's ModernGL renderer, against a real GL context.

This is the half the previous ImGui editor never reached. Its renderer
needed PyOpenGL, which was installed nowhere, so `HAS_IMGUI` was always
`False` and no pixel was ever produced. These tests read the framebuffer
back and assert geometry actually landed in it.

`isolated_gl_ctx` rather than the shared `gl_ctx`: the renderer sets
context-global state (blend func, depth/cull enables), which would leak
into every later GL test on a session-scoped context.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.scene.manager import SceneManager

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.editor.attach import attach_editor  # noqa: E402
from pyguara.editor.imgui_pass import PASS_NAME, ImGuiPass  # noqa: E402
from pyguara.editor.layer import EditorLayer  # noqa: E402
from pyguara.editor.renderer import ModernGLImGuiRenderer  # noqa: E402
from pyguara.graphics.pipeline.graph import RenderGraph  # noqa: E402

_SIZE = (320, 240)


class _FakeScene:
    def __init__(self, entity_manager: EntityManager) -> None:
        self.entity_manager = entity_manager


class _FakeSceneManager:
    def __init__(self, scene: Any) -> None:
        self.current_scene = scene


@pytest.fixture
def world() -> EntityManager:
    manager = EntityManager()
    manager.create_entity("root")
    manager.create_entity("child")
    manager.set_parent("child", "root")
    return manager


@pytest.fixture
def container(world: EntityManager) -> DIContainer:
    container = DIContainer()
    container.register_instance(SceneManager, _FakeSceneManager(_FakeScene(world)))
    return container


@pytest.fixture
def target(isolated_gl_ctx: Any) -> Any:
    """A framebuffer to draw into, cleared to black."""
    fbo = isolated_gl_ctx.simple_framebuffer(_SIZE)
    fbo.use()
    fbo.clear(0.0, 0.0, 0.0, 1.0)
    try:
        yield fbo
    finally:
        fbo.release()


def _pixels(fbo: Any) -> np.ndarray:
    """Read the framebuffer back as an (N, 3) uint8 array."""
    return np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(-1, 3)


@pytest.mark.integration
class TestRendererDrawsPixels:
    def test_the_editor_actually_rasterises(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        """The assertion the deleted editor could never have passed."""
        layer = EditorLayer(
            container,
            renderer_factory=lambda: ModernGLImGuiRenderer(isolated_gl_ctx),
        )
        try:
            # ImGui emits no geometry on a context's first frame.
            layer.build_frame(*_SIZE, dt=1 / 60)
            target.use()
            layer.render(*_SIZE, dt=1 / 60)

            drawn = _pixels(target)
            assert int((drawn.sum(axis=1) > 0).sum()) > 100
        finally:
            layer.release()

    def test_the_frame_is_not_a_single_flat_colour(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        """Text and panel chrome mean many distinct colours. One colour
        would mean the shader ran but sampled nothing -- the failure a
        pixel count alone would miss."""
        layer = EditorLayer(
            container,
            renderer_factory=lambda: ModernGLImGuiRenderer(isolated_gl_ctx),
        )
        try:
            layer.build_frame(*_SIZE, dt=1 / 60)
            target.use()
            layer.render(*_SIZE, dt=1 / 60)
            assert len(np.unique(_pixels(target), axis=0)) > 3
        finally:
            layer.release()

    def test_a_hidden_layer_draws_nothing(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        layer = EditorLayer(
            container,
            renderer_factory=lambda: ModernGLImGuiRenderer(isolated_gl_ctx),
        )
        try:
            layer.build_frame(*_SIZE, dt=1 / 60)
            layer.toggle()
            target.use()
            target.clear(0.0, 0.0, 0.0, 1.0)
            layer.render(*_SIZE, dt=1 / 60)
            assert int(_pixels(target).sum()) == 0
        finally:
            layer.release()

    def test_many_frames_do_not_leak_or_fail(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        """Exercises the buffer-reuse path: the VBO/IBO are only
        reallocated when they are too small, so steady state must reuse."""
        layer = EditorLayer(
            container,
            renderer_factory=lambda: ModernGLImGuiRenderer(isolated_gl_ctx),
        )
        try:
            for _ in range(30):
                target.use()
                layer.render(*_SIZE, dt=1 / 60)
            assert int((_pixels(target).sum(axis=1) > 0).sum()) > 100
        finally:
            layer.release()


@pytest.mark.integration
class TestGLStateHygiene:
    def test_the_scissor_covers_the_whole_target_afterwards(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        """A scissor left narrow would clip whatever the engine draws next.

        Assigning `ctx.scissor = None` *resets* the rect to the full
        framebuffer rather than storing `None`, so reading it back gives
        the full bounds -- which is the state being asserted here.
        """
        layer = EditorLayer(
            container,
            renderer_factory=lambda: ModernGLImGuiRenderer(isolated_gl_ctx),
        )
        try:
            layer.build_frame(*_SIZE, dt=1 / 60)
            target.use()
            layer.render(*_SIZE, dt=1 / 60)
            assert isolated_gl_ctx.scissor == (0, 0, *_SIZE)
        finally:
            layer.release()

    def test_a_later_full_clear_is_not_clipped(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        """The observable consequence of the scissor being reset."""
        layer = EditorLayer(
            container,
            renderer_factory=lambda: ModernGLImGuiRenderer(isolated_gl_ctx),
        )
        try:
            layer.build_frame(*_SIZE, dt=1 / 60)
            target.use()
            layer.render(*_SIZE, dt=1 / 60)

            target.clear(0.0, 1.0, 0.0, 1.0)
            drawn = _pixels(target)
            assert len(np.unique(drawn, axis=0)) == 1
            assert tuple(drawn[0]) == (0, 255, 0)
        finally:
            layer.release()


@pytest.mark.integration
class TestFontAtlasTextures:
    def test_the_font_atlas_is_created_and_marked_ok(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        """ImGui 1.92 hands the atlas over as a texture *request* each
        frame; a backend that ignores it draws no text at all."""
        layer = EditorLayer(
            container,
            renderer_factory=lambda: ModernGLImGuiRenderer(isolated_gl_ctx),
        )
        try:
            target.use()
            layer.render(*_SIZE, dt=1 / 60)
            atlas = imgui.get_io().fonts.tex_data
            assert atlas.status == imgui.ImTextureStatus.ok
            assert atlas.get_tex_id() != 0
        finally:
            layer.release()


@pytest.mark.integration
class TestReleaseAndLifecycle:
    def test_release_is_idempotent(
        self, isolated_gl_ctx: Any, container: DIContainer
    ) -> None:
        layer = EditorLayer(
            container,
            renderer_factory=lambda: ModernGLImGuiRenderer(isolated_gl_ctx),
        )
        layer.release()
        layer.release()

    def test_the_renderer_releases_without_the_context(
        self, isolated_gl_ctx: Any
    ) -> None:
        """The renderer never owns the context, so releasing it must leave
        the context usable."""
        ctx = imgui.create_context()
        imgui.set_current_context(ctx)
        try:
            renderer = ModernGLImGuiRenderer(isolated_gl_ctx)
            renderer.release()
            # The context still works.
            assert isolated_gl_ctx.simple_framebuffer((8, 8)) is not None
        finally:
            imgui.destroy_context(ctx)


@pytest.mark.integration
class TestAttachEditor:
    def test_it_installs_a_pass_on_a_real_graph(
        self, isolated_gl_ctx: Any, container: DIContainer
    ) -> None:
        graph = RenderGraph(isolated_gl_ctx, *_SIZE)
        container.register_instance(RenderGraph, graph)
        layer = attach_editor(container)
        try:
            assert layer is not None
            assert graph.get_pass(PASS_NAME) is not None
        finally:
            if layer is not None:
                layer.release()
            graph.release()

    def test_the_installed_pass_draws_through_the_graph(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        """Being a `BaseRenderPass` is the whole integration: the existing
        pass loop drives the editor with no change to the frame loop."""
        graph = RenderGraph(isolated_gl_ctx, *_SIZE)
        container.register_instance(RenderGraph, graph)
        layer = attach_editor(container)
        assert layer is not None
        editor_pass = graph.get_pass(PASS_NAME)
        assert isinstance(editor_pass, ImGuiPass)
        try:
            # First frame emits no geometry, as ever.
            target.use()
            editor_pass.execute(isolated_gl_ctx, graph)
            target.use()
            editor_pass.execute(isolated_gl_ctx, graph)
            assert int((_pixels(target).sum(axis=1) > 0).sum()) > 100
        finally:
            layer.release()
            graph.release()

    def test_a_disabled_pass_draws_nothing(
        self, isolated_gl_ctx: Any, container: DIContainer, target: Any
    ) -> None:
        graph = RenderGraph(isolated_gl_ctx, *_SIZE)
        container.register_instance(RenderGraph, graph)
        layer = attach_editor(container)
        assert layer is not None
        editor_pass = graph.get_pass(PASS_NAME)
        assert editor_pass is not None
        try:
            editor_pass.enabled = False
            target.use()
            target.clear(0.0, 0.0, 0.0, 1.0)
            editor_pass.execute(isolated_gl_ctx, graph)
            assert int(_pixels(target).sum()) == 0
        finally:
            layer.release()
            graph.release()

    def test_a_resize_reaches_the_pass(
        self, isolated_gl_ctx: Any, container: DIContainer
    ) -> None:
        """`graph.resize()` forwards to every pass's `on_resize()`, which is
        how the editor tracks the window without watching events."""
        graph = RenderGraph(isolated_gl_ctx, *_SIZE)
        container.register_instance(RenderGraph, graph)
        layer = attach_editor(container)
        assert layer is not None
        editor_pass = graph.get_pass(PASS_NAME)
        assert isinstance(editor_pass, ImGuiPass)
        try:
            graph.resize(640, 480)
            assert (editor_pass._width, editor_pass._height) == (640, 480)
        finally:
            layer.release()
            graph.release()

    def test_it_declines_on_a_backend_with_no_gl_graph(self) -> None:
        """The Pygame backend registers a non-subclass stub under the same
        key. The editor is ModernGL-only and must decline, not
        half-install."""
        from pyguara.graphics.backends.pygame.stubs import PygameRenderGraph

        container = DIContainer()
        container.register_instance(RenderGraph, PygameRenderGraph(*_SIZE))
        assert attach_editor(container) is None

    def test_it_declines_with_no_graph_registered(self) -> None:
        assert attach_editor(DIContainer()) is None
