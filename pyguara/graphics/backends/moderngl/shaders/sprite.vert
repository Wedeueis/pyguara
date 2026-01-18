#version 330 core

// Quad vertex attributes (static geometry)
layout(location = 0) in vec2 in_vert;   // Quad vertex position (-0.5 to 0.5)
layout(location = 1) in vec2 in_uv;     // Texture coordinates (0.0 to 1.0)

// Per-instance attributes (dynamic, changes per sprite)
layout(location = 2) in vec2 in_pos;    // Screen position (pixels)
layout(location = 3) in float in_rot;   // Rotation (radians)
layout(location = 4) in vec2 in_scale;  // Scale factor
layout(location = 5) in vec2 in_size;   // Texture dimensions (pixels)

// Uniforms
uniform mat4 u_projection;

// Output to fragment shader
out vec2 v_uv;

void main() {
    // Apply size and scale to the base quad vertex
    vec2 sized = in_vert * in_size * in_scale;

    // Apply rotation (2D rotation matrix)
    float c = cos(in_rot);
    float s = sin(in_rot);
    vec2 rotated = mat2(c, -s, s, c) * sized;

    // Translate to screen position and project
    gl_Position = u_projection * vec4(rotated + in_pos, 0.0, 1.0);

    // Pass UV coordinates to fragment shader
    v_uv = in_uv;
}
