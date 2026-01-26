#version 330 core

// Bloom threshold shader - extracts bright pixels
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform float u_threshold;  // Brightness threshold (default: 0.8)

void main() {
    vec4 color = texture(u_texture, v_uv);

    // Calculate luminance using standard weights
    float luminance = dot(color.rgb, vec3(0.2126, 0.7152, 0.0722));

    // Extract pixels brighter than threshold
    if (luminance > u_threshold) {
        // Soft knee - gradual transition
        float knee = u_threshold * 0.5;
        float soft = clamp((luminance - u_threshold + knee) / (2.0 * knee), 0.0, 1.0);
        soft = soft * soft;
        frag_color = vec4(color.rgb * soft, 1.0);
    } else {
        frag_color = vec4(0.0, 0.0, 0.0, 1.0);
    }
}
