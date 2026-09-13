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
layout(location = 7) in float in_type;          // LightType value (1/2/3)
layout(location = 8) in float in_spot_dir;      // Cone axis, radians
layout(location = 9) in float in_spot_cos_half; // cos(spot_angle / 2)

uniform mat4 u_projection;

// Outputs to fragment shader
out vec2 v_uv;
out vec3 v_color;
out float v_intensity;
out float v_falloff;
flat out float v_type;
out float v_spot_dir;
out float v_spot_cos_half;

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
    // `flat`: the type is a discriminant, not a quantity. Interpolating it
    // across the quad would produce fragments claiming to be 1.4 of a light.
    v_type = in_type;
    v_spot_dir = in_spot_dir;
    v_spot_cos_half = in_spot_cos_half;
}
