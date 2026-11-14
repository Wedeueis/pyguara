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

from typing import TYPE_CHECKING

from pyguara.common.random import RandomStream
from pyguara.graphics.pipeline.device import FullscreenShader, Uniform
from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.device import GraphicsDevice
    from pyguara.graphics.pipeline.framebuffer import Framebuffer

# Cool, slightly blue daylight-through-cloud, and a colder white for the
# discharge itself. Both are overridable; these are what read as weather
# over a warm scene.
DEFAULT_RAIN_COLOR = (0.55, 0.72, 0.95)
DEFAULT_FLASH_COLOR = (0.78, 0.86, 1.0)

STORM = FullscreenShader(
    "storm",
    inputs=("u_texture",),
    uniforms=(
        Uniform("u_resolution", "vec2"),
        Uniform("u_time"),
        Uniform("u_rain"),
        Uniform("u_rain_speed"),
        Uniform("u_wind"),
        Uniform("u_rain_color", "vec3"),
        Uniform("u_flash"),
        Uniform("u_flash_color", "vec3"),
        Uniform("u_bolt"),
        Uniform("u_bolt_x"),
        Uniform("u_bolt_seed"),
    ),
    # A line-for-line port of storm.frag; see it for the reasoning.
    # Ported in GL's coordinate convention, not wgpu's: `v_uv` is rebuilt
    # with y up, every expression below is the GLSL's, and only the texture
    # read flips back. The rain and the bolt are hashes of position, so
    # mirroring the coordinates instead would mirror nothing -- it would
    # draw different noise.
    wgsl="""
// An integer hash of the input's exact bits (PCG), so every GPU draws the
// same noise. The usual fract(sin(x) * 43758.5453) depends on how precisely a
// GPU computes sin of a large argument, which differs between vendors and
// drivers: the same frame came out thousands of pixels apart on lavapipe.
fn pcg(v: u32) -> u32 {
    let state = v * 747796405u + 2891336453u;
    let word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
    return (word >> 22u) ^ word;
}

fn unit(h: u32) -> f32 {
    return f32(h >> 8u) / 16777216.0;
}

fn hash21(p: vec2<f32>) -> f32 {
    return unit(pcg(bitcast<u32>(p.x) ^ pcg(bitcast<u32>(p.y))));
}

fn hash11(n: f32) -> f32 {
    return unit(pcg(bitcast<u32>(n)));
}

fn tri(x: f32) -> f32 {
    return abs(fract(x) - 0.5) * 4.0 - 1.0;
}

fn rain_layer(uv: vec2<f32>, cells: f32, speed: f32, dash: f32, width: f32, density: f32) -> f32 {
    var p = uv * cells;
    p.x += p.y * params.u_wind;
    p.y += params.u_time * speed * params.u_rain_speed * cells;
    let column = floor(p.x);
    p.y += hash11(column) * 7.0;
    let cell = vec2<f32>(column, floor(p.y));
    let f = fract(p);
    let exists = step(1.0 - density, hash21(cell));
    let across = 1.0 - smoothstep(0.0, width, abs(f.x - 0.5));
    let along = smoothstep(0.0, dash * 0.35, f.y) * (1.0 - smoothstep(dash * 0.7, dash, f.y));
    return exists * across * along;
}

fn bolt_offset(t: f32, seed: f32) -> f32 {
    var o = tri(t * 3.5 + seed * 7.3) * 0.030;
    o += tri(t * 9.0 + seed * 13.7) * 0.013;
    o += tri(t * 21.0 + seed * 23.1) * 0.005;
    return o * (0.35 + 1.8 * t);
}

fn bolt_stroke(uv: vec2<f32>, x0: f32, seed: f32, y_top: f32, y_end: f32, width: f32) -> f32 {
    let span = max(y_top - y_end, 1e-4);
    let t = clamp((y_top - uv.y) / span, 0.0, 1.0);
    let inside = step(y_end, uv.y) * step(uv.y, y_top);
    let x = x0 + bolt_offset(t, seed);
    let d = abs(uv.x - x);
    let core = 1.0 - smoothstep(0.0, width * mix(1.2, 0.45, t), d);
    let halo = exp(-d / (width * 9.0)) * 0.55;
    return inside * (core + halo);
}

@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let v_uv = vec2<f32>(in.uv.x, 1.0 - in.uv.y);
    let aspect = params.u_resolution.x / max(params.u_resolution.y, 1.0);
    let auv = vec2<f32>(v_uv.x * aspect, v_uv.y);
    var color = textureSample(u_texture, input_sampler, in.uv).rgb;
    if (params.u_rain > 0.0) {
        var rain = rain_layer(auv, 15.0, 0.85, 0.20, 0.030, 0.30) * 0.45;
        rain += rain_layer(auv, 10.0, 1.40, 0.27, 0.045, 0.22) * 0.75;
        rain += rain_layer(auv, 6.0, 2.20, 0.28, 0.060, 0.14) * 1.00;
        color += params.u_rain_color * rain * params.u_rain;
    }
    var bolt = 0.0;
    if (params.u_bolt > 0.0) {
        let bx = params.u_bolt_x * aspect;
        bolt = bolt_stroke(auv, bx, params.u_bolt_seed, 1.05, 0.10, 0.0045);
        let fork_y = mix(0.72, 0.42, hash11(params.u_bolt_seed * 3.1));
        let fork_t = clamp((1.05 - fork_y) / 0.95, 0.0, 1.0);
        let fork_x = bx + bolt_offset(fork_t, params.u_bolt_seed);
        bolt += 0.6 * bolt_stroke(auv, fork_x, params.u_bolt_seed + 5.0, fork_y, fork_y - 0.32, 0.0028);
    }
    color = color * (1.0 + 0.9 * params.u_flash) + params.u_flash_color * (0.28 * params.u_flash);
    color += params.u_flash_color * bolt * params.u_bolt * 1.6;
    return vec4<f32>(color, 1.0);
}
""",
)


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
        *,
        rain: float = 0.0,
        rain_speed: float = 1.0,
        wind: float = 0.12,
        rain_color: tuple[float, float, float] = DEFAULT_RAIN_COLOR,
        flash_color: tuple[float, float, float] = DEFAULT_FLASH_COLOR,
        rng: RandomStream | None = None,
        enabled: bool = True,
    ) -> None:
        """Set the storm's starting weather.

        Args:
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
        device: GraphicsDevice,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Draw the weather over the input frame.

        Args:
            device: What to run the shader on.
            input_fbo: Source framebuffer.
            output_fbo: Destination framebuffer.
        """
        device.run(
            STORM,
            {"u_texture": input_fbo},
            {
                "u_resolution": (float(input_fbo.width), float(input_fbo.height)),
                "u_time": self._time,
                "u_rain": self.rain,
                "u_rain_speed": self.rain_speed,
                "u_wind": self.wind,
                "u_rain_color": self.rain_color,
                "u_flash": self.flash,
                "u_flash_color": self.flash_color,
                "u_bolt": self.bolt,
                "u_bolt_x": self.bolt_x,
                "u_bolt_seed": self._bolt_seed,
            },
            output_fbo,
        )
