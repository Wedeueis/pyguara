"""An asynchronously loaded GL texture must equal a synchronously loaded one.

`GLTextureLoader` is the loader that motivated splitting decode from
upload: one 2356x1824 jpg costs ~31 ms to decode, nearly two 60 Hz frames
(see "Resource loading, and the GIL" in `docs/guides/performance.md`). The
split is only safe if it is also *invisible* -- the same file through either
path has to produce the same texture, and "the same" here means the same
bytes on the GPU, not merely the same dimensions.

`isolated_gl_ctx` rather than the shared `gl_ctx`: these create textures and
a standalone context keeps that out of other GL tests.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.resources.loader import ITwoPhaseLoader
from pyguara.resources.manager import ResourceManager

pytest.importorskip("moderngl")

from pyguara.graphics.backends.moderngl.loaders import GLTextureLoader  # noqa: E402
from pyguara.graphics.backends.moderngl.texture import GLTexture  # noqa: E402

IMAGE = "assets/textures/pyguara_mascot.png"


@pytest.fixture
def _display() -> Any:
    """A dummy display, which `convert_alpha()` in `decode()` requires.

    Free in a running game -- the window exists long before any asset loads
    -- but a test has to ask for it, and the failure is explicit:
    "cannot convert without pygame.display initialized".
    """
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    already = pygame.display.get_init()
    if not already:
        pygame.display.init()
    surface = pygame.display.set_mode((64, 64))
    yield surface
    if not already:
        pygame.display.quit()


@pytest.fixture
def loader(isolated_gl_ctx: Any, _display: Any) -> GLTextureLoader:
    return GLTextureLoader(isolated_gl_ctx)


@pytest.mark.integration
class TestAsyncTextureMatchesSync:
    def test_the_pixels_are_identical(self, loader: GLTextureLoader) -> None:
        """The assertion that makes the split trustworthy."""
        synchronous = loader.load(IMAGE)

        manager = ResourceManager()
        manager.register_loader(loader)
        try:
            manager.wait_for(manager.preload([(IMAGE, GLTexture)]))
            asynchronous = manager.load(IMAGE, GLTexture)

            assert asynchronous.native_handle.read() == synchronous.native_handle.read()
        finally:
            manager.shutdown_decode_pool()

    def test_the_sampler_state_is_identical(self, loader: GLTextureLoader) -> None:
        """`TextureMeta.filter` is applied in `upload()`, so it would be the
        easy thing to drop when splitting the loader."""
        synchronous = loader.load(IMAGE)

        manager = ResourceManager()
        manager.register_loader(loader)
        try:
            manager.wait_for(manager.preload([(IMAGE, GLTexture)]))
            asynchronous = manager.load(IMAGE, GLTexture)

            assert asynchronous.native_handle.filter == synchronous.native_handle.filter
            assert (
                asynchronous.native_handle.swizzle == synchronous.native_handle.swizzle
            )
        finally:
            manager.shutdown_decode_pool()

    def test_the_dimensions_survive_the_split(self, loader: GLTextureLoader) -> None:
        """Width and height come back from `decode()` rather than being
        re-read from the surface in `upload()`, so they cross a thread
        boundary."""
        synchronous = loader.load(IMAGE)

        manager = ResourceManager()
        manager.register_loader(loader)
        try:
            manager.wait_for(manager.preload([(IMAGE, GLTexture)]))
            asynchronous = manager.load(IMAGE, GLTexture)

            assert (asynchronous.width, asynchronous.height) == (
                synchronous.width,
                synchronous.height,
            )
        finally:
            manager.shutdown_decode_pool()


@pytest.mark.integration
class TestLoaderContract:
    def test_it_satisfies_the_two_phase_protocol(self, loader: GLTextureLoader) -> None:
        assert isinstance(loader, ITwoPhaseLoader)

    def test_it_opts_in_to_threaded_decode(self, loader: GLTextureLoader) -> None:
        """Measured, not assumed: `pygame.image.load` scales 2.9-3.4x on
        four threads because SDL releases the GIL."""
        assert loader.threaded_decode is True

    def test_decode_touches_no_gl_state(self, loader: GLTextureLoader) -> None:
        """What makes it safe on a worker. If `decode()` needed the
        context, every asynchronous texture load would be a race."""
        data, width, height = loader.decode(IMAGE, None)  # type: ignore[misc]

        assert isinstance(data, bytes)
        assert len(data) == width * height * 4

    def test_the_synchronous_path_is_unchanged(self, loader: GLTextureLoader) -> None:
        """`load()` still does both halves in one call, so existing callers
        are untouched by the split."""
        texture = loader.load(IMAGE)
        assert isinstance(texture, GLTexture)
        assert texture.width > 0
