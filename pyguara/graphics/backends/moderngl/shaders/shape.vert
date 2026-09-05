#version 330 core

// Quad vertex attributes (static geometry, -0.5 to 0.5)
layout(location = 0) in vec2 in_vert;

// Per-instance attributes (dynamic, one shape per instance)
layout(location = 1) in vec2 in_pos;         // World-space center (pixels)
layout(location = 2) in vec2 in_size;        // Padded half-extents; see shape.frag
layout(location = 3) in float in_rotation;   // Radians
layout(location = 4) in vec4 in_color;       // Normalized RGBA
layout(location = 5) in float in_width;      // Stroke width in pixels, 0 = filled
layout(location = 6) in float in_shape_type; // 0 = rect, 1 = circle, 2 = line

// Uniforms
uniform mat4 u_projection;

// Output to fragment shader
out vec2 v_local;
out vec2 v_size;
out vec4 v_color;
out float v_width;
out float v_shape_type;

void main() {
    // Scale the unit quad by the instance's padded half-extents
    vec2 local = in_vert * 2.0 * in_size;

    // Apply rotation (2D rotation matrix)
    float c = cos(in_rotation);
    float s = sin(in_rotation);
    vec2 rotated = mat2(c, -s, s, c) * local;

    // Translate to world position and project
    gl_Position = u_projection * vec4(rotated + in_pos, 0.0, 1.0);

    // Pass local-space (unrotated) coordinates for SDF evaluation
    v_local = local;
    v_size = in_size;
    v_color = in_color;
    v_width = in_width;
    v_shape_type = in_shape_type;
}
