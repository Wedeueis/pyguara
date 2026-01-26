"""Framebuffer management for multi-pass rendering.

This module provides a wrapper around ModernGL framebuffers and a manager
for coordinating FBO lifecycle (creation, resize, cleanup).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pyguara.common.types import Color

if TYPE_CHECKING:
    import moderngl


class Framebuffer:
    """Wrapper around a ModernGL framebuffer with associated texture.

    Provides a higher-level interface for render-to-texture operations,
    including automatic texture creation and resize support.
    """

    def __init__(
        self,
        ctx: "moderngl.Context",
        name: str,
        width: int,
        height: int,
        *,
        samples: int = 0,
        dtype: str = "f1",
    ) -> None:
        """Create a new framebuffer.

        Args:
            ctx: The ModernGL context.
            name: Identifier for this framebuffer.
            width: Width in pixels.
            height: Height in pixels.
            samples: Number of MSAA samples (0 for no multisampling).
            dtype: Data type for the texture ('f1' for 8-bit, 'f2' for 16-bit).
        """
        self._ctx = ctx
        self._name = name
        self._width = width
        self._height = height
        self._samples = samples
        self._dtype = dtype

        # Create backing texture and FBO
        self._texture: Optional["moderngl.Texture"] = None
        self._fbo: Optional["moderngl.Framebuffer"] = None
        self._create_resources()

    def _create_resources(self) -> None:
        """Create the texture and framebuffer objects."""
        # Create color texture
        self._texture = self._ctx.texture(
            (self._width, self._height),
            components=4,
            dtype=self._dtype,
            samples=self._samples,
        )
        self._texture.filter = (
            self._ctx.LINEAR,
            self._ctx.LINEAR,
        )

        # Create framebuffer with texture attachment
        self._fbo = self._ctx.framebuffer(color_attachments=[self._texture])

    @property
    def name(self) -> str:
        """Identifier for this framebuffer."""
        return self._name

    @property
    def width(self) -> int:
        """Width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Height in pixels."""
        return self._height

    @property
    def texture(self) -> "moderngl.Texture":
        """The backing texture that can be sampled from."""
        if self._texture is None:
            raise RuntimeError(f"Framebuffer '{self._name}' texture not initialized")
        return self._texture

    @property
    def fbo(self) -> "moderngl.Framebuffer":
        """The underlying ModernGL framebuffer object."""
        if self._fbo is None:
            raise RuntimeError(f"Framebuffer '{self._name}' FBO not initialized")
        return self._fbo

    def bind(self) -> None:
        """Bind this framebuffer as the current render target."""
        if self._fbo is not None:
            self._fbo.use()

    def unbind(self) -> None:
        """Unbind this framebuffer, returning to the screen framebuffer."""
        self._ctx.screen.use()

    def clear(self, color: Color) -> None:
        """Clear the framebuffer with the specified color.

        Args:
            color: RGBA color to clear with.
        """
        if self._fbo is None:
            return

        r = color[0] / 255.0
        g = color[1] / 255.0
        b = color[2] / 255.0
        a = color[3] / 255.0 if len(color) > 3 else 1.0
        self._fbo.clear(r, g, b, a)

    def resize(self, width: int, height: int) -> None:
        """Resize the framebuffer to new dimensions.

        This releases the old resources and creates new ones.

        Args:
            width: New width in pixels.
            height: New height in pixels.
        """
        if width == self._width and height == self._height:
            return

        self._release_resources()
        self._width = width
        self._height = height
        self._create_resources()

    def _release_resources(self) -> None:
        """Release GPU resources."""
        if self._fbo is not None:
            self._fbo.release()
            self._fbo = None
        if self._texture is not None:
            self._texture.release()
            self._texture = None

    def release(self) -> None:
        """Release all GPU resources associated with this framebuffer."""
        self._release_resources()


class FramebufferManager:
    """Singleton manager for creating and coordinating framebuffers.

    Handles FBO lifecycle, including automatic resize when the window
    dimensions change and cleanup on shutdown.
    """

    def __init__(self, ctx: "moderngl.Context", width: int, height: int) -> None:
        """Initialize the framebuffer manager.

        Args:
            ctx: The ModernGL context.
            width: Initial viewport width.
            height: Initial viewport height.
        """
        self._ctx = ctx
        self._width = width
        self._height = height
        self._framebuffers: dict[str, Framebuffer] = {}

    @property
    def width(self) -> int:
        """Current viewport width."""
        return self._width

    @property
    def height(self) -> int:
        """Current viewport height."""
        return self._height

    def get_or_create(
        self,
        name: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        *,
        samples: int = 0,
        dtype: str = "f1",
    ) -> Framebuffer:
        """Get an existing framebuffer or create a new one.

        Args:
            name: Unique identifier for the framebuffer.
            width: Width in pixels (defaults to viewport width).
            height: Height in pixels (defaults to viewport height).
            samples: Number of MSAA samples (0 for no multisampling).
            dtype: Data type for the texture.

        Returns:
            The framebuffer instance.
        """
        if name in self._framebuffers:
            return self._framebuffers[name]

        # Use viewport dimensions if not specified
        w = width if width is not None else self._width
        h = height if height is not None else self._height

        fbo = Framebuffer(self._ctx, name, w, h, samples=samples, dtype=dtype)
        self._framebuffers[name] = fbo
        return fbo

    def get(self, name: str) -> Optional[Framebuffer]:
        """Get a framebuffer by name.

        Args:
            name: The framebuffer identifier.

        Returns:
            The framebuffer if it exists, None otherwise.
        """
        return self._framebuffers.get(name)

    def resize_all(self, width: int, height: int) -> None:
        """Resize all managed framebuffers to new dimensions.

        Should be called when the window is resized.

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        if width == self._width and height == self._height:
            return

        self._width = width
        self._height = height

        for fbo in self._framebuffers.values():
            fbo.resize(width, height)

    def release_all(self) -> None:
        """Release all framebuffers.

        Should be called during shutdown to clean up GPU resources.
        """
        for fbo in self._framebuffers.values():
            fbo.release()
        self._framebuffers.clear()

    def release(self, name: str) -> None:
        """Release a specific framebuffer.

        Args:
            name: The framebuffer identifier.
        """
        if name in self._framebuffers:
            self._framebuffers[name].release()
            del self._framebuffers[name]
