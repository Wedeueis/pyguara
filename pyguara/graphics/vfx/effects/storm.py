"""Rain and lightning as a screen-space post-process effect.

Weather drawn over the finished frame rather than as entities: the rain is
procedural in the fragment shader, so a downpour costs exactly what a
drizzle costs and neither one puts anything through the ECS, the render
queue, or the batcher.

The split of responsibility matters. This effect owns how the weather
*looks*; the game owns what the weather is *doing*. A strike is not
scheduled here -- the caller drives `flash`, `bolt` and friends, which is
what lets one strike brighten the light map, shake the camera, and fire a
thunderclap on the same frame it appears.

Typical use, per frame::

    storm.rain = 0.3          # a steady drizzle
    storm.update(dt)          # advances the shader clock
    # ... and when a strike lands:
    storm.strike(x=0.4)       # a new bolt shape at 40% across the frame
    storm.flash = envelope    # driven by the caller's own fade
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyguara.common.random import RandomStream
from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.framebuffer import Framebuffer


# Shader directory
_SHADER_DIR = Path(__file__).parent.parent.parent / "backends" / "moderngl" / "shaders"

# Cool, slightly blue daylight-through-cloud, and a colder white for the
# discharge itself. Both are overridable; these are what read as weather
# over a warm scene.
DEFAULT_RAIN_COLOR = (0.55, 0.72, 0.95)
DEFAULT_FLASH_COLOR = (0.78, 0.86, 1.0)


class StormEffect(PostProcessEffect):
    """Procedural rain streaks, sheet lightning, and forked bolts.

    Attributes:
        rain: Downpour amount, 0.0 (dry) to 1.0 (heavy). Scales both how
            many drops fall and how brightly they read.
        rain_speed: Multiplier on fall rate. 1.0 is a steady vertical
            rain; raise it with `wind` for a squall.
        wind: Streak slant. Positive leans the rain right, negative left.
            Roughly -0.5..0.5 stays believable.
        rain_color: Linear RGB the streaks add to the frame.
        flash: Sheet lightning, 0.0 to 1.0 -- a wash that lifts the whole
            frame. Drive this from an envelope; holding it high looks like
            a fade to white, not like lightning.
        flash_color: Linear RGB of both the sheet wash and the bolt.
        bolt: The bolt's own brightness, 0.0 to 1.0. Usually held for a
            few frames per strike, much shorter than `flash`.
        bolt_x: Where the bolt falls, 0.0 (left edge) to 1.0 (right).
    """

    def __init__(
        self,
        ctx: moderngl.Context,
        *,
        rain: float = 0.0,
        rain_speed: float = 1.0,
        wind: float = 0.12,
        rain_color: tuple[float, float, float] = DEFAULT_RAIN_COLOR,
        flash_color: tuple[float, float, float] = DEFAULT_FLASH_COLOR,
        rng: RandomStream | None = None,
        enabled: bool = True,
    ) -> None:
        """Build the storm's shader program.

        Args:
            ctx: The ModernGL context.
            rain: Initial downpour amount.
            rain_speed: Initial fall-rate multiplier.
            wind: Initial streak slant.
            rain_color: Linear RGB of the rain streaks.
            flash_color: Linear RGB of the lightning.
            rng: Random stream picking each bolt's shape. Defaults to a
                fresh, unseeded stream; pass a seeded one for a
                reproducible sequence of strikes.
            enabled: Whether the effect is active.
        """
        super().__init__("storm", enabled=enabled)
        self._ctx = ctx
        self._rng = rng if rng is not None else RandomStream()

        self.rain = rain
        self.rain_speed = rain_speed
        self.wind = wind
        self.rain_color = rain_color
        self.flash_color = flash_color

        self.flash = 0.0
        self.bolt = 0.0
        self.bolt_x = 0.5

        self._time = 0.0
        self._bolt_seed = 0.0
        self._resolution = (1.0, 1.0)

        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._create_resources()

    def _create_resources(self) -> None:
        """Compile the fullscreen-quad program."""
        vert_source = (_SHADER_DIR / "fullscreen_quad.vert").read_text()
        frag_source = (_SHADER_DIR / "storm.frag").read_text()

        self._program = self._ctx.program(
            vertex_shader=vert_source, fragment_shader=frag_source
        )
        self._vao = self._ctx.vertex_array(self._program, [])

    @property
    def time(self) -> float:
        """Seconds of weather elapsed -- the shader's animation clock."""
        return self._time

    def update(self, dt: float) -> None:
        """Advance the rain's animation clock.

        Nothing else moves on its own: `flash`, `bolt` and `rain` are the
        caller's to drive, deliberately, so a strike can be one beat in a
        sequence the game is already running.

        Args:
            dt: Seconds since the last frame.
        """
        self._time += dt

    def strike(self, x: float | None = None) -> None:
        """Reshape the bolt, as a new strike rather than the same one again.

        Does not set `bolt` or `flash`: brightness is an envelope, and the
        caller owns it. Call this once when a strike begins.

        Args:
            x: Where the bolt falls, 0.0 (left) to 1.0 (right). Random by
                default, biased away from the very edges where a bolt is
                mostly off-frame.
        """
        self.bolt_x = self._rng.uniform(0.12, 0.88) if x is None else x
        # Any new value is a new shape; the shader only ever uses it as a
        # phase, so the range just has to be wide enough to decorrelate.
        self._bolt_seed = self._rng.uniform(0.0, 100.0)

    def apply(
        self,
        ctx: moderngl.Context,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Draw the weather over the input frame.

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
        self._program["u_rain"] = self.rain
        self._program["u_rain_speed"] = self.rain_speed
        self._program["u_wind"] = self.wind
        self._program["u_rain_color"] = self.rain_color
        self._program["u_flash"] = self.flash
        self._program["u_flash_color"] = self.flash_color
        self._program["u_bolt"] = self.bolt
        self._program["u_bolt_x"] = self.bolt_x
        self._program["u_bolt_seed"] = self._bolt_seed

        self._vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._program is not None:
            self._program.release()
            self._program = None
