"""Mourisco: Ressonância - the expanding-wavefront render pass.

The engine's `LightPass` draws filled radial discs. An echolocation pulse
is a *ring* travelling outward, which no existing shader produces -- so
this pass forks LightPass's quad/instance plumbing (unchanged, right down
to the 8-float instance layout) and swaps in `pulse_ring.vert/frag`, which
measure distance from the quad's rim instead of its centre.

It draws into the same `lightmap` FBO the lights accumulate into, with the
same additive blend, so a pulse genuinely *lights* the cave during
compositing rather than being painted over the top of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import moderngl
import numpy as np

from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.passes.light_pass import LIGHT_FBO_NAME
from pyguara.graphics.pipeline.render_pass import BaseRenderPass
from pyguara.graphics.pipeline.viewport import Viewport

_SHADER_DIR = (
    Path(__file__).resolve().parents[2]
    / "pyguara"
    / "graphics"
    / "backends"
    / "moderngl"
    / "shaders"
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
    INSTANCE_STRIDE = INSTANCE_FLOATS * 4
    INITIAL_CAPACITY = 32

    def __init__(self, ctx: moderngl.Context, *, enabled: bool = True) -> None:
        """Build the ring program, quad and instance buffer."""
        super().__init__("pulse", enabled=enabled)
        self._ctx = ctx
        self._rings: list[PulseRing] = []
        self._camera: Camera2D | None = None
        self._viewport: Viewport | None = None
        self._instance_capacity = self.INITIAL_CAPACITY

        self._program = ctx.program(
            vertex_shader=(_SHADER_DIR / "pulse_ring.vert").read_text(),
            fragment_shader=(_SHADER_DIR / "pulse_ring.frag").read_text(),
        )

        vertices = np.array(
            [
                -0.5,
                -0.5,
                0.0,
                0.0,
                0.5,
                -0.5,
                1.0,
                0.0,
                -0.5,
                0.5,
                0.0,
                1.0,
                0.5,
                0.5,
                1.0,
                1.0,
            ],
            dtype="f4",
        )
        self._quad_vbo = ctx.buffer(vertices.tobytes())
        self._instance_vbo = ctx.buffer(
            reserve=self._instance_capacity * self.INSTANCE_STRIDE
        )
        self._vao = ctx.vertex_array(
            self._program,
            [
                # The quad buffer still carries per-vertex UVs (shared
                # layout with the light pass's quad), but this shader
                # derives its coordinate from in_vert, so they are skipped
                # rather than bound -- an unused attribute is optimised
                # out and cannot be bound by name.
                (self._quad_vbo, "2f 2x4", "in_vert"),
                (
                    self._instance_vbo,
                    "2f 1f 3f 1f 1f/i",
                    "in_pos",
                    "in_radius",
                    "in_color",
                    "in_intensity",
                    "in_thickness",
                ),
            ],
        )

    def set_rings(self, rings: list[PulseRing]) -> None:
        """Set the wavefronts to draw on the next execute."""
        self._rings = rings

    def set_camera(self, camera: Camera2D, viewport: Viewport | None = None) -> None:
        """Set the camera used for this frame's world-to-screen transform."""
        self._camera = camera
        self._viewport = viewport

    def execute(self, ctx: moderngl.Context, graph: RenderGraph) -> None:
        """Add every active ring into the light map, additively."""
        if not self._enabled or not self._rings or self._camera is None:
            return

        light_fbo = graph.fbo_manager.get_or_create(LIGHT_FBO_NAME)
        viewport = self._viewport or Viewport(0, 0, light_fbo.width, light_fbo.height)
        # Bound, but deliberately not cleared: LightPass already cleared
        # this FBO to ambient and drew the scene's lights into it, and the
        # rings belong on top of that.
        light_fbo.bind()

        zoom = self._camera.zoom

        if len(self._rings) > self._instance_capacity:
            self._grow(len(self._rings))

        data = np.zeros((len(self._rings), self.INSTANCE_FLOATS), dtype="f4")
        for i, ring in enumerate(self._rings):
            # `world_to_screen` is the engine's single world->screen
            # definition, and `screen_offset` already has the camera
            # position subtracted out -- doing it again here shifted every
            # ring by a full camera position.
            screen = self._camera.world_to_screen(ring.position, viewport)
            data[i] = [
                screen.x,
                screen.y,
                ring.radius * zoom,
                ring.color[0],
                ring.color[1],
                ring.color[2],
                ring.intensity,
                ring.thickness,
            ]
        self._instance_vbo.write(data.tobytes())

        projection = np.array(
            [
                [2.0 / viewport.width, 0.0, 0.0, 0.0],
                [0.0, -2.0 / viewport.height, 0.0, 0.0],
                [0.0, 0.0, -1.0, 0.0],
                [-1.0, 1.0, 0.0, 1.0],
            ],
            dtype="f4",
        )
        self._program["u_projection"].write(projection.tobytes())

        ctx.enable(ctx.BLEND)
        ctx.blend_func = ctx.ONE, ctx.ONE
        self._vao.render(mode=ctx.TRIANGLE_STRIP, instances=len(self._rings))
        ctx.blend_func = ctx.SRC_ALPHA, ctx.ONE_MINUS_SRC_ALPHA

        self._camera = None
        self._viewport = None

    def _grow(self, needed: int) -> None:
        while self._instance_capacity < needed:
            self._instance_capacity *= 2
        self._instance_vbo.orphan(self._instance_capacity * self.INSTANCE_STRIDE)

    def release(self) -> None:
        """Release GPU resources."""
        for resource in (self._vao, self._instance_vbo, self._quad_vbo, self._program):
            if resource is not None:
                resource.release()
