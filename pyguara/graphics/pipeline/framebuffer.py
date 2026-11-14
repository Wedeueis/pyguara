"""Framebuffer management for multi-pass rendering.

A `Framebuffer` is a buffer in the native wgpu frame, drawn into and
sampled from by the render graph's passes. `FramebufferManager` names
them, owns their format, and resizes them with the window.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyguara.graphics.pipeline.device import WgpuFramebuffer as Framebuffer

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.device import GraphicsDevice

__all__ = ["Framebuffer", "FramebufferManager"]


class FramebufferManager:
    """Singleton manager for creating and coordinating framebuffers.

    Handles FBO lifecycle, including automatic resize when the window
    dimensions change and cleanup on shutdown.
    """

    def __init__(self, device: GraphicsDevice, width: int, height: int) -> None:
        """Initialize the framebuffer manager.

        Args:
            device: The device buffers are made on.
            width: Initial viewport width.
            height: Initial viewport height.
        """
        self._device = device
        self._width = width
        self._height = height
        self._framebuffers: dict[str, Framebuffer] = {}
        self._declared: dict[str, str] = {}

    @property
    def device(self) -> GraphicsDevice:
        """The device this manager's buffers are made on."""
        return self._device

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
        what lets the two kinds of caller coexist: `RenderGraph` declares
        `lightmap` as `f2` because the chain needs the range, and
        `LightPass` later asks for the same buffer without caring, and
        gets the format the declaration named.

        Args:
            name: Unique identifier for the framebuffer.
            width: Required width in pixels. None uses the viewport's.
            height: Required height in pixels. None uses the viewport's.
            samples: Required MSAA sample count. None accepts any.
            dtype: Required texture data type, e.g. `"f1"` or `"f2"`.
                None accepts whatever exists, and creates the declared
                format, or `"f1"` if the name was never declared.

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

        fbo = self._device.create_target(
            name,
            w,
            h,
            samples=samples if samples is not None else 0,
            dtype=self._format_for(name, dtype),
        )
        self._framebuffers[name] = fbo
        return fbo

    def declare(self, name: str, *, dtype: str) -> None:
        """Record the format `name` is created with, before anything creates it.

        Declaring is not allocating: the framebuffer is still built by the
        first `get_or_create` that needs it, at the declared format rather
        than the 8-bit default. That is what gives a chain of buffers one
        owner -- without it, the format is whichever caller happens to run
        first, and every other caller has to either pass the same dtype or
        accept what it finds.

        Args:
            name: The framebuffer name.
            dtype: The texture data type to create it with.

        Raises:
            ValueError: If `name` was already declared as a different format,
                or already exists in one.
        """
        existing = self._framebuffers.get(name)
        if existing is not None:
            self._reject_conflict(existing, None, None, None, dtype)

        declared = self._declared.get(name)
        if declared is not None and declared != dtype:
            raise ValueError(
                f"Framebuffer '{name}' is already declared as {declared!r}; "
                f"'{dtype}' would silently win or lose depending on which "
                "declaration ran first. Declare it once."
            )

        self._declared[name] = dtype

    def declared_format(self, name: str) -> str | None:
        """Report the format `name` was declared with, if any.

        Args:
            name: The framebuffer name.

        Returns:
            The declared data type, or None.
        """
        return self._declared.get(name)

    def _format_for(self, name: str, requested: str | None) -> str:
        """Resolve the data type to create `name` with.

        Args:
            name: The framebuffer name.
            requested: The caller's requirement, or None.

        Returns:
            The requirement if there is one, else the declared format, else
            the 8-bit default.
        """
        if requested is not None:
            return requested
        return self._declared.get(name, "f1")

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
