"""Mourisco: Ressonância - the expanding-wavefront render pass.

The engine's `LightPass` draws filled radial discs. An echolocation pulse
is a *ring* travelling outward, which no existing shader produces -- so
this pass is LightPass's shape -- an `InstancedShader`, a quad per ring --
with `pulse_ring.vert/frag` (and their WGSL port), which measure distance
from the quad's rim instead of its centre.

It draws into the same `lightmap` FBO the lights accumulate into, with the
same additive blend, so a pulse genuinely *lights* the cave during
compositing rather than being painted over the top of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.device import Attribute, InstancedShader, Uniform
from pyguara.graphics.pipeline.passes.light_pass import LIGHT_FBO_NAME, projection
from pyguara.graphics.pipeline.render_pass import BaseRenderPass
from pyguara.graphics.pipeline.viewport import Viewport

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.graph import RenderGraph

PULSE_RINGS = InstancedShader(
    "pulse_rings",
    attributes=(
        Attribute("pos", "vec2"),
        Attribute("radius"),
        Attribute("color", "vec3"),
        Attribute("intensity"),
        Attribute("thickness"),
    ),
    uniforms=(Uniform("u_projection", "mat4"),),
    # A port of pulse_ring.vert/frag. Radially symmetric, so the two uv
    # conventions agree; the projection is the light pass's.
    wgsl="""
struct Varying {
    @builtin(position) position: vec4<f32>,
    @location(0) local: vec2<f32>,
    @location(1) color: vec3<f32>,
    @location(2) intensity: f32,
    @location(3) thickness: f32,
};

@vertex
fn vertex(@builtin(vertex_index) index: u32, ring: Instance) -> Varying {
    let corner = quad_corner(index);
    let scaled = corner * ring.radius * 2.0;
    var out: Varying;
    out.position = params.u_projection * vec4<f32>(scaled + ring.pos, 0.0, 1.0);
    out.local = corner * 2.0;
    out.color = ring.color;
    out.intensity = ring.intensity;
    out.thickness = ring.thickness;
    return out;
}

@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let dist = length(in.local);
    if (dist > 1.0) {
        discard;
    }
    let band = abs(1.0 - dist);
    let falloff = 1.0 - smoothstep(0.0, max(in.thickness, 0.001), band);
    let wake = (1.0 - smoothstep(0.0, 1.0, dist)) * 0.18;
    let strength = (falloff + wake) * in.intensity;
    if (strength <= 0.001) {
        discard;
    }
    return vec4<f32>(in.color * strength, strength);
}
""",
)


@dataclass(slots=True)
class PulseRing:
    """One wavefront to draw this frame, already in world space."""

    position: Vector2
    radius: float
    color: tuple[float, float, float]
    intensity: float
    thickness: float = 0.06


class PulsePass(BaseRenderPass):
    """Adds expanding wavefront rings into the light map."""

    INSTANCE_FLOATS = 8

    def __init__(self, *, enabled: bool = True) -> None:
        """Start with no rings.

        Args:
            enabled: Whether this pass should execute.
        """
        super().__init__("pulse", enabled=enabled)
        self._rings: list[PulseRing] = []
        self._camera: Camera2D | None = None
        self._viewport: Viewport | None = None

    def set_rings(self, rings: list[PulseRing]) -> None:
        """Set the wavefronts to draw on the next execute."""
        self._rings = rings

    def set_camera(self, camera: Camera2D, viewport: Viewport | None = None) -> None:
        """Set the camera used for this frame's world-to-screen transform."""
        self._camera = camera
        self._viewport = viewport

    def execute(self, graph: RenderGraph) -> None:
        """Add every active ring into the light map, additively."""
        if not self._enabled or not self._rings or self._camera is None:
            return

        light_fbo = graph.fbo_manager.get_or_create(LIGHT_FBO_NAME)
        viewport = self._viewport or Viewport(0, 0, light_fbo.width, light_fbo.height)
        zoom = self._camera.zoom

        rows = np.zeros((len(self._rings), self.INSTANCE_FLOATS), dtype="<f4")
        for i, ring in enumerate(self._rings):
            # `world_to_screen` is the engine's single world->screen
            # definition, and `screen_offset` already has the camera
            # position subtracted out -- doing it again here shifted every
            # ring by a full camera position.
            screen = self._camera.world_to_screen(ring.position, viewport)
            rows[i] = [
                screen.x,
                screen.y,
                ring.radius * zoom,
                ring.color[0],
                ring.color[1],
                ring.color[2],
                ring.intensity,
                ring.thickness,
            ]

        # Not cleared: LightPass already cleared this buffer to ambient and
        # drew the scene's lights into it, and the rings belong on top.
        graph.device.draw_instanced(
            PULSE_RINGS,
            rows.tobytes(),
            len(self._rings),
            {"u_projection": projection(viewport.width, viewport.height)},
            light_fbo,
            blend="add",
        )
        self._camera = None
        self._viewport = None
