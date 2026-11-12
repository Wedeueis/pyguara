"""The soil-health colour grade: a whole-scene mood, driven by real data.

The fun-improvement roadmap's own ask was "the soil composition should
affect the visual" -- this is that, honestly scoped. There is no per-tile
data on the GPU (the world pass draws the same plain rects/circles
`art.py` always has, just through `IRenderer` now instead of `UIRenderer`
-- see `bootstrap.py` and `garden_widget.py`), so a true per-tile shader
would need an instanced draw path and per-instance soil attributes this
demo does not have. What this effect gives instead is a screen-wide grade
towards warm green or dusty red-brown, driven by `scoring.soil_health` --
the exact same number the evaluation screen already scores the plot on,
so the shader's mood and the score screen's grade never disagree.

Follows `pyguara.graphics.vfx.effects.vignette.VignetteEffect`'s shape
exactly (one `FullscreenShader`, in GLSL and WGSL, two uniforms set per
`apply()`), since this is the same kind of effect: a cheap, whole-frame
colour operation, not a bloom/lighting feature needing the engine's
lighting pipeline this game does not run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyguara.graphics.pipeline.device import FullscreenShader, Uniform
from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.device import GraphicsDevice
    from pyguara.graphics.pipeline.framebuffer import Framebuffer

SOIL_HEALTH = FullscreenShader(
    "soil_health",
    inputs=("u_texture",),
    uniforms=(Uniform("u_health"), Uniform("u_strength")),
    wgsl="""
const SICK_TINT = vec3<f32>(0.95, 0.62, 0.45);      // dusty, chemical red-brown
const THRIVING_TINT = vec3<f32>(0.65, 1.05, 0.72);  // warm, saturated green

@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let color = textureSample(u_texture, input_sampler, in.uv);
    let tint = mix(SICK_TINT, THRIVING_TINT, clamp(params.u_health, 0.0, 1.0));
    let graded = color.rgb * tint;
    let result = mix(color.rgb, graded, clamp(params.u_strength, 0.0, 1.0));
    return vec4<f32>(result, color.a);
}
""",
)


class SoilHealthEffect(PostProcessEffect):
    """Tints the frame towards the plot's `scoring.soil_health`.

    Attributes:
        health: 0.0 (degraded/dry) to 1.0 (rich/organic) -- set this from
            `scoring.soil_health(grid)` every frame the grade should track
            the plot live, e.g. `GardenScene.update()`.
        strength: Overall blend amount, 0.0 to 1.0. 0.0 is a genuine no-op
            (the shader still runs but leaves the frame untouched) -- the
            caller's way to fade the grade in only once there is soil
            worth grading, rather than tinting a still-untilled plot.
    """

    def __init__(
        self,
        *,
        health: float = 0.0,
        strength: float = 0.0,
        enabled: bool = True,
    ) -> None:
        """Set the grade's starting values.

        Args:
            health: Initial `health`.
            strength: Initial `strength`.
            enabled: Whether the effect is active.
        """
        super().__init__("soil_health", enabled=enabled)
        self.health = health
        self.strength = strength

    def apply(
        self,
        device: GraphicsDevice,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Grade the input frame towards `health`, by `strength`.

        Args:
            device: What to run the shader on.
            input_fbo: Source framebuffer.
            output_fbo: Destination framebuffer.
        """
        device.run(
            SOIL_HEALTH,
            {"u_texture": input_fbo},
            {"u_health": self.health, "u_strength": self.strength},
            output_fbo,
        )
