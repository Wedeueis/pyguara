#version 330

// ImGui's vertex colour is straight (not premultiplied) alpha, and the
// engine's default blend mode is the matching SRC_ALPHA / ONE_MINUS_SRC_ALPHA
// pair, so a plain multiply is correct here. Premultiplying would double the
// alpha term.
uniform sampler2D u_texture;

in vec2 v_uv;
in vec4 v_color;

out vec4 f_color;

void main() {
    f_color = v_color * texture(u_texture, v_uv);
}
