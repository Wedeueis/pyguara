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
class TestWgpuRenderer:
    """The size the world is drawn at, which is not the window's own target."""

    def test_it_adopts_the_render_size(self, wgpu_frame) -> None:
        from pyguara.graphics.backends.wgpu import WgpuRenderer

        renderer = WgpuRenderer(wgpu_frame(1280, 720))

        renderer.resize(1990, 820)

        assert (renderer.width, renderer.height) == (1990, 820)

    def test_it_leaves_the_window_target_alone(self, wgpu_frame) -> None:
        """The main target is the window, sized by the render graph. The
        renderer resizing it to the render size cut a letterboxed window --
        editor included -- down to the game's frame."""
        from pyguara.graphics.backends.wgpu import WgpuRenderer

        frame = wgpu_frame(1980, 720)
        renderer = WgpuRenderer(frame)

        renderer.resize(1280, 720)

        assert (frame.gpu.width, frame.gpu.height) == (1980, 720)

    def test_a_zero_size_is_refused(self, wgpu_frame) -> None:
        from pyguara.graphics.backends.wgpu import WgpuRenderer

        renderer = WgpuRenderer(wgpu_frame(1280, 720))

        renderer.resize(0, 0)
        renderer.resize(-1, 100)

        assert (renderer.width, renderer.height) == (1280, 720)
