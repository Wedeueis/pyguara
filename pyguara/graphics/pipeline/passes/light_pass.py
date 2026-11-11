"""Light render pass - renders dynamic lights to a light map.

This pass collects all lights in the scene and renders them to
a light framebuffer using additive blending. The result is then
composited with the world in the composite pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.buffers import LIGHT_FBO_NAME  # re-exported
from pyguara.graphics.pipeline.device import Attribute, InstancedShader, Uniform, glsl
from pyguara.graphics.pipeline.render_pass import BaseRenderPass
from pyguara.graphics.pipeline.viewport import Viewport

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.lighting.light_system import LightingSystem
    from pyguara.graphics.pipeline.graph import RenderGraph

LIGHTS = InstancedShader(
    "lights",
    # pos(2) + radius(1) + color(3) + intensity(1) + falloff(1) + kind(1)
    # + spot_dir(1) + spot_cos_half(1) = 11 floats a light.
    attributes=(
        Attribute("pos", "vec2"),
        Attribute("radius"),
        Attribute("color", "vec3"),
        Attribute("intensity"),
        Attribute("falloff"),
        Attribute("kind"),
        Attribute("spot_dir"),
        Attribute("spot_cos_half"),
    ),
    uniforms=(Uniform("u_projection", "mat4"),),
    glsl_vertex=glsl("light.vert"),
    glsl_fragment=glsl("light.frag"),
    # A line-for-line port of light.vert and light.frag. The projection is
    # the same matrix, so a light lands on the same pixels; and the quad's
    # uv runs as in_uv does -- (0, 0) at the corner nearest the screen's
    # top left -- so the spot cone's clockwise-from-+x convention holds.
    wgsl="""
struct Varying {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) color: vec3<f32>,
    @location(2) intensity: f32,
    @location(3) falloff: f32,
    // Flat: the type is a discriminant, not a quantity.
    @location(4) @interpolate(flat) kind: f32,
    @location(5) spot_dir: f32,
    @location(6) spot_cos_half: f32,
};

@vertex
fn vertex(@builtin(vertex_index) index: u32, light: Instance) -> Varying {
    let corner = quad_corner(index);
    let scaled = corner * light.radius * 2.0;
    var out: Varying;
    out.position = params.u_projection * vec4<f32>(scaled + light.pos, 0.0, 1.0);
    out.uv = corner + vec2<f32>(0.5, 0.5);
    out.color = light.color;
    out.intensity = light.intensity;
    out.falloff = light.falloff;
    out.kind = light.kind;
    out.spot_dir = light.spot_dir;
    out.spot_cos_half = light.spot_cos_half;
    return out;
}

const TYPE_DIRECTIONAL: f32 = 2.0;
const TYPE_SPOT: f32 = 3.0;

@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let offset = in.uv - vec2<f32>(0.5, 0.5);
    let dist = length(offset) * 2.0;
    var attenuation = 1.0 - pow(clamp(dist, 0.0, 1.0), in.falloff);
    attenuation = max(attenuation, 0.0);
    attenuation = smoothstep(0.0, 1.0, attenuation);
    if (in.kind == TYPE_DIRECTIONAL) {
        attenuation = 1.0;
    } else if (in.kind == TYPE_SPOT) {
        let axis = vec2<f32>(cos(in.spot_dir), sin(in.spot_dir));
        var aligned = 1.0;
        if (dist > 0.0001) {
            aligned = dot(normalize(offset), axis);
        }
        let edge = (1.0 - in.spot_cos_half) * 0.15 + 0.0001;
        attenuation *= smoothstep(in.spot_cos_half - edge, in.spot_cos_half + edge, aligned);
    }
    return vec4<f32>(in.color * (attenuation * in.intensity), 1.0);
}
""",
)
"""A quad per light: radial falloff, an even directional fill, or a cone."""


def projection(width: int, height: int) -> tuple[float, ...]:
    """Return the orthographic projection from screen pixels, y down, to clip space.

    Column by column, as GL and WGSL both store a matrix. The sprite
    renderer's, so a light lands where a sprite at the same point does.
    """
    return (
        2.0 / width, 0.0, 0.0, 0.0,
        0.0, 2.0 / -height, 0.0, 0.0,
        0.0, 0.0, -1.0, 0.0,
        -1.0, 1.0, 0.0, 1.0,
    )  # fmt: skip


class LightPass(BaseRenderPass):
    """Renders dynamic lights to a light map framebuffer.

    This pass:
    1. Clears the light FBO to ambient color
    2. Renders each light as a radial gradient quad
    3. Uses additive blending so overlapping lights combine

    `games/mourisco_ressonancia/pulse_pass.py` copies the shape of this
    pass but is not bound to it: it draws its own rings into the same
    light map, additively.
    """

    INSTANCE_FLOATS = 11

    def __init__(
        self,
        ctx: Any,
        lighting_system: LightingSystem,
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the light pass.

        Args:
            ctx: Unused. Accepted so callers written when passes needed a
                ModernGL context keep working; removed in stage E.
            lighting_system: The system that provides light data.
            enabled: Whether this pass should execute.
        """
        super().__init__("light", enabled=enabled)
        self._lighting_system = lighting_system
        # Current frame's camera (set before execute)
        self._camera: Camera2D | None = None
        self._viewport: Viewport | None = None

    def set_camera(self, camera: Camera2D, viewport: Viewport | None = None) -> None:
        """Set the camera and viewport for this frame.

        Args:
            camera: The active camera.
            viewport: Optional viewport.
        """
        self._camera = camera
        self._viewport = viewport

    def execute(self, ctx: moderngl.Context | None, graph: RenderGraph) -> None:
        """Execute the light pass.

        Args:
            ctx: Unused; the pass runs through `graph.device`.
            graph: The RenderGraph providing access to framebuffers.
        """
        if not self._enabled:
            return
        device = graph.device
        light_fbo = graph.fbo_manager.get_or_create(LIGHT_FBO_NAME)
        viewport = self._viewport or Viewport(0, 0, light_fbo.width, light_fbo.height)

        # Ambient in floats: the light map is HDR, and ambient may exceed 1.
        ambient = self._lighting_system.get_ambient_normalized()
        device.clear(light_fbo, (ambient[0], ambient[1], ambient[2], 1.0))
        light_fbo.bind()

        if self._camera is None:
            return
        # World-to-screen offset -- the same definition the batcher and the
        # particle system use, so lit geometry lines up with drawn geometry.
        lights = self._lighting_system.collect_lights_screen_space(
            self._camera.zoom, self._camera.screen_offset(viewport)
        )
        if lights:
            rows = np.array(
                [
                    (
                        light.position.x,
                        light.position.y,
                        light.radius,
                        light.color[0],
                        light.color[1],
                        light.color[2],
                        light.intensity,
                        light.falloff,
                        light.light_type,
                        light.spot_direction,
                        light.spot_cos_half_angle,
                    )
                    for light in lights
                ],
                dtype="<f4",
            )
            # Overlapping lights accumulate rather than occlude.
            device.draw_instanced(
                LIGHTS,
                rows.tobytes(),
                len(lights),
                {"u_projection": projection(viewport.width, viewport.height)},
                light_fbo,
                blend="add",
            )

        # Clear camera for next frame
        self._camera = None
        self._viewport = None
