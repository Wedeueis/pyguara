"""Composite render pass - combines world and light map.

This pass multiplies the world texture by the light map to create
the final lit scene. The result is either written to another FBO
for post-processing or directly to the screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara.graphics.pipeline.buffers import COMPOSITE_FBO_NAME  # re-exported
from pyguara.graphics.pipeline.device import FullscreenShader, glsl
from pyguara.graphics.pipeline.render_pass import BaseRenderPass

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.graph import RenderGraph

COMPOSITE = FullscreenShader(
    "composite",
    inputs=("u_world", "u_lightmap"),
    glsl=glsl("composite.frag"),
    wgsl="""
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let world_color = textureSample(u_world, input_sampler, in.uv);
    let light_color = textureSample(u_lightmap, input_sampler, in.uv);
    // Light above 1.0 brightens, below darkens; the world's alpha is kept.
    return vec4<f32>(world_color.rgb * light_color.rgb, world_color.a);
}
""",
)
"""World times light map, the same in both sources."""


class CompositePass(BaseRenderPass):
    """Composites world and light map into a lit scene.

    This pass:
    1. Reads from the world FBO (rendered sprites)
    2. Reads from the light FBO (accumulated lights), or the world again
       when there is none, so an unlit scene passes through squared --
       as it always has
    3. Multiplies them together (world * light)
    4. Writes to the composite FBO (or screen if no post-processing)
    """

    def __init__(
        self,
        ctx: Any = None,
        world_fbo_name: str = "world",
        light_fbo_name: str = "lightmap",
        output_fbo_name: str | None = COMPOSITE_FBO_NAME,
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the composite pass.

        Args:
            ctx: Unused. Accepted so callers written when passes needed a
                ModernGL context keep working; removed in stage E.
            world_fbo_name: Name of the world framebuffer.
            light_fbo_name: Name of the light map framebuffer.
            output_fbo_name: Name of output FBO (None = screen).
            enabled: Whether this pass should execute.
        """
        super().__init__("composite", enabled=enabled)
        self._world_fbo_name = world_fbo_name
        self._light_fbo_name = light_fbo_name
        self._output_fbo_name = output_fbo_name

    def execute(self, ctx: moderngl.Context | None, graph: RenderGraph) -> None:
        """Execute the composite pass.

        Args:
            ctx: Unused; the pass runs through `graph.device`.
            graph: The RenderGraph providing access to framebuffers.
        """
        if not self._enabled:
            return
        manager = graph.fbo_manager
        world_fbo = manager.get(self._world_fbo_name)
        if world_fbo is None:
            return
        light_fbo = manager.get(self._light_fbo_name) or world_fbo
        output = (
            manager.get_or_create(self._output_fbo_name)
            if self._output_fbo_name is not None
            else None
        )
        graph.device.run(
            COMPOSITE, {"u_world": world_fbo, "u_lightmap": light_fbo}, {}, output
        )
