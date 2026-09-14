"""Framebuffer management for multi-pass rendering.

This module provides a wrapper around ModernGL framebuffers and a manager
for coordinating FBO lifecycle (creation, resize, cleanup).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
        ctx: moderngl.Context,
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
        self._texture: moderngl.Texture | None = None
        self._fbo: moderngl.Framebuffer | None = None
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
    def samples(self) -> int:
        """MSAA sample count. 0 means no multisampling."""
        return self._samples

    @property
    def dtype(self) -> str:
        """Texture data type, e.g. `"f1"` (8-bit) or `"f2"` (16-bit float)."""
        return self._dtype

    @property
    def texture(self) -> moderngl.Texture:
        """The backing texture that can be sampled from."""
        if self._texture is None:
            raise RuntimeError(f"Framebuffer '{self._name}' texture not initialized")
        return self._texture

    @property
    def fbo(self) -> moderngl.Framebuffer:
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

    def __init__(self, ctx: moderngl.Context, width: int, height: int) -> None:
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
        width: int | None = None,
        height: int | None = None,
        *,
        samples: int | None = None,
        dtype: str | None = None,
    ) -> Framebuffer:
        """Get the framebuffer called `name`, creating it if it is new.

        **An argument you pass is a requirement, not a preference.** If
        `name` already exists with a different format, this raises rather
        than handing back the existing one. It used to hand it back
        silently, which is what turns a format mismatch into invisible
        data loss: a caller asking for a 16-bit float buffer and getting
        an 8-bit one has no way to tell, and the range simply disappears
        somewhere downstream.

        Arguments you leave out are not requirements. That distinction is
        what lets the two kinds of caller coexist: a game's bootstrap
        claims `lightmap` as `f2` because it needs the range, and
        `LightPass` later asks for the same buffer without caring, and
        gets the one that is there.

        Args:
            name: Unique identifier for the framebuffer.
            width: Required width in pixels. None uses the viewport's.
            height: Required height in pixels. None uses the viewport's.
            samples: Required MSAA sample count. None accepts any.
            dtype: Required texture data type, e.g. `"f1"` or `"f2"`.
                None accepts whatever exists, and creates `"f1"`.

        Returns:
            The framebuffer.

        Raises:
            ValueError: If `name` exists and any argument given here
                disagrees with it.
        """
        existing = self._framebuffers.get(name)
        if existing is not None:
            self._reject_conflict(existing, width, height, samples, dtype)
            return existing

        # Use viewport dimensions if not specified
        w = width if width is not None else self._width
        h = height if height is not None else self._height

        fbo = Framebuffer(
            self._ctx,
            name,
            w,
            h,
            samples=samples if samples is not None else 0,
            dtype=dtype if dtype is not None else "f1",
        )
        self._framebuffers[name] = fbo
        return fbo

    @staticmethod
    def _reject_conflict(
        existing: Framebuffer,
        width: int | None,
        height: int | None,
        samples: int | None,
        dtype: str | None,
    ) -> None:
        """Raise if any requested attribute disagrees with `existing`.

        Args:
            existing: The framebuffer already registered under the name.
            width: Requested width, or None for no requirement.
            height: Requested height, or None for no requirement.
            samples: Requested sample count, or None.
            dtype: Requested data type, or None.

        Raises:
            ValueError: Naming every attribute that disagrees, what was
                asked for and what is actually there.
        """
        mismatches = [
            (label, wanted, actual)
            for label, wanted, actual in (
                ("width", width, existing.width),
                ("height", height, existing.height),
                ("samples", samples, existing.samples),
                ("dtype", dtype, existing.dtype),
            )
            if wanted is not None and wanted != actual
        ]
        if not mismatches:
            return

        detail = ", ".join(
            f"{label}={wanted!r} but it is {actual!r}"
            for label, wanted, actual in mismatches
        )
        raise ValueError(
            f"framebuffer {existing.name!r} already exists and does not "
            f"match: asked for {detail}. Whoever created it first wins; "
            f"claim it with the format you need before anything else asks "
            f"for it, or drop the argument if you do not mind."
        )

    def get(self, name: str) -> Framebuffer | None:
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
