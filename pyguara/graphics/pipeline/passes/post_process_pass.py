"""Post-processing render pass - applies screen-space effects.

This pass executes the PostProcessStack on the input framebuffer,
applying effects like bloom, vignette, color grading, etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyguara.graphics.pipeline.render_pass import BaseRenderPass

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.framebuffer import Framebuffer
    from pyguara.graphics.pipeline.graph import RenderGraph
    from pyguara.graphics.vfx.post_process import PostProcessStack


class PostProcessPass(BaseRenderPass):
    """Applies post-processing effects to the scene.

    This pass:
    1. Reads from the input FBO (typically composite or world)
    2. Runs the effect stack (bloom, vignette, etc.)
    3. Writes to the output FBO (or leaves result in stack's output)
    """

    def __init__(
        self,
        post_process_stack: "PostProcessStack",
        input_fbo_name: str = "composite",
        output_fbo_name: str = "post_processed",
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the post-process pass.

        Args:
            post_process_stack: The effect stack to execute.
            input_fbo_name: Name of the input framebuffer.
            output_fbo_name: Name for the output framebuffer.
            enabled: Whether this pass should execute.
        """
        super().__init__("post_process", enabled=enabled)
        self._stack = post_process_stack
        self._input_fbo_name = input_fbo_name
        self._output_fbo_name = output_fbo_name

    @property
    def stack(self) -> "PostProcessStack":
        """Get the post-processing stack."""
        return self._stack

    @property
    def input_fbo_name(self) -> str:
        """Name of the input framebuffer."""
        return self._input_fbo_name

    @input_fbo_name.setter
    def input_fbo_name(self, value: str) -> None:
        """Set the input framebuffer name."""
        self._input_fbo_name = value

    @property
    def output_fbo_name(self) -> str:
        """Name of the output framebuffer."""
        return self._output_fbo_name

    def execute(self, ctx: "moderngl.Context", graph: "RenderGraph") -> None:
        """Execute the post-processing pass.

        Args:
            ctx: The ModernGL rendering context.
            graph: The RenderGraph providing access to framebuffers.
        """
        if not self._enabled:
            return

        # Get input framebuffer
        input_fbo = graph.fbo_manager.get(self._input_fbo_name)
        if input_fbo is None:
            return

        # Check if any effects are enabled
        enabled_effects = [e for e in self._stack.effects if e.enabled]
        if not enabled_effects:
            # No effects - copy input to output for consistency
            output_fbo = graph.fbo_manager.get_or_create(self._output_fbo_name)
            self._blit(ctx, input_fbo, output_fbo)
            return

        # Process through effect stack
        result_fbo = self._stack.process(input_fbo)

        # Copy result to named output FBO if different
        if result_fbo.name != self._output_fbo_name:
            output_fbo = graph.fbo_manager.get_or_create(self._output_fbo_name)
            self._blit(ctx, result_fbo, output_fbo)

    def _blit(
        self,
        ctx: "moderngl.Context",
        src: "Framebuffer",
        dst: "Framebuffer",
    ) -> None:
        """Copy one framebuffer to another.

        Args:
            ctx: The ModernGL context.
            src: Source framebuffer.
            dst: Destination framebuffer.
        """
        # Use ModernGL's blit functionality
        ctx.copy_framebuffer(dst.fbo, src.fbo)

    def on_resize(self, width: int, height: int) -> None:
        """Handle viewport resize.

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        self._stack.on_resize(width, height)

    def release(self) -> None:
        """Release resources."""
        self._stack.release()
