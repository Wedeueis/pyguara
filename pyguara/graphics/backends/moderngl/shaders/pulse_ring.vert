#version 330 core

// Wavefront ring vertex shader.
//
// Deliberately mirrors `light.vert`'s instance layout, so a pulse pass can
// reuse the light pass's quad/instance buffer plumbing unchanged. The only
// differences: it hands the fragment shader a centred -1..1 coordinate
// (`v_local`) so the shader can measure distance from the rim, and it
// reads the trailing float as the ring's band thickness rather than a
// falloff exponent.

// The quad's UVs are deliberately not declared: this shader derives its
// coordinate from `in_vert` instead, and an unused attribute is stripped
// by the compiler, which then makes binding it by name fail outright.
layout(location = 0) in vec2 in_vert;   // Unit quad vertex (-0.5 .. 0.5)

layout(location = 2) in vec2 in_pos;      // Screen position (pixels)
layout(location = 3) in float in_radius;  // Current wavefront radius (pixels)
layout(location = 4) in vec3 in_color;
layout(location = 5) in float in_intensity;
layout(location = 6) in float in_thickness;

uniform mat4 u_projection;

out vec2 v_local;
out vec3 v_color;
out float v_intensity;
out float v_thickness;

void main() {
    vec2 scaled = in_vert * in_radius * 2.0;
    gl_Position = u_projection * vec4(scaled + in_pos, 0.0, 1.0);

    v_local = in_vert * 2.0;  // -1 .. 1, so length() == 1 is the wavefront
    v_color = in_color;
    v_intensity = in_intensity;
    v_thickness = in_thickness;
}
