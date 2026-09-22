#version 330 core

// Soil health color grade: tints the finished frame toward the plot's
// overall soil condition -- warm and green as organic matter builds up,
// dusty and reddish where chemical treatment has degraded it.
//
// Driven by two plain floats computed on the CPU from the plot's soil
// cells (an average, not a per-tile read -- there is no per-tile data on
// the GPU side at all), so this is a whole-scene mood, not a per-tile
// effect. u_strength lets the caller fade it in/out (e.g. only once the
// plot has enough tilled ground to have a "condition" worth showing).

in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform float u_health;    // 0 = degraded/dry, 1 = rich/organic
uniform float u_strength;  // overall blend amount; 0 disables the grade

const vec3 SICK_TINT = vec3(0.95, 0.62, 0.45);      // dusty, chemical red-brown
const vec3 THRIVING_TINT = vec3(0.65, 1.05, 0.72);  // warm, saturated green

void main() {
    vec4 color = texture(u_texture, v_uv);

    vec3 tint = mix(SICK_TINT, THRIVING_TINT, clamp(u_health, 0.0, 1.0));
    vec3 graded = color.rgb * tint;
    vec3 result = mix(color.rgb, graded, clamp(u_strength, 0.0, 1.0));

    frag_color = vec4(result, color.a);
}
