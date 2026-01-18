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
        """Release the GPU texture resources.

        Should be called when the texture is no longer needed to free GPU memory.
        """
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
    ) -> Texture:
        """Create a GLTexture from raw RGBA pixel data.

        Note: The data should be in standard top-to-bottom row order.
        This factory handles the vertical flip required for OpenGL's
        bottom-left origin coordinate system.

        Args:
            path: Identifier/name for the texture.
            data: Raw RGBA pixel data (4 bytes per pixel, top-to-bottom).
            width: Width of the image in pixels.
            height: Height of the image in pixels.

        Returns:
            A GLTexture ready for GPU rendering.
        """
        # Flip the image vertically for OpenGL (origin at bottom-left)
        # Each row is width * 4 bytes (RGBA)
        row_size = width * 4
        flipped_data = b"".join(
            data[i : i + row_size]
            for i in range((height - 1) * row_size, -1, -row_size)
        )

        # Create GPU texture
        gl_texture = self._ctx.texture((width, height), 4, flipped_data)
        gl_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        return GLTexture(path, gl_texture, width, height)
