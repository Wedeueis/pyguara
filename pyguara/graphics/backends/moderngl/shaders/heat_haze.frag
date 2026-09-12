#version 330 core

// Hot air: a refracting shimmer rising off sun-baked ground, with dust
// drifting through it.
//
// Everything is procedural, so a blazing afternoon costs exactly what a
// mild one costs and neither puts a single particle through the ECS.
//
// The shader owns only the *appearance*. How hot it is, which way the
// wind blows, how much dust a scuffle has kicked up -- all of that is
// driven from the CPU, which is what lets a game tie a gust to an
// explosion it already knows about.

in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform vec2 u_resolution;
uniform float u_time;

uniform float u_haze;        // refraction strength, in pixels of offset
uniform float u_haze_scale;  // spatial frequency of the shimmer cells
uniform float u_haze_speed;  // how fast the shimmer rises
uniform float u_horizon;     // 0..1 down the frame; heat builds below it

uniform float u_dust;        // 0 = clear, 1 = a duststorm
uniform vec3 u_dust_color;
uniform float u_wind;        // lateral drift; negative blows left

uniform float u_sun;         // warm bleed the shimmer glows with
uniform vec3 u_sun_color;

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

// Value noise: smooth, cheap, and tileable enough that nothing in a
// shimmer reads as a repeat.
float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);

    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));

    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// Two octaves is the whole budget. A third adds detail finer than the
// refraction can displace, so it costs a texture fetch and shows nothing.
float fbm(vec2 p) {
    return vnoise(p) * 0.65 + vnoise(p * 2.17 + 11.3) * 0.35;
}

// One depth of dust: a grid of cells, each holding at most one mote,
// drifting with the wind and rising slowly. Several of these at different
// densities read as depth, because the near ones are larger and faster.
//
// cells:   grid resolution, aspect-corrected so motes stay round
// rise:    upward drift in screen heights per second
// drift:   lateral drift, scaled by the wind
// size:    mote radius as a fraction of one cell
// density: fraction of cells holding a mote
float dust_layer(
    vec2 uv, vec2 cells, float rise, float drift, float size, float density
) {
    vec2 p = uv * cells;
    p.x += u_time * drift * u_wind;
    p.y -= u_time * rise;

    vec2 cell = floor(p);
    vec2 f = fract(p);

    // Reject most cells outright, so dust reads as scattered motes rather
    // than as a regular lattice with gaps.
    float pick = hash21(cell);
    if (pick > density) {
        return 0.0;
    }

    vec2 centre = vec2(
        hash21(cell + vec2(13.7, 7.1)),
        hash21(cell + vec2(3.3, 91.7))
    );
    float mote = smoothstep(size, 0.0, distance(f, centre));

    // Each mote breathes on its own phase, so the field never pulses as
    // one.
    float twinkle = 0.55 + 0.45 * sin(u_time * 1.7 + pick * 43.0);

    return mote * twinkle;
}

void main() {
    // Heat pools on the ground. Above the horizon there is still some
    // shimmer -- air does not stop moving -- but the strength ramps into
    // the bottom of the frame, where the baked earth is.
    float ground = smoothstep(u_horizon, 1.0, v_uv.y);
    float heat = u_haze * mix(0.4, 1.0, ground);

    // Two noise fields sampled a little apart: one displaces horizontally,
    // the other vertically. Sampling one field twice would displace both
    // axes in lockstep, which reads as the frame sliding rather than as
    // air churning.
    vec2 flow = vec2(u_time * u_wind * 0.06, -u_time * u_haze_speed);
    vec2 sp = v_uv * u_haze_scale + flow;

    float nx = fbm(sp);
    float ny = fbm(sp + vec2(37.2, 18.9));
    vec2 shimmer = vec2(nx, ny) - 0.5;

    // Vertical displacement is halved: rising air stretches a scene far
    // more side to side than it does up and down, and the full amount
    // reads as a wobble rather than as heat.
    vec2 offset = vec2(shimmer.x, shimmer.y * 0.5) * 2.0 * heat / u_resolution;

    vec2 uv = clamp(v_uv + offset, vec2(0.0), vec2(1.0));
    vec4 color = texture(u_texture, uv);

    // Where the air churns hardest it glows, faintly and warm -- the
    // scattered light that makes a hot afternoon look hot.
    float churn = abs(shimmer.x) + abs(shimmer.y);
    color.rgb += u_sun_color * (u_sun * churn * ground);

    if (u_dust > 0.0) {
        float motes =
            dust_layer(v_uv, vec2(u_resolution.x / u_resolution.y, 1.0) * 26.0,
                       0.035, 0.10, 0.055, 0.30) * 0.55
          + dust_layer(v_uv, vec2(u_resolution.x / u_resolution.y, 1.0) * 15.0,
                       0.055, 0.17, 0.075, 0.22) * 0.75
          + dust_layer(v_uv, vec2(u_resolution.x / u_resolution.y, 1.0) * 8.0,
                       0.085, 0.26, 0.095, 0.14) * 1.0;

        color.rgb += u_dust_color * motes * u_dust;
    }

    frag_color = color;
}
