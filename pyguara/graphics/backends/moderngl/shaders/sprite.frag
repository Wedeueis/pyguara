#version 330 core

// Input from vertex shader
in vec2 v_uv;
in vec4 v_color;

// Output color
out vec4 frag_color;

// Texture sampler
uniform sampler2D u_texture;

void main() {
    // Sample the texture and multiply by the per-instance tint.
    //
    // A straight multiply matches what the Pygame backend gets from
    // BLEND_RGBA_MULT, because the blend func set in PygameGLWindow.open()
    // is the non-premultiplied SRC_ALPHA / ONE_MINUS_SRC_ALPHA pair: the
    // alpha column is consumed by the blend, not by the colour channels.
    // A pipeline that switched to premultiplied alpha would need the RGB
    // scaled by the tint's alpha here, and would otherwise diverge from
    // Pygame silently.
    frag_color = texture(u_texture, v_uv) * v_color;
}
