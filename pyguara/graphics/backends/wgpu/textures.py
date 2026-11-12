"""The wgpu backend's textures: RGBA bytes decoded in Rust, not pygame surfaces.

A texture on this backend is the pixels the GPU will be given, held once on
the CPU: `ImageTexture`. Its loader decodes with `decode_image`
(`rust/src/imaging.rs`) and its factory wraps bytes a caller already has --
a sprite sheet's cells, rasterised geometry. Neither imports pygame.

The pixels stay on the CPU after upload because the upload is lazy and
per-frame cached (`GpuFrame.image`), and because a texture that outlives a
device -- the window closed and reopened -- has to be uploadable again.
"""

from __future__ import annotations

from pyguara import native
from pyguara.log import get_logger
from pyguara.resources.meta import AssetMeta, TextureFilter, TextureMeta
from pyguara.resources.types import Resource, Texture

logger = get_logger(__name__)


class ImageTexture(Texture):
    """An image as RGBA bytes, top row first.

    Attributes:
        pixels: `width * height * 4` bytes.
        smooth: Sample bilinearly when scaled or turned, as `filter: linear`
            in the image's meta asks.
    """

    def __init__(
        self, path: str, pixels: bytes, width: int, height: int, smooth: bool = False
    ) -> None:
        """Wrap decoded pixels.

        Args:
            path: The source file, or a name for pixels made in memory.
            pixels: RGBA bytes, top row first.
            width: Width in pixels.
            height: Height in pixels.
            smooth: Whether the meta asked for `filter: linear`.

        Raises:
            ValueError: If the byte count does not match the size.
        """
        super().__init__(path)
        if len(pixels) != width * height * 4:
            raise ValueError(
                f"'{path}': {width}x{height} RGBA is {width * height * 4} bytes, "
                f"got {len(pixels)}"
            )
        self.pixels = pixels
        self._width = width
        self._height = height
        self.smooth = smooth

    @property
    def width(self) -> int:
        """Width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Height in pixels."""
        return self._height

    @property
    def native_handle(self) -> ImageTexture:
        """The texture itself: its pixels are what a renderer reads."""
        return self


class NativeImageLoader:
    """Decode image files into `ImageTexture`s, in Rust.

    Registered instead of `PygameImageLoader` on the wgpu backend. Honours
    the same meta: `filter` travels on the texture, `premultiply_alpha`
    multiplies the colour by alpha once, at load.
    """

    @property
    def supported_extensions(self) -> list[str]:
        """The formats `decode_image` is built with."""
        return [".png", ".jpg", ".jpeg", ".bmp", ".tga"]

    def load(self, path: str) -> Resource:
        """Load a texture with default settings."""
        return self.load_with_meta(path, None)

    def load_with_meta(self, path: str, meta: AssetMeta | None) -> Resource:
        """Decode a file, applying its meta.

        Args:
            path: The image file.
            meta: Its `TextureMeta`, or None for the defaults.

        Returns:
            An `ImageTexture`.

        Raises:
            OSError: If the file cannot be read or decoded.
        """
        texture_meta = meta if isinstance(meta, TextureMeta) else TextureMeta()
        module = native.require_extension("The wgpu image loader")
        pixels, width, height = module.decode_image(path)
        if texture_meta.premultiply_alpha:
            pixels = module.premultiply_rgba(pixels)
        smooth = texture_meta.get_filter_mode() is TextureFilter.LINEAR
        return ImageTexture(path, bytes(pixels), width, height, smooth=smooth)


class ImageTextureFactory:
    """`TextureFactory` for the wgpu backend: bytes in, `ImageTexture` out."""

    def create_from_bytes(
        self, path: str, data: bytes, width: int, height: int
    ) -> Texture:
        """Wrap RGBA pixel data, top row first.

        Args:
            path: A name for the texture.
            data: RGBA bytes, top row first.
            width: Width in pixels.
            height: Height in pixels.

        Returns:
            An `ImageTexture` holding a copy of `data`.
        """
        return ImageTexture(path, bytes(data), width, height)
