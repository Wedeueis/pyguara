#version 330 core

// Vignette effect - darkens edges of the screen
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform float u_intensity;   // How dark the edges get (default: 0.5)
uniform float u_radius;      // Where vignette starts (default: 0.75, from center)
uniform float u_softness;    // Edge softness (default: 0.45)

void main() {
    vec4 color = texture(u_texture, v_uv);

    // Calculate distance from center (0.5, 0.5)
    vec2 center = vec2(0.5, 0.5);
    float dist = distance(v_uv, center);

    // Normalize distance based on radius
    float vignette = smoothstep(u_radius, u_radius - u_softness, dist);

    // Mix original color with darkened version
    vec3 result = color.rgb * mix(1.0 - u_intensity, 1.0, vignette);

    frag_color = vec4(result, color.a);
}
