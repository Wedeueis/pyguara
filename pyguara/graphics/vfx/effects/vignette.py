"""Vignette post-processing effect.

Darkens the edges of the screen, drawing focus to the center
and creating a cinematic look.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyguara.graphics.pipeline.device import FullscreenShader, Uniform
from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.device import GraphicsDevice
    from pyguara.graphics.pipeline.framebuffer import Framebuffer

VIGNETTE = FullscreenShader(
    "vignette",
    inputs=("u_texture",),
    uniforms=(Uniform("u_intensity"), Uniform("u_radius"), Uniform("u_softness")),
    # Symmetric about the centre, so the two uv conventions agree.
    wgsl="""
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let color = textureSample(u_texture, input_sampler, in.uv);
    let dist = distance(in.uv, vec2<f32>(0.5, 0.5));
    let vignette = smoothstep(params.u_radius, params.u_radius - params.u_softness, dist);
    let result = color.rgb * mix(1.0 - params.u_intensity, 1.0, vignette);
    return vec4<f32>(result, color.a);
}
""",
)


class VignetteEffect(PostProcessEffect):
    """Vignette effect for darkening screen edges.

    Parameters:
        intensity: How dark the edges get (0.0-1.0, default: 0.5).
        radius: Where the vignette starts from center (default: 0.75).
        softness: Edge softness/feathering (default: 0.45).
    """

    def __init__(
        self,
        *,
        intensity: float = 0.5,
        radius: float = 0.75,
        softness: float = 0.45,
        enabled: bool = True,
    ) -> None:
        """Initialize the vignette effect.

        Args:
            intensity: Edge darkness (0.0-1.0).
            radius: Where vignette starts (0.0-1.0 from center).
            softness: Edge transition softness.
            enabled: Whether the effect is active.
        """
        super().__init__("vignette", enabled=enabled)
        self.intensity = intensity
        self.radius = radius
        self.softness = softness

    def apply(
        self,
        device: GraphicsDevice,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Apply the vignette effect.

        Args:
            device: What to run the shader on.
            input_fbo: Source framebuffer.
            output_fbo: Destination framebuffer.
        """
        device.run(
            VIGNETTE,
            {"u_texture": input_fbo},
            {
                "u_intensity": self.intensity,
                "u_radius": self.radius,
                "u_softness": self.softness,
            },
            output_fbo,
        )
