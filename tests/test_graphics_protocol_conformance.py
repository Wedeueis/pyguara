"""Every protocol in `pyguara.graphics.protocols` is checkable at runtime.

Five of the then-seven carried `@runtime_checkable` and two -- `IFramebuffer` and
`IRenderPass` -- did not, for no reason the module recorded. The cost was not
theoretical: the parity tests added by the backends audit assert a shipped
implementation satisfies its protocol via `isinstance`, and those two were the
ones that could not be covered. That is the same gap that let the pygame stubs
drift undetected.

The enumeration test is the guard against the split coming back; the two
conformance tests are the coverage it unblocks.
"""

from __future__ import annotations

import inspect
from typing import Protocol
from unittest.mock import MagicMock

import pytest

from pyguara.graphics import protocols
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.passes import FinalPass, PostProcessPass
from pyguara.graphics.protocols import IFramebuffer, IRenderPass


def graphics_protocols() -> list[type]:
    """Every Protocol class the module defines, in declaration order."""
    return [
        member
        for _, member in inspect.getmembers(protocols, inspect.isclass)
        if Protocol in member.__bases__ and member.__module__ == protocols.__name__
    ]


class TestEveryProtocolIsRuntimeCheckable:
    def test_the_module_defines_the_expected_protocols(self) -> None:
        """A new protocol should fail this until it is added below -- which is
        the prompt to decide whether it is runtime-checkable too."""
        assert {p.__name__ for p in graphics_protocols()} == {
            "IFramebuffer",
            "IRenderPass",
            "IRenderer",
            "IWindowBackend",
            "IWindowChrome",
            "Renderable",
            "ShapeBatchRenderer",
            "ShapeRenderer",
            "TextureFactory",
            "UIRenderer",
        }

    @pytest.mark.parametrize(
        "protocol", graphics_protocols(), ids=lambda p: str(p.__name__)
    )
    def test_it_is_runtime_checkable(self, protocol: type) -> None:
        assert getattr(protocol, "_is_runtime_protocol", False), (
            f"{protocol.__name__} cannot be used with isinstance(), so no parity "
            "test can assert an implementation satisfies it"
        )


class TestFramebufferConforms:
    """`Framebuffer` against `IFramebuffer`, over a mock context -- what the
    framebuffer *does* needs GL, but which members it carries does not."""

    def test_framebuffer_conforms(self) -> None:
        ctx = MagicMock()
        ctx.texture.side_effect = lambda *a, **k: MagicMock()
        ctx.framebuffer.side_effect = lambda *a, **k: MagicMock()

        fbo = FramebufferManager(ctx, 800, 600).get_or_create("world")

        assert isinstance(fbo, IFramebuffer)


class TestRenderPassesConform:
    """The two passes that need no GL context to construct. The ctx-taking
    passes compile shaders in `__init__` and are covered by the integration
    suite instead."""

    def test_final_pass_conforms(self) -> None:
        assert isinstance(FinalPass(MagicMock()), IRenderPass)

    def test_post_process_pass_conforms(self) -> None:
        assert isinstance(PostProcessPass(MagicMock()), IRenderPass)


class TestShapeBatchRendererIsACapability:
    """`ShapeBatchRenderer` is optional by design, so both answers matter.

    A caller picks its route with `isinstance`, which means "does not
    satisfy it" is as much a contract as "does". If the pygame backend ever
    grows a `render_shapes` that just loops, `Sparks` would start handing
    it batches and these would catch the change rather than it being
    noticed as a slowdown.
    """

    def test_the_moderngl_renderer_satisfies_it(self) -> None:
        from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

        assert hasattr(ModernGLRenderer, "render_shapes")

    def test_the_pygame_backend_does_not(self) -> None:
        from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend

        assert not hasattr(PygameBackend, "render_shapes")

    def test_the_headless_backend_does_not(self) -> None:
        from pyguara.graphics.backends.headless_renderer import HeadlessBackend

        assert not hasattr(HeadlessBackend, "render_shapes")
