#version 330 core

// Bloom composite shader - adds bloom to the scene
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_scene;  // Original scene
uniform sampler2D u_bloom;  // Blurred bright pixels
uniform float u_intensity;  // Bloom intensity (default: 1.0)

void main() {
    vec4 scene_color = texture(u_scene, v_uv);
    vec4 bloom_color = texture(u_bloom, v_uv);

    // Additive blend
    vec3 result = scene_color.rgb + bloom_color.rgb * u_intensity;

    // Optional: Tone mapping to prevent over-saturation
    // result = result / (result + vec3(1.0)); // Reinhard tone mapping

    frag_color = vec4(result, scene_color.a);
}
