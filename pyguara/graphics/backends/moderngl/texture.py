"""ModernGL texture implementation."""

import moderngl
from pyguara.resources.types import Texture


class GLTexture(Texture):
    """GPU texture wrapper for ModernGL.

    Wraps a moderngl.Texture object and provides the standard Texture
    interface expected by the engine. The texture data lives on the GPU
    and can be efficiently used for rendering.
    """

    def __init__(
        self,
        path: str,
        gl_texture: moderngl.Texture,
        tex_width: int,
        tex_height: int,
    ) -> None:
        """Initialize the GL texture.

        Args:
            path: The source file path.
            gl_texture: The ModernGL texture object.
            tex_width: Width of the texture in pixels.
            tex_height: Height of the texture in pixels.
        """
        super().__init__(path)
        self._texture = gl_texture
        self._width = tex_width
        self._height = tex_height
        self._released = False

    @property
    def width(self) -> int:
        """Get the width of the texture in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Get the height of the texture in pixels."""
        return self._height

    @property
    def native_handle(self) -> moderngl.Texture:
        """Returns the internal ModernGL texture.

        This is used by the renderer to bind the texture for drawing.
        """
        return self._texture

    def release(self) -> None:
        """Release the GPU texture, freeing its VRAM.

        Idempotent: `ResourceManager` calls this on every eviction, and a
        backend teardown may reach the same texture, so a second call has
        to be harmless. It previously left `self._texture` in place, so
        the second call went through to moderngl on an already-released
        texture.
        """
        if self._released:
            return
        self._released = True
        if self._texture is not None:
            self._texture.release()


class GLTextureFactory:
    """Factory for creating GLTexture instances from raw image data."""

    def __init__(self, ctx: moderngl.Context) -> None:
        """Initialize the factory with a ModernGL context.

        Args:
            ctx: The ModernGL context to create textures in.
        """
        self._ctx = ctx

    def create_from_bytes(
        self, path: str, data: bytes, width: int, height: int
    ) -> GLTexture:
        """Create a GLTexture from raw RGBA pixel data.

        Rows go up in the order given, top row first -- which is what
        every producer in this tree already has: pygame's
        `image.tobytes(..., False)` and PIL's `tobytes("raw", "RGBA")`.

        This used to reverse them, on the reasoning that OpenGL's origin
        is bottom-left. That is true of GL in general and not of this
        renderer: the sprite quad carries `v = 0` on its *top* vertex
        (`_create_quad_vbo`) and the projection inverts Y
        (`top = 0.0, bottom = height`), so it wants plain top-down rows --
        exactly what `loaders.py` hands `ctx.texture` directly, and what
        `tests/integration/test_gl_texture_orientation.py` pins.

        The flip was not harmless. `draw_text` pre-flipped to cancel it,
        so text came out right by luck, while `SpriteSheet` handed over
        PIL's top-down bytes and every frame uploaded upside down -- latent
        only because no GL demo loads a sheet.

        Args:
            path: Identifier/name for the texture.
            data: Raw RGBA pixel data, 4 bytes per pixel, top row first.
            width: Width of the image in pixels.
            height: Height of the image in pixels.

        Returns:
            A GLTexture ready for GPU rendering.
        """
        gl_texture = self._ctx.texture((width, height), 4, data)
        gl_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        return GLTexture(path, gl_texture, width, height)
