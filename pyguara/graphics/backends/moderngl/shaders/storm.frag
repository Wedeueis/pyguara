#version 330 core

// Weather overlay: falling rain, sheet lightning, and the bolt itself.
//
// Everything is procedural. There is no rain texture and no bolt sprite,
// so the cost is constant per pixel however heavy the downpour gets, and
// changing the weather means changing a uniform rather than authoring an
// asset.
//
// The shader owns only the *appearance*. The weather state -- how hard it
// is raining, when a strike lands, where it lands -- is driven from the
// CPU, which is what lets a game sync a thunderclap, a screen shake and a
// light-map boost to the same bolt.

in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform vec2 u_resolution;
uniform float u_time;

uniform float u_rain;        // 0 = dry, 1 = downpour
uniform float u_rain_speed;  // multiplier on how fast the drops fall
uniform float u_wind;        // streak slant; negative blows to the left
uniform vec3 u_rain_color;

uniform float u_flash;       // sheet lightning washing over the whole frame
uniform vec3 u_flash_color;

uniform float u_bolt;        // the bolt's own brightness, 0 = no bolt
uniform float u_bolt_x;      // where it falls, 0..1 across the frame
uniform float u_bolt_seed;   // reshapes it -- a new value is a new bolt

float hash11(float n) {
    return fract(sin(n * 78.233) * 43758.5453);
}

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

// A triangle wave in [-1, 1]. Used instead of sin() for the bolt, whose
// character is sharp direction changes -- a sine sum wanders, it does not
// fork.
float tri(float x) {
    return abs(fract(x) - 0.5) * 4.0 - 1.0;
}

// One depth of rain: a grid of cells, each holding at most one streak,
// scrolling downward. Several of these at different densities read as
// depth, because the near ones are longer, wider and faster.
//
// cells:   how many cells tall the screen is (sets streak spacing)
// speed:   fall rate in screen heights per second
// dash:    streak length as a fraction of one cell
// width:   streak half-width as a fraction of one cell
// density: fraction of cells holding a drop
float rain_layer(
    vec2 uv, float cells, float speed, float dash, float width, float density
) {
    vec2 p = uv * cells;
    p.x += p.y * u_wind;
    // v_uv.y points up, so advancing p.y walks the pattern down the screen.
    p.y += u_time * speed * u_rain_speed * cells;

    float column = floor(p.x);
    p.y += hash11(column) * 7.0;  // columns fall out of step with each other

    vec2 cell = vec2(column, floor(p.y));
    vec2 f = fract(p);

    float exists = step(1.0 - density, hash21(cell));
    float across = 1.0 - smoothstep(0.0, width, abs(f.x - 0.5));
    float along = smoothstep(0.0, dash * 0.35, f.y)
                * (1.0 - smoothstep(dash * 0.7, dash, f.y));

    return exists * across * along;
}

// How far the bolt has wandered from its origin, `t` fractions of the way
// down its span. The amplitude grows as it descends, the way a real strike
// spreads out from the cloud base.
float bolt_offset(float t, float seed) {
    float o = tri(t * 3.5 + seed * 7.3) * 0.030;
    o += tri(t * 9.0 + seed * 13.7) * 0.013;
    o += tri(t * 21.0 + seed * 23.1) * 0.005;
    return o * (0.35 + 1.8 * t);
}

// One stroke of lightning, as a distance field: a hot core that tapers as
// it descends, wrapped in an exponential halo so it reads as light rather
// than as a drawn line.
float bolt_stroke(
    vec2 uv, float x0, float seed, float y_top, float y_end, float width
) {
    float span = max(y_top - y_end, 1e-4);
    float t = clamp((y_top - uv.y) / span, 0.0, 1.0);
    float inside = step(y_end, uv.y) * step(uv.y, y_top);

    float x = x0 + bolt_offset(t, seed);
    float d = abs(uv.x - x);

    float core = 1.0 - smoothstep(0.0, width * mix(1.2, 0.45, t), d);
    float halo = exp(-d / (width * 9.0)) * 0.55;

    return inside * (core + halo);
}

void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 auv = vec2(v_uv.x * aspect, v_uv.y);

    vec3 color = texture(u_texture, v_uv).rgb;

    if (u_rain > 0.0) {
        float rain = rain_layer(auv, 15.0, 0.85, 0.20, 0.030, 0.30) * 0.45;
        rain += rain_layer(auv, 10.0, 1.40, 0.27, 0.045, 0.22) * 0.75;
        rain += rain_layer(auv, 6.0, 2.20, 0.28, 0.060, 0.14) * 1.00;
        color += u_rain_color * rain * u_rain;
    }

    // The bolt is added after the rain so a strike lights the drops in
    // front of it rather than being occluded by them.
    float bolt = 0.0;
    if (u_bolt > 0.0) {
        float bx = u_bolt_x * aspect;
        bolt = bolt_stroke(auv, bx, u_bolt_seed, 1.05, 0.10, 0.0045);

        // One fork, branching off wherever the main stroke happens to be.
        float fork_y = mix(0.72, 0.42, hash11(u_bolt_seed * 3.1));
        float fork_t = clamp((1.05 - fork_y) / 0.95, 0.0, 1.0);
        float fork_x = bx + bolt_offset(fork_t, u_bolt_seed);
        bolt += 0.6 * bolt_stroke(
            auv, fork_x, u_bolt_seed + 5.0, fork_y, fork_y - 0.32, 0.0028
        );
    }

    // Sheet lightning lifts what is already there rather than only washing
    // white over it, so a strike reveals the scene instead of erasing it.
    color = color * (1.0 + 0.9 * u_flash) + u_flash_color * (0.28 * u_flash);
    color += u_flash_color * bolt * u_bolt * 1.6;

    frag_color = vec4(color, 1.0);
}
