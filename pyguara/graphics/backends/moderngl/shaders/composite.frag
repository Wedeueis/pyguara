#version 330 core

// Composite shader - multiplies world texture by light map
// Creates the final lit scene

in vec2 v_uv;

out vec4 frag_color;

uniform sampler2D u_world;      // The rendered world (sprites, etc.)
uniform sampler2D u_lightmap;   // The light accumulation buffer

void main() {
    // Sample both textures
    vec4 world_color = texture(u_world, v_uv);
    vec4 light_color = texture(u_lightmap, v_uv);

    // Multiply world by light to get lit result
    // Light RGB values > 1.0 will brighten, < 1.0 will darken
    vec3 lit = world_color.rgb * light_color.rgb;

    // Preserve world alpha (for transparency)
    frag_color = vec4(lit, world_color.a);
}
