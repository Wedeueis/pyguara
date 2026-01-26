#version 330 core

// Light vertex shader
// Renders a quad for each light, positioned and scaled appropriately

layout(location = 0) in vec2 in_vert;   // Unit quad vertex (-0.5 to 0.5)
layout(location = 1) in vec2 in_uv;     // Texture coordinates

// Per-instance attributes
layout(location = 2) in vec2 in_pos;     // Screen position (pixels)
layout(location = 3) in float in_radius; // Light radius (pixels)
layout(location = 4) in vec3 in_color;   // Light color (normalized RGB)
layout(location = 5) in float in_intensity;
layout(location = 6) in float in_falloff;

uniform mat4 u_projection;

// Outputs to fragment shader
out vec2 v_uv;
out vec3 v_color;
out float v_intensity;
out float v_falloff;

void main() {
    // Scale quad by light diameter (radius * 2)
    vec2 scaled = in_vert * in_radius * 2.0;

    // Translate to screen position
    gl_Position = u_projection * vec4(scaled + in_pos, 0.0, 1.0);

    // Pass interpolated data to fragment shader
    v_uv = in_uv;
    v_color = in_color;
    v_intensity = in_intensity;
    v_falloff = in_falloff;
}
