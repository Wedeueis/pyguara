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
exactly (a fullscreen-quad program compiled once, two uniforms set per
`apply()`), since this is the same kind of effect: a cheap, whole-frame
colour operation, not a bloom/lighting feature needing the engine's
lighting pipeline this game does not run.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.framebuffer import Framebuffer

_SHADER_DIR = (
    Path(__file__).parent.parent.parent
    / "pyguara"
    / "graphics"
    / "backends"
    / "moderngl"
    / "shaders"
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
        ctx: moderngl.Context,
        *,
        health: float = 0.0,
        strength: float = 0.0,
        enabled: bool = True,
    ) -> None:
        """Build the effect's shader program.

        Args:
            ctx: The ModernGL context.
            health: Initial `health`.
            strength: Initial `strength`.
            enabled: Whether the effect is active.
        """
        super().__init__("soil_health", enabled=enabled)
        self._ctx = ctx

        self.health = health
        self.strength = strength

        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._create_resources()

    def _create_resources(self) -> None:
        """Compile the fullscreen-quad program."""
        vert_source = (_SHADER_DIR / "fullscreen_quad.vert").read_text()
        frag_source = (_SHADER_DIR / "soil_health.frag").read_text()

        self._program = self._ctx.program(
            vertex_shader=vert_source, fragment_shader=frag_source
        )
        self._vao = self._ctx.vertex_array(self._program, [])

    def apply(
        self,
        ctx: moderngl.Context,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Grade the input frame towards `health`, by `strength`.

        Args:
            ctx: The ModernGL context.
            input_fbo: Source framebuffer.
            output_fbo: Destination framebuffer.
        """
        if self._program is None or self._vao is None:
            return

        output_fbo.bind()
        input_fbo.texture.use(0)

        self._program["u_texture"] = 0
        self._program["u_health"] = self.health
        self._program["u_strength"] = self.strength

        self._vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._program is not None:
            self._program.release()
            self._program = None
