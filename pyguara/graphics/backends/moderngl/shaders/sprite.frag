#version 330 core

// Input from vertex shader
in vec2 v_uv;

// Output color
out vec4 frag_color;

// Texture sampler
uniform sampler2D u_texture;

void main() {
    // Sample the texture and output with alpha
    frag_color = texture(u_texture, v_uv);
}
