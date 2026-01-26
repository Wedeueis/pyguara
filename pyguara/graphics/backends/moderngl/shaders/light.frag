#version 330 core

// Light fragment shader
// Creates a radial gradient with configurable falloff

in vec2 v_uv;
in vec3 v_color;
in float v_intensity;
in float v_falloff;

out vec4 frag_color;

void main() {
    // Calculate distance from center (UV is 0-1, center is 0.5)
    vec2 center = vec2(0.5, 0.5);
    float dist = distance(v_uv, center) * 2.0; // Normalize to 0-1 range

    // Apply falloff curve (inverse power law)
    // falloff = 1.0: linear, falloff = 2.0: quadratic (realistic), etc.
    float attenuation = 1.0 - pow(clamp(dist, 0.0, 1.0), v_falloff);
    attenuation = max(attenuation, 0.0);

    // Smooth the edge to avoid hard cutoff
    attenuation = smoothstep(0.0, 1.0, attenuation);

    // Calculate final light contribution
    float lightStrength = attenuation * v_intensity;

    // Output with additive blending (handled by blend mode)
    frag_color = vec4(v_color * lightStrength, 1.0);
}
