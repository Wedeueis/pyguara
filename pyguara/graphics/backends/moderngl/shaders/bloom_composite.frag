#version 330 core

// Bloom composite shader - adds bloom to the scene
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_scene;  // Original scene
uniform sampler2D u_bloom;  // Blurred bright pixels
uniform float u_intensity;  // Bloom intensity (default: 1.0)

// Where the highlight roll-off begins. Below this the curve is the
// identity, so anything lit against the old clamped pipeline is untouched.
const float KNEE = 0.8;

// Bring the HDR range into something the screen can show.
//
// The chain is 16-bit float end to end (`pipeline/buffers.py`), so an
// additive bloom really does leave values above 1.0 here -- a 2.0 scene
// pixel composites to ~4.0. `FinalPass` blits to an 8-bit target, which
// hard-clips every one of them to flat white: the brightest parts of the
// frame lose all their detail at exactly the moment the bloom is meant to
// be doing something.
//
// A plain Reinhard (`x / (x + 1)`) would map that range in, but it
// compresses the whole scale with it -- mid-grey 0.5 becomes 0.333 -- and
// re-grades every lit pixel in the two demos that use bloom. So roll off
// only above a knee instead: identity below it, asymptotic to 1.0 above,
// and C1-continuous at the join so there is no visible seam where the
// curve starts to bend.
vec3 tonemap(vec3 color) {
    vec3 excess = max(color - vec3(KNEE), vec3(0.0));
    vec3 headroom = vec3(1.0 - KNEE);
    return min(color, vec3(KNEE)) + headroom * (excess / (excess + headroom));
}

void main() {
    vec4 scene_color = texture(u_scene, v_uv);
    vec4 bloom_color = texture(u_bloom, v_uv);

    // Additive blend
    vec3 result = scene_color.rgb + bloom_color.rgb * u_intensity;

    frag_color = vec4(tonemap(result), scene_color.a);
}
