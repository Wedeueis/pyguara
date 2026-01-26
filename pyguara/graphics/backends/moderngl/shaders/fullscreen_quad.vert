#version 330 core

// Fullscreen quad vertex shader
// Generates a full-screen triangle strip without vertex buffers

out vec2 v_uv;

void main() {
    // Generate vertices for a fullscreen quad using gl_VertexID
    // 0: (-1, -1), 1: (1, -1), 2: (-1, 1), 3: (1, 1)
    vec2 vertices[4] = vec2[4](
        vec2(-1.0, -1.0),
        vec2( 1.0, -1.0),
        vec2(-1.0,  1.0),
        vec2( 1.0,  1.0)
    );

    vec2 uvs[4] = vec2[4](
        vec2(0.0, 0.0),
        vec2(1.0, 0.0),
        vec2(0.0, 1.0),
        vec2(1.0, 1.0)
    );

    gl_Position = vec4(vertices[gl_VertexID], 0.0, 1.0);
    v_uv = uvs[gl_VertexID];
}
