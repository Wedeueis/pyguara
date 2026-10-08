"""Resource loaders for ModernGL backend."""

from typing import cast

import pygame

import moderngl
from pyguara.graphics.backends.moderngl.texture import GLTexture
from pyguara.resources.meta import AssetMeta, TextureFilter, TextureMeta
from pyguara.resources.types import Resource


class GLTextureLoader:
    """Load image files into GPU textures for ModernGL rendering.

    Uses pygame.image to load the file, then uploads the pixel data
    to the GPU via ModernGL. The resulting GLTexture can be used
    with the ModernGLRenderer for hardware-accelerated drawing.

    Meta-aware: honours ``TextureMeta.filter`` (``nearest`` -> point
    sampling, ``linear`` -> bilinear). Other TextureMeta fields (mipmaps,
    wrap modes) are not applied yet.

    Also two-phase, which is what makes asynchronous loading worth having.
    ``decode()`` is pure CPU work on bytes and runs on a worker;
    ``upload()`` creates the GL texture and must run on the thread that
    owns the context. ``threaded_decode`` is True because the decode is
    measured to release the GIL -- `pygame.image.load` scales 2.9-3.4x on
    four threads (see "Resource loading, and the GIL" in
    ``docs/guides/performance.md``). It is the loader that motivated the
    split: one 2356x1824 jpg costs ~31 ms to decode, nearly two 60 Hz
    frames.

    ``load()`` is unchanged and still does both halves in one call, so
    every existing synchronous caller behaves exactly as before.
    """

    threaded_decode = True
    """`decode()` spends its time in SDL, which releases the GIL."""

    def __init__(self, ctx: moderngl.Context) -> None:
        """Initialize the loader with a ModernGL context.

        Args:
            ctx: The ModernGL context to create textures in.
        """
        self._ctx = ctx

    @property
    def supported_extensions(self) -> list[str]:
        """Return supported image file extensions."""
        return [".png", ".jpg", ".jpeg", ".bmp", ".tga"]

    def load(self, path: str) -> Resource:
        """Load an image file and create a GPU texture with default settings."""
        return self.load_with_meta(path, None)

    def load_with_meta(self, path: str, meta: AssetMeta | None) -> Resource:
        """Load an image file and create a GPU texture.

        The image is loaded via pygame, converted to RGBA bytes and
        uploaded top-down -- **not** flipped. `ModernGLRenderer`'s sprite
        quad pairs the screen's top edge with `v = 0` (see
        `_create_quad_vbo`), so its first row of texel data is the top of
        the sprite. A file loaded bottom-up draws upside down.

        Args:
            path: Full path to the image file.
            meta: Optional TextureMeta; ``filter`` selects point vs bilinear.

        Returns:
            A GLTexture resource ready for rendering.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            pygame.error: If the image format is unsupported.
        """
        texture_meta = meta if isinstance(meta, TextureMeta) else TextureMeta()

        # Load the image using pygame
        surface = pygame.image.load(path)

        # Convert to RGBA format
        surface = surface.convert_alpha()

        # Get dimensions
        width = surface.get_width()
        height = surface.get_height()

        # No vertical flip. This used to flip "for OpenGL (origin at
        # bottom-left)", which is the right instinct for a quad whose UVs
        # run bottom-up -- but `ModernGLRenderer`'s sprite quad does not:
        # its top vertex carries `v = 0`, so the data it wants is the
        # ordinary top-down order pygame already has. Every sprite loaded
        # from a file drew upside down, which no demo had noticed because
        # none of them loaded one -- the GL demos all generate their
        # textures at runtime through `GLTextureFactory` instead.
        data = pygame.image.tobytes(surface, "RGBA", False)

        # Create the GPU texture
        gl_texture = self._ctx.texture((width, height), 4, data)

        # Set texture parameters
        if texture_meta.get_filter_mode() is TextureFilter.NEAREST:
            gl_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        else:
            gl_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        # No swizzle, for the same reason as `ui_renderer.py`: the bytes
        # above are already RGBA, because that is what `tobytes` was asked
        # for. Reading them as BGRA swaps red with blue. Latent rather
        # than visible -- every GL demo generates its textures at runtime
        # through `GLTextureFactory`, which never had the swizzle, so this
        # path has no consumer that would have shown it.
        gl_texture.swizzle = "RGBA"

        return GLTexture(path, gl_texture, width, height)

    def decode(self, path: str, meta: AssetMeta | None) -> object:
        """Read and decode the image to raw RGBA bytes. Safe off-thread.

        Exactly the CPU half of `load_with_meta()`, in the same order and
        with the same calls, so an asynchronous load cannot drift from a
        synchronous one. Touches no GL state at all.

        **Requires `pygame.display` to be initialised**, because
        `convert_alpha()` reads the display's pixel format -- it raises
        "cannot convert without pygame.display initialized" otherwise. That
        is free in a running game, where the window exists long before any
        asset loads, but it means this is not usable from a bare script or
        an offscreen tool that never opened a display.

        It reads that format rather than mutating it, which is what makes
        concurrent decodes safe; the shared path is exercised by four
        workers at once in `docs/guides/performance.md`'s measurements and
        by the byte-for-byte comparison in
        `tests/integration/test_gl_async_texture.py`.

        `convert_alpha()` is kept rather than dropped in favour of letting
        `tobytes` convert, even though that would remove the display
        dependency: it would change the pixels for some source formats, and
        an async path that quietly disagreed with the sync one is a worse
        problem than a prerequisite.

        Args:
            path: Full path to the image file.
            meta: Unused here -- `TextureMeta.filter` is a sampler setting,
                which belongs to the texture and so to `upload()`. Accepted
                to satisfy the protocol.

        Returns:
            `(rgba_bytes, width, height)`, which is all `upload()` needs.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            pygame.error: If the image format is unsupported.
        """
        surface = pygame.image.load(path)
        surface = surface.convert_alpha()
        # No vertical flip, for the reason `load_with_meta` documents at
        # length: this renderer's sprite quad pairs the top edge with v=0.
        return (
            pygame.image.tobytes(surface, "RGBA", False),
            surface.get_width(),
            surface.get_height(),
        )

    def upload(self, path: str, decoded: object, meta: AssetMeta | None) -> Resource:
        """Create the GPU texture from decoded bytes. Main thread only.

        Args:
            path: Full path, kept on the resource.
            decoded: The `(bytes, width, height)` tuple from `decode()`.
            meta: Optional TextureMeta; ``filter`` selects point vs bilinear.

        Returns:
            A GLTexture ready for rendering.
        """
        data, width, height = cast("tuple[bytes, int, int]", decoded)
        texture_meta = meta if isinstance(meta, TextureMeta) else TextureMeta()

        gl_texture = self._ctx.texture((width, height), 4, data)
        if texture_meta.get_filter_mode() is TextureFilter.NEAREST:
            gl_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        else:
            gl_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        gl_texture.swizzle = "RGBA"

        return GLTexture(path, gl_texture, width, height)
