"""Render graph - orchestrates multi-pass rendering.

The RenderGraph manages the sequence of render passes that compose
the final frame. It provides access to shared resources like the
FramebufferManager and coordinates pass execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.render_pass import BaseRenderPass

if TYPE_CHECKING:
    import moderngl


class RenderGraph:
    """Orchestrates the rendering pipeline by executing passes in order.

    The graph maintains:
    - A FramebufferManager for FBO lifecycle
    - An ordered list of render passes
    - Methods to add/remove/query passes

    Typical pass order for a 2D game with lighting and post-processing:
    1. WorldPass - Render sprites to world FBO
    2. LightPass - Render lights to light FBO (Phase C)
    3. CompositePass - Multiply world * light (Phase C)
    4. PostProcessPass - Apply bloom, vignette, etc. (Phase D)
    5. FinalPass - Blit result to screen
    """

    def __init__(
        self,
        ctx: "moderngl.Context",
        width: int,
        height: int,
    ) -> None:
        """Initialize the render graph.

        Args:
            ctx: The ModernGL rendering context.
            width: Initial viewport width.
            height: Initial viewport height.
        """
        self._ctx = ctx
        self._fbo_manager = FramebufferManager(ctx, width, height)
        self._passes: list[BaseRenderPass] = []

    @property
    def ctx(self) -> "moderngl.Context":
        """The ModernGL rendering context."""
        return self._ctx

    @property
    def fbo_manager(self) -> FramebufferManager:
        """The framebuffer manager for creating/accessing FBOs."""
        return self._fbo_manager

    @property
    def passes(self) -> list[BaseRenderPass]:
        """The ordered list of render passes."""
        return self._passes

    def add_pass(self, render_pass: BaseRenderPass) -> None:
        """Add a render pass to the end of the pipeline.

        Args:
            render_pass: The pass to add.
        """
        self._passes.append(render_pass)

    def insert_pass(self, index: int, render_pass: BaseRenderPass) -> None:
        """Insert a render pass at a specific position.

        Args:
            index: Position in the pass list.
            render_pass: The pass to insert.
        """
        self._passes.insert(index, render_pass)

    def remove_pass(self, name: str) -> Optional[BaseRenderPass]:
        """Remove a render pass by name.

        Args:
            name: The pass identifier.

        Returns:
            The removed pass, or None if not found.
        """
        for i, p in enumerate(self._passes):
            if p.name == name:
                return self._passes.pop(i)
        return None

    def get_pass(self, name: str) -> Optional[BaseRenderPass]:
        """Get a render pass by name.

        Args:
            name: The pass identifier.

        Returns:
            The pass if found, None otherwise.
        """
        for p in self._passes:
            if p.name == name:
                return p
        return None

    def execute(self) -> None:
        """Execute all enabled render passes in order.

        Each pass receives the context and this graph, allowing
        it to access framebuffers and other shared resources.
        """
        for render_pass in self._passes:
            if render_pass.enabled:
                render_pass.execute(self._ctx, self)

    def resize(self, width: int, height: int) -> None:
        """Handle viewport resize.

        Resizes all framebuffers and notifies passes.

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        self._fbo_manager.resize_all(width, height)

        for render_pass in self._passes:
            render_pass.on_resize(width, height)

    def release(self) -> None:
        """Release all GPU resources.

        Should be called during shutdown.
        """
        # Release passes first (they may reference FBOs)
        for render_pass in self._passes:
            render_pass.release()
        self._passes.clear()

        # Release framebuffers
        self._fbo_manager.release_all()
