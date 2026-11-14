"""Bloom post-processing effect.

Creates a glowing halo around bright areas by:
1. Extracting bright pixels (threshold pass)
2. Blurring the bright pixels (Gaussian blur)
3. Adding the blur back to the original (composite pass)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyguara.graphics.pipeline.buffers import HDR_DTYPE
from pyguara.graphics.pipeline.device import FullscreenShader, Uniform
from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.device import GraphicsDevice
    from pyguara.graphics.pipeline.framebuffer import Framebuffer, FramebufferManager

THRESHOLD = FullscreenShader(
    "bloom_threshold",
    inputs=("u_texture",),
    uniforms=(Uniform("u_threshold"),),
    wgsl="""
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let color = textureSample(u_texture, input_sampler, in.uv);
    let luminance = dot(color.rgb, vec3<f32>(0.2126, 0.7152, 0.0722));
    if (luminance > params.u_threshold) {
        // Soft knee - gradual transition
        let knee = params.u_threshold * 0.5;
        var soft = clamp((luminance - params.u_threshold + knee) / (2.0 * knee), 0.0, 1.0);
        soft = soft * soft;
        return vec4<f32>(color.rgb * soft, 1.0);
    }
    return vec4<f32>(0.0, 0.0, 0.0, 1.0);
}
""",
)

BLUR = FullscreenShader(
    "bloom_blur",
    inputs=("u_texture",),
    uniforms=(Uniform("u_direction", "vec2"), Uniform("u_texel_size", "vec2")),
    # The kernel is symmetric, so a vertical pass blurs the same whichever
    # way up the rows run.
    wgsl="""
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    // 9-tap Gaussian weights (sigma ~= 2.0)
    var weights = array<f32, 5>(0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
    var result = textureSample(u_texture, input_sampler, in.uv).rgb * weights[0];
    let offset = params.u_direction * params.u_texel_size;
    for (var i = 1; i < 5; i++) {
        let sample_offset = offset * f32(i);
        result += textureSample(u_texture, input_sampler, in.uv + sample_offset).rgb * weights[i];
        result += textureSample(u_texture, input_sampler, in.uv - sample_offset).rgb * weights[i];
    }
    return vec4<f32>(result, 1.0);
}
""",
)

COMPOSITE = FullscreenShader(
    "bloom_composite",
    inputs=("u_scene", "u_bloom"),
    uniforms=(Uniform("u_intensity"),),
    # The tonemap is `bloom_composite.frag`'s: identity below the knee,
    # asymptotic to 1.0 above it. See that file for why.
    wgsl="""
const KNEE: f32 = 0.8;

fn tonemap(color: vec3<f32>) -> vec3<f32> {
    let excess = max(color - vec3<f32>(KNEE), vec3<f32>(0.0));
    let headroom = vec3<f32>(1.0 - KNEE);
    return min(color, vec3<f32>(KNEE)) + headroom * (excess / (excess + headroom));
}

@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let scene_color = textureSample(u_scene, input_sampler, in.uv);
    let bloom_color = textureSample(u_bloom, input_sampler, in.uv);
    let result = scene_color.rgb + bloom_color.rgb * params.u_intensity;
    return vec4<f32>(tonemap(result), scene_color.a);
}
""",
)


class BloomEffect(PostProcessEffect):
    """Bloom effect for glowing bright areas.

    Parameters:
        threshold: Brightness level above which pixels glow (default: 0.8).
        intensity: Strength of the glow (default: 1.0).
        blur_passes: Number of blur iterations (default: 2).
    """

    def __init__(
        self,
        fbo_manager: FramebufferManager,
        *,
        threshold: float = 0.8,
        intensity: float = 1.0,
        blur_passes: int = 2,
        enabled: bool = True,
    ) -> None:
        """Initialize the bloom effect.

        Args:
            fbo_manager: Manager for creating temp framebuffers.
            threshold: Brightness threshold (0.0-1.0).
            intensity: Bloom intensity multiplier.
            blur_passes: Number of blur iterations.
            enabled: Whether the effect is active.
        """
        super().__init__("bloom", enabled=enabled)
        self._fbo_manager = fbo_manager
        self.threshold = threshold
        self.intensity = intensity
        self.blur_passes = blur_passes

        # Internal FBO names
        self._bright_fbo_name = "_bloom_bright"
        self._blur_fbo_name = "_bloom_blur"

        # Bloom's scratch buffers are part of the HDR chain: they carry the
        # bright pass's output, which is where values above 1.0 would live.
        fbo_manager.declare(self._bright_fbo_name, dtype=HDR_DTYPE)
        fbo_manager.declare(self._blur_fbo_name, dtype=HDR_DTYPE)

    def apply(
        self,
        device: GraphicsDevice,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Apply the bloom effect.

        Args:
            device: What to run the shaders on.
            input_fbo: Source framebuffer.
            output_fbo: Destination framebuffer.
        """
        bright_fbo = self._fbo_manager.get_or_create(self._bright_fbo_name)
        blur_fbo = self._fbo_manager.get_or_create(self._blur_fbo_name)
        texel_size = (1.0 / input_fbo.width, 1.0 / input_fbo.height)

        # Pass 1: Extract bright pixels
        device.run(
            THRESHOLD,
            {"u_texture": input_fbo},
            {"u_threshold": self.threshold},
            bright_fbo,
        )

        # Pass 2: Blur bright pixels (ping-pong horizontal/vertical)
        for _ in range(self.blur_passes):
            device.run(
                BLUR,
                {"u_texture": bright_fbo},
                {"u_direction": (1.0, 0.0), "u_texel_size": texel_size},
                blur_fbo,
            )
            device.run(
                BLUR,
                {"u_texture": blur_fbo},
                {"u_direction": (0.0, 1.0), "u_texel_size": texel_size},
                bright_fbo,
            )

        # Pass 3: Composite bloom with original
        device.run(
            COMPOSITE,
            {"u_scene": input_fbo, "u_bloom": bright_fbo},
            {"u_intensity": self.intensity},
            output_fbo,
        )
