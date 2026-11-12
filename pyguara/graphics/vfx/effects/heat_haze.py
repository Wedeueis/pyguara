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

from typing import TYPE_CHECKING

from pyguara.graphics.pipeline.device import FullscreenShader, Uniform
from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.device import GraphicsDevice
    from pyguara.graphics.pipeline.framebuffer import Framebuffer

# Sunlit grit and the warm scatter of hot air. Both are overridable; these
# are what read as afternoon over a red-earth scene.
DEFAULT_DUST_COLOR = (0.78, 0.62, 0.42)
DEFAULT_SUN_COLOR = (0.95, 0.65, 0.32)

# How fast a gust decays back to the standing dust level, per second.
GUST_DECAY = 1.6

HEAT_HAZE = FullscreenShader(
    "heat_haze",
    inputs=("u_texture",),
    uniforms=(
        Uniform("u_resolution", "vec2"),
        Uniform("u_time"),
        Uniform("u_haze"),
        Uniform("u_haze_scale"),
        Uniform("u_haze_speed"),
        Uniform("u_horizon"),
        Uniform("u_dust"),
        Uniform("u_dust_color", "vec3"),
        Uniform("u_wind"),
        Uniform("u_sun"),
        Uniform("u_sun_color", "vec3"),
    ),
    # A line-for-line port of heat_haze.frag; see it for the reasoning.
    # Ported in GL's coordinate convention, not wgpu's: `v_uv` is rebuilt
    # with y up, every expression below is the GLSL's, and only the texture
    # read flips back. The shimmer and motes are hashes of position, so
    # mirroring the coordinates instead would mirror nothing -- it would
    # draw different noise.
    wgsl="""
fn hash21(p: vec2<f32>) -> f32 {
    return fract(sin(dot(p, vec2<f32>(127.1, 311.7))) * 43758.5453);
}

fn vnoise(p: vec2<f32>) -> f32 {
    let i = floor(p);
    let f = fract(p);
    let u = f * f * (3.0 - 2.0 * f);
    let a = hash21(i);
    let b = hash21(i + vec2<f32>(1.0, 0.0));
    let c = hash21(i + vec2<f32>(0.0, 1.0));
    let d = hash21(i + vec2<f32>(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

fn fbm(p: vec2<f32>) -> f32 {
    return vnoise(p) * 0.65 + vnoise(p * 2.17 + 11.3) * 0.35;
}

fn dust_layer(uv: vec2<f32>, cells: vec2<f32>, rise: f32, drift: f32, size: f32, density: f32) -> f32 {
    var p = uv * cells;
    p.x += params.u_time * drift * params.u_wind;
    p.y -= params.u_time * rise;
    let cell = floor(p);
    let f = fract(p);
    let pick = hash21(cell);
    if (pick > density) {
        return 0.0;
    }
    let centre = vec2<f32>(
        hash21(cell + vec2<f32>(13.7, 7.1)),
        hash21(cell + vec2<f32>(3.3, 91.7)),
    );
    let mote = smoothstep(size, 0.0, distance(f, centre));
    let twinkle = 0.55 + 0.45 * sin(params.u_time * 1.7 + pick * 43.0);
    return mote * twinkle;
}

@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let v_uv = vec2<f32>(in.uv.x, 1.0 - in.uv.y);
    let ground = smoothstep(params.u_horizon, 1.0, 1.0 - v_uv.y);
    let heat = params.u_haze * mix(0.4, 1.0, ground);
    let flow = vec2<f32>(params.u_time * params.u_wind * 0.06, -params.u_time * params.u_haze_speed);
    let sp = v_uv * params.u_haze_scale + flow;
    let nx = fbm(sp);
    let ny = fbm(sp + vec2<f32>(37.2, 18.9));
    let shimmer = vec2<f32>(nx, ny) - 0.5;
    let offset = vec2<f32>(shimmer.x, shimmer.y * 0.5) * 2.0 * heat / params.u_resolution;
    let uv = clamp(v_uv + offset, vec2<f32>(0.0), vec2<f32>(1.0));
    var color = textureSample(u_texture, input_sampler, vec2<f32>(uv.x, 1.0 - uv.y));
    let churn = abs(shimmer.x) + abs(shimmer.y);
    color = vec4<f32>(color.rgb + params.u_sun_color * (params.u_sun * churn * ground), color.a);
    if (params.u_dust > 0.0) {
        let aspect = params.u_resolution.x / params.u_resolution.y;
        let motes =
            dust_layer(v_uv, vec2<f32>(aspect, 1.0) * 26.0, 0.035, 0.10, 0.055, 0.30) * 0.55
          + dust_layer(v_uv, vec2<f32>(aspect, 1.0) * 15.0, 0.055, 0.17, 0.075, 0.22) * 0.75
          + dust_layer(v_uv, vec2<f32>(aspect, 1.0) * 8.0, 0.085, 0.26, 0.095, 0.14) * 1.0;
        color = vec4<f32>(color.rgb + params.u_dust_color * motes * params.u_dust, color.a);
    }
    return color;
}
""",
)


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
        """Set the heat haze's starting conditions.

        Args:
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
        device: GraphicsDevice,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Refract the input frame and lay dust over it.

        Args:
            device: What to run the shader on.
            input_fbo: Source framebuffer.
            output_fbo: Destination framebuffer.
        """
        device.run(
            HEAT_HAZE,
            {"u_texture": input_fbo},
            {
                "u_resolution": (float(input_fbo.width), float(input_fbo.height)),
                "u_time": self._time,
                "u_haze": self.haze,
                "u_haze_scale": self.haze_scale,
                "u_haze_speed": self.haze_speed,
                "u_horizon": self.horizon,
                "u_dust": min(1.0, self.dust + self._gust),
                "u_dust_color": self.dust_color,
                "u_wind": self.wind,
                "u_sun": self.sun,
                "u_sun_color": self.sun_color,
            },
            output_fbo,
        )
