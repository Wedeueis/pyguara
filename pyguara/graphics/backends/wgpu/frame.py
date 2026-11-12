"""What the wgpu window, world renderer and UI renderer share.

All three draw into one `NativeGpu` frame, in the order they are called,
so they hold one `GpuFrame` between them: the native device, and the two
caches that turn CPU-side pixels into GPU textures.

**Text is rasterised in Rust (`NativeFont`) and cached as a texture.** A
string is rendered once, in white, and tinted by the instance colour when
drawn -- so a damage number fading out, or the same label in two colours,
is one texture. The face is the engine's bundled default
(`pyguara.graphics.fonts`), which the pygame renderer opens too.

**Nothing is freed in the middle of a frame.** A primitive already pushed
names its texture by id, and the frame is only drawn at `end_frame`. So an
eviction queues the id and `after_frame` frees it once the frame that
might still use it has been rendered.
"""

from __future__ import annotations

import math
import sys
import weakref
from collections import OrderedDict
from typing import Any

from pyguara import native
from pyguara.graphics.backends.wgpu.textures import ImageTexture
from pyguara.log import get_logger

logger = get_logger(__name__)

# How many distinct strings stay rasterised. A HUD is a few dozen; a room
# full of damage numbers, each a different value, is a few hundred.
TEXT_CACHE_LIMIT = 1024

FontKey = tuple[int, bool, bool]
"""Size, bold, italic."""

GlyphRun = tuple[int, int, int]
"""Texture id, width and height of one rasterised string."""

ImageRun = tuple[int, int, int]
"""Texture id, width and height of one uploaded image."""

_warned_unusable: set[str] = set()


def _owner(texture: object) -> object | None:
    """Return the object whose pixels `texture` names, or None.

    An `ImageTexture` is its own; a pygame surface, or a texture wrapping
    one, is the surface -- recognised only if a game already imported
    pygame.
    """
    if isinstance(texture, ImageTexture):
        return texture
    pygame = sys.modules.get("pygame")
    if pygame is None:
        return None
    surface_type: type = pygame.Surface
    if isinstance(texture, surface_type):
        return texture
    handle: object = getattr(texture, "native_handle", None)
    if isinstance(handle, surface_type):
        return handle
    return None


def _pixels(owner: object) -> tuple[bytes, int, int]:
    """Read RGBA bytes and a size from what `_owner` returned."""
    if isinstance(owner, ImageTexture):
        return owner.pixels, owner.width, owner.height
    pygame = sys.modules["pygame"]
    width, height = owner.get_size()  # type: ignore[attr-defined]
    return pygame.image.tobytes(owner, "RGBA"), width, height


def _warn_unusable(texture: object) -> None:
    kind = type(texture).__name__
    if kind not in _warned_unusable:
        _warned_unusable.add(kind)
        logger.warning(
            "The wgpu renderer cannot draw a %s: it needs an ImageTexture, or "
            "a pygame.Surface a game made itself. Drawing nothing.",
            kind,
        )


# pygame draws a circle of radius r inside a 2r-pixel box whose centre is
# the *corner* of the pixel it was given, and its edge sits a little inside
# the true radius. Measured over r = 1 to 40 against `pygame.draw.circle`:
# 492 differing pixels in total with this shrink, 1104 with none, and
# 2456 when centred on the pixel's centre instead.
CIRCLE_SHRINK = 0.25


def line_quad(
    start_x: float, start_y: float, end_x: float, end_y: float, width: int
) -> tuple[float, float, float, float, float]:
    """Turn a pygame-style line into the quad that covers the same pixels.

    pygame does not draw a thick line as a rotated rectangle. It draws a
    one-pixel line and repeats it `width` times along the *minor* axis --
    up and down for a mostly horizontal line, side to side for a steep
    one. So its thickness is measured along an axis, not across the line;
    an even width sits half a pixel towards positive on that axis; and
    both end pixels are drawn.

    Args:
        start_x: Start, x. Truncated to a pixel as pygame truncates it.
        start_y: Start, y.
        end_x: End, x.
        end_y: End, y.
        width: Thickness in pixels, at least 1.

    Returns:
        `(from_x, from_y, to_x, to_y, thickness)` for `NativeGpu.line`.
    """
    from_x, from_y = int(start_x) + 0.5, int(start_y) + 0.5
    to_x, to_y = int(end_x) + 0.5, int(end_y) + 0.5
    along_x, along_y = to_x - from_x, to_y - from_y
    length = math.hypot(along_x, along_y)
    if length == 0.0:
        # A single point: `width` pixels along y, as a flat line stacks.
        shift = 0.5 if width % 2 == 0 else 0.0
        return (from_x - 0.5, from_y + shift, to_x + 0.5, to_y + shift, float(width))
    major = max(abs(along_x), abs(along_y))
    # Half a pixel past each end, measured along the major axis.
    reach = 0.5 * length / major
    reach_x, reach_y = along_x / length * reach, along_y / length * reach
    shift_x = shift_y = 0.0
    if width % 2 == 0:
        if abs(along_x) >= abs(along_y):
            shift_y = 0.5
        else:
            shift_x = 0.5
    return (
        from_x - reach_x + shift_x,
        from_y - reach_y + shift_y,
        to_x + reach_x + shift_x,
        to_y + reach_y + shift_y,
        # Axis-measured thickness, seen across the line.
        width * major / length,
    )


