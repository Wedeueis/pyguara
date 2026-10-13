"""A renderer follows the window it draws into.

`IRenderer.width` and `height` were read-only, so nothing could tell a
renderer the window had changed -- and the ModernGL one builds its
orthographic projection from exactly those two numbers. Left on the size
it was constructed with, it maps the *original* pixel rectangle onto the
new framebuffer: the world is scaled by `new/old` on each axis
independently, which is a stretch whenever the two aspect ratios differ.

Measured on the demo at the window shape this was reported from, a
1280x720 renderer in a 1990x820 window stretched the world 1.37x
horizontally. The visible symptom was the sun drawn as an ellipse.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pytest

from pyguara.graphics.backends.headless_renderer import (
    HeadlessBackend,
    HeadlessUIRenderer,
)
from pyguara.graphics.protocols import IRenderer, UIRenderer


@pytest.mark.unit
class TestHeadlessRenderer:
    def test_it_adopts_the_new_size(self) -> None:
        renderer = HeadlessBackend(800, 600)
        assert (renderer.width, renderer.height) == (800, 600)

        renderer.resize(1990, 820)

        assert (renderer.width, renderer.height) == (1990, 820)

    def test_a_zero_size_is_refused(self) -> None:
        """Minimising reports zero, and a renderer that believed it would
        divide by it."""
        renderer = HeadlessBackend(800, 600)

        renderer.resize(0, 0)
        renderer.resize(-1, 100)

        assert (renderer.width, renderer.height) == (800, 600)

    def test_the_ui_renderer_takes_it_without_complaint(self) -> None:
        HeadlessUIRenderer().resize(1990, 820)


@pytest.mark.unit
class TestProtocolConformance:
    def test_every_renderer_can_be_resized(self) -> None:
        """Including the ones that have nothing to store. A renderer that
        quietly lacked the method would be found at the first resize, in a
        window, by a person."""
        for name in ("resize",):
            assert hasattr(IRenderer, name)
            assert hasattr(UIRenderer, name)

    def test_the_headless_pair_still_satisfies_the_protocols(self) -> None:
        assert isinstance(HeadlessBackend(800, 600), IRenderer)
        assert isinstance(HeadlessUIRenderer(), UIRenderer)

    def test_the_pygame_pair_does_too(self) -> None:
        import pygame

        from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
        from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer

        surface = pygame.Surface((320, 240))
        assert isinstance(PygameBackend(surface), IRenderer)
        assert isinstance(PygameUIRenderer(surface), UIRenderer)

    def test_the_pygame_renderer_reads_its_size_from_the_surface(self) -> None:
        """So its resize is a documented no-op rather than a lie: recording
        a size that disagreed with the surface would be worse than
        recording none."""
        import pygame

        from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend

        renderer = PygameBackend(pygame.Surface((320, 240)))
        renderer.resize(1990, 820)

        assert (renderer.width, renderer.height) == (320, 240)


@pytest.mark.integration
class TestModernGLRenderer:
    """The one whose projection actually depends on the size."""

    def test_the_projection_follows_the_window(self, isolated_gl_ctx) -> None:
        from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

        renderer = ModernGLRenderer(isolated_gl_ctx, 1280, 720)
        before = renderer._projection_bytes

        renderer.resize(1990, 820)

        assert (renderer.width, renderer.height) == (1990, 820)
        assert renderer._projection_bytes != before, (
            "The projection maps pixels one to one onto the framebuffer, so "
            "it is only correct while the two agree. Unchanged, the original "
            "rectangle is drawn stretched across the new one."
        )

    def test_an_unchanged_size_rebuilds_nothing(self, isolated_gl_ctx) -> None:
        from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

        renderer = ModernGLRenderer(isolated_gl_ctx, 1280, 720)
        before = renderer._projection_bytes

        renderer.resize(1280, 720)

        assert renderer._projection_bytes is before

    def test_a_zero_size_is_refused(self, isolated_gl_ctx) -> None:
        from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

        renderer = ModernGLRenderer(isolated_gl_ctx, 1280, 720)

        renderer.resize(0, 0)

        assert (renderer.width, renderer.height) == (1280, 720)

    def test_the_ui_surface_follows_the_window(self, isolated_gl_ctx) -> None:
        """It is uploaded whole and composited as a fullscreen quad, so a
        surface left at the original size is stretched across the new
        window -- which is what distorted the HUD."""
        from pyguara.graphics.backends.moderngl.ui_renderer import GLUIRenderer

        renderer = GLUIRenderer(isolated_gl_ctx, 1280, 720)

        renderer.resize(1990, 820)

        assert renderer._surface.get_size() == (1990, 820)
        assert renderer._texture.size == (1990, 820)
