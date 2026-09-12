"""Rising heat and drifting dust as a screen-space post-process effect.

Hot air drawn over the finished frame rather than as entities: the
shimmer is a refraction in the fragment shader, so a blazing afternoon
costs exactly what a mild one costs and neither one puts anything through
the ECS, the render queue, or the batcher.

The split of responsibility is the same one `StormEffect` draws. This
effect owns how the heat *looks*; the game owns how hot it is. Nothing
here decides that a firefight has kicked up dust -- the caller drives
`haze`, `dust` and `wind`, which is what lets an explosion raise a gust
on the same frame it goes off.

Typical use, per frame::

    haze.haze = 5.0          # a steady shimmer, in pixels of offset
    haze.dust = 0.4
    haze.update(dt)          # advances the shader clock
    # ... and when something explodes nearby:
    haze.gust(0.6)           # a dust kick that decays on its own
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.framebuffer import Framebuffer


# Shader directory
_SHADER_DIR = Path(__file__).parent.parent.parent / "backends" / "moderngl" / "shaders"

# Sunlit grit and the warm scatter of hot air. Both are overridable; these
# are what read as afternoon over a red-earth scene.
DEFAULT_DUST_COLOR = (0.78, 0.62, 0.42)
DEFAULT_SUN_COLOR = (0.95, 0.65, 0.32)

# How fast a gust decays back to the standing dust level, per second.
GUST_DECAY = 1.6


class HeatHazeEffect(PostProcessEffect):
    """Refracting heat shimmer with dust motes drifting through it.

    Attributes:
        haze: Refraction strength in pixels of maximum offset. Around 2-4
            is a warm day; past about 12 the frame stops being readable,
            which is occasionally the point.
        haze_scale: Spatial frequency of the shimmer. Low values churn in
            broad sheets, high values boil.
        haze_speed: How fast the shimmer rises.
        horizon: Where the ground heat begins, 0.0 (top of frame) to 1.0
            (bottom). Below it the shimmer ramps to full strength; above
            it a fraction remains, because air does not stop moving.
        dust: Mote density, 0.0 (clear) to 1.0 (duststorm). `gust()` adds
            to this temporarily without disturbing the standing level.
        dust_color: Linear RGB the motes add to the frame.
        wind: Lateral drift. Positive blows the dust right, negative left.
        sun: How brightly churning air glows. A warm scatter, not a light.
        sun_color: Linear RGB of that glow.
    """

    def __init__(
        self,
        ctx: moderngl.Context,
        *,
        haze: float = 3.0,
        haze_scale: float = 6.0,
        haze_speed: float = 0.22,
        horizon: float = 0.0,
        dust: float = 0.0,
        dust_color: tuple[float, float, float] = DEFAULT_DUST_COLOR,
        wind: float = 1.0,
        sun: float = 0.0,
        sun_color: tuple[float, float, float] = DEFAULT_SUN_COLOR,
        enabled: bool = True,
    ) -> None:
        """Build the heat haze's shader program.

        Args:
            ctx: The ModernGL context.
            haze: Initial refraction strength, in pixels.
            haze_scale: Initial shimmer frequency.
            haze_speed: Initial rise rate.
            horizon: Where ground heat begins, 0.0 to 1.0 down the frame.
            dust: Initial standing mote density.
            dust_color: Linear RGB of the motes.
            wind: Initial lateral drift.
            sun: Initial warm-scatter strength.
            sun_color: Linear RGB of the warm scatter.
            enabled: Whether the effect is active.
        """
        super().__init__("heat_haze", enabled=enabled)
        self._ctx = ctx

        self.haze = haze
        self.haze_scale = haze_scale
        self.haze_speed = haze_speed
        self.horizon = horizon
        self.dust = dust
        self.dust_color = dust_color
        self.wind = wind
        self.sun = sun
        self.sun_color = sun_color

        self._time = 0.0
        self._gust = 0.0

        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._create_resources()

    def _create_resources(self) -> None:
        """Compile the fullscreen-quad program."""
        vert_source = (_SHADER_DIR / "fullscreen_quad.vert").read_text()
        frag_source = (_SHADER_DIR / "heat_haze.frag").read_text()

        self._program = self._ctx.program(
            vertex_shader=vert_source, fragment_shader=frag_source
        )
        self._vao = self._ctx.vertex_array(self._program, [])

    @property
    def time(self) -> float:
        """Seconds of heat elapsed -- the shader's animation clock."""
        return self._time

    @property
    def gust_level(self) -> float:
        """The decaying dust a `gust()` added, over the standing `dust`."""
        return self._gust

    def update(self, dt: float) -> None:
        """Advance the shimmer's clock and decay any gust.

        `haze`, `dust` and `wind` are the caller's to drive; only the
        gust decays on its own, because a kicked-up cloud settling is a
        property of the dust rather than a beat in the game.

        Args:
            dt: Seconds since the last frame.
        """
        self._time += dt
        if self._gust > 0.0:
            self._gust = max(0.0, self._gust - GUST_DECAY * dt)

    def gust(self, amount: float = 0.5) -> None:
        """Kick up a cloud of dust that settles on its own.

        Adds to whatever a previous gust has not yet shed, so a firefight
        raises more dust than a single shot -- clamped, so a long one
        does not white the frame out.

        Args:
            amount: Dust to add, on the same 0.0-1.0 scale as `dust`.
        """
        self._gust = min(1.0, self._gust + amount)

    def apply(
        self,
        ctx: moderngl.Context,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Refract the input frame and lay dust over it.

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
        self._program["u_resolution"] = (
            float(input_fbo.width),
            float(input_fbo.height),
        )
        self._program["u_time"] = self._time
        self._program["u_haze"] = self.haze
        self._program["u_haze_scale"] = self.haze_scale
        self._program["u_haze_speed"] = self.haze_speed
        self._program["u_horizon"] = self.horizon
        self._program["u_dust"] = min(1.0, self.dust + self._gust)
        self._program["u_dust_color"] = self.dust_color
        self._program["u_wind"] = self.wind
        self._program["u_sun"] = self.sun
        self._program["u_sun_color"] = self.sun_color

        self._vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._program is not None:
            self._program.release()
            self._program = None