class GpuFrame:
    """The native device plus the texture caches drawn through it.

    Attributes:
        gpu: The `NativeGpu`.
    """

    def __init__(
        self,
        width: int,
        height: int,
        window: tuple[str, int, int] | None = None,
        vsync: bool = True,
    ) -> None:
        """Open a device with an offscreen target, and a window's if given.

        Args:
            width: Target width in pixels.
            height: Target height in pixels.
            window: `(kind, window, display)` naming a native window to
                present to -- see `NativeGpu.for_window`. None renders
                offscreen only. If the window cannot be drawn to, this
                logs why and carries on offscreen, so `gpu.has_surface`
                is what says which happened.
            vsync: Wait for the display's refresh when presenting.

        Raises:
            RuntimeError: If the extension cannot be imported or no
                graphics adapter can be opened at all.
        """
        extension = native.require_extension("The wgpu rendering backend")
        self._extension = extension
        self.gpu: Any = None
        if window is not None:
            try:
                self.gpu = extension.NativeGpu.for_window(*window, width, height, vsync)
            except (RuntimeError, ValueError) as error:
                logger.warning(
                    f"wgpu could not draw to the {window[0]} window directly "
                    f"({error}); rendering offscreen and copying each frame "
                    f"to it instead, which is much slower."
                )
        if self.gpu is None:
            self.gpu = extension.NativeGpu(width, height)
        how = "to the window" if self.gpu.has_surface else "offscreen"
        logger.info(f"wgpu renderer on {self.gpu.adapter}, drawing {how}")
        self._fonts: dict[FontKey, Any] = {}
        self._text: OrderedDict[tuple[FontKey, str], GlyphRun] = OrderedDict()
        self._images: dict[tuple[int, bool], tuple[weakref.ref[object], ImageRun]] = {}
        self._doomed: list[int] = []

    # -- fonts and text ----------------------------------------------------

    def font(self, size: int, bold: bool = False, italic: bool = False) -> Any:
        """Return the `NativeFont` for a size and style, made once.

        The engine's default face (`pyguara.graphics.fonts`), rasterised in
        Rust; see `rust/src/text.rs` for how its layout follows SDL_ttf's.
        """
        key = (size, bold, italic)
        font = self._fonts.get(key)
        if font is None:
            font = self._extension.NativeFont(max(1, size), bold, italic)
            self._fonts[key] = font
        return font

    def text(
        self, text: str, size: int, bold: bool = False, italic: bool = False
    ) -> GlyphRun | None:
        """Return the texture holding a string, rasterising it if new.

        Args:
            text: What to draw.
            size: Font size.
            bold: Bold style.
            italic: Italic style.

        Returns:
            `(texture, width, height)`, or None for a string with no
            pixels -- empty, or all of it zero-width.
        """
        key = ((size, bold, italic), text)
        found = self._text.get(key)
        if found is not None:
            self._text.move_to_end(key)
            return found
        pixels, width, height = self.font(size, bold, italic).render(text)
        if width == 0 or height == 0:
            return None
        texture = self.gpu.create_texture(width, height, pixels)
        run = (texture, width, height)
        self._text[key] = run
        if len(self._text) > TEXT_CACHE_LIMIT:
            _, (evicted, _, _) = self._text.popitem(last=False)
            self._doomed.append(evicted)
        return run

    # -- images ------------------------------------------------------------

    def image(self, texture: object, smooth: bool = False) -> ImageRun | None:
        """Return the GPU texture for an image, uploading it on first use.

        The upload happens once per image object and filter. Pixels changed
        *after* the first draw are not seen: this is for images, which do
        not change, not for scratch buffers.

        Takes an `ImageTexture` -- what this backend's loader and factory
        make -- or, for a game that made one itself, a `pygame.Surface` or
        a texture wrapping one. A surface is only recognised if pygame is
        already imported; this never imports it.

        Args:
            texture: The image.
            smooth: Sample bilinearly when scaled or turned, rather than
                texel for texel. A texture's meta says which.

        Returns:
            `(texture id, width, height)`, or None for something that is
            not an image, which is logged once per type.
        """
        owner = _owner(texture)
        if owner is None:
            _warn_unusable(texture)
            return None
        key = (id(owner), smooth)
        found = self._images.get(key)
        if found is not None and found[0]() is owner:
            return found[1]
        pixels, width, height = _pixels(owner)
        uploaded: int = self.gpu.create_texture(width, height, pixels, smooth)
        run = (uploaded, width, height)

        # `id()` is reused once an image is collected, so the entry has to
        # go when the image does or a new one would inherit its pixels.
        def forget(_: weakref.ref[object]) -> None:
            gone = self._images.pop(key, None)
            if gone is not None:
                self._doomed.append(gone[1][0])

        self._images[key] = (weakref.ref(owner, forget), run)
        return run

    def once_rgba(self, pixels: bytes, width: int, height: int) -> int:
        """Upload RGBA pixels for this frame only.

        For pixels made on the spot -- a polygon rasterised on the CPU --
        that nothing will ask for again.

        Args:
            pixels: RGBA bytes, top row first.
            width: Width in pixels.
            height: Height in pixels.

        Returns:
            A texture id, freed after the frame is drawn.
        """
        texture: int = self.gpu.create_texture(width, height, pixels)
        self._doomed.append(texture)
        return texture

    # -- frame boundary ----------------------------------------------------

    def after_frame(self) -> None:
        """Free what was evicted while the last frame was being built."""
        for texture in self._doomed:
            self.gpu.destroy_texture(texture)
        self._doomed.clear()
