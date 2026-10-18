#version 330

// Dear ImGui emits vertices in framebuffer-relative pixel coordinates with
// the origin top-left, so the projection here is an orthographic map from
// that space to clip space -- including the Y flip, since GL's origin is
// bottom-left. `u_display_pos` is almost always (0,0); it is non-zero only
// when ImGui viewports place a window outside the main framebuffer.
uniform vec2 u_display_pos;
uniform vec2 u_display_size;

in vec2 in_pos;
in vec2 in_uv;
in vec4 in_color;

out vec2 v_uv;
out vec4 v_color;

void main() {
    v_uv = in_uv;
    v_color = in_color;

    vec2 normalized = (in_pos - u_display_pos) / u_display_size;
    gl_Position = vec4(
        normalized.x * 2.0 - 1.0,
        1.0 - normalized.y * 2.0,
        0.0,
        1.0
    );
}
