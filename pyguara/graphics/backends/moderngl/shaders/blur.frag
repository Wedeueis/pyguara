#version 330 core

// Separable Gaussian blur shader
// Run horizontally then vertically for full blur
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform vec2 u_direction;  // (1,0) for horizontal, (0,1) for vertical
uniform vec2 u_texel_size; // 1.0 / texture_size

// 9-tap Gaussian weights (sigma ~= 2.0)
const float weights[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);

void main() {
    vec3 result = texture(u_texture, v_uv).rgb * weights[0];

    vec2 offset = u_direction * u_texel_size;

    // Sample in both directions from center
    for (int i = 1; i < 5; i++) {
        vec2 sample_offset = offset * float(i);
        result += texture(u_texture, v_uv + sample_offset).rgb * weights[i];
        result += texture(u_texture, v_uv - sample_offset).rgb * weights[i];
    }

    frag_color = vec4(result, 1.0);
}
