#version 330 core

// Light fragment shader
// Radial gradient with configurable falloff, plus the two non-point
// shapes: a directional light that covers its quad evenly, and a spot
// light masked to a cone.

in vec2 v_uv;
in vec3 v_color;
in float v_intensity;
in float v_falloff;
flat in float v_type;
in float v_spot_dir;
in float v_spot_cos_half;

out vec4 frag_color;

// Matches pyguara.graphics.lighting.components.LightType.
const float TYPE_POINT = 1.0;
const float TYPE_DIRECTIONAL = 2.0;
const float TYPE_SPOT = 3.0;

void main() {
    // Calculate distance from center (UV is 0-1, center is 0.5)
    vec2 center = vec2(0.5, 0.5);
    vec2 offset = v_uv - center;
    float dist = length(offset) * 2.0; // Normalize to 0-1 range

    // Apply falloff curve (inverse power law)
    // falloff = 1.0: linear, falloff = 2.0: quadratic (realistic), etc.
    float attenuation = 1.0 - pow(clamp(dist, 0.0, 1.0), v_falloff);
    attenuation = max(attenuation, 0.0);

    // Smooth the edge to avoid hard cutoff
    attenuation = smoothstep(0.0, 1.0, attenuation);

    if (v_type == TYPE_DIRECTIONAL) {
        // Parallel rays: no point to fall off from. The quad is lit
        // evenly, and `radius` bounds the area rather than shaping it --
        // a scene-wide sun is a directional light with a large radius.
        attenuation = 1.0;
    } else if (v_type == TYPE_SPOT) {
        // Cone test. The half-angle arrives as its cosine, precomputed on
        // the CPU, so this is a dot product rather than a per-fragment
        // acos. Angles run clockwise from screen +x because screen Y
        // points down -- the same convention `draw_line` uses.
        vec2 axis = vec2(cos(v_spot_dir), sin(v_spot_dir));
        // At the exact centre the direction is undefined; normalize()
        // would divide by zero, and the centre is inside every cone.
        float aligned = dist > 0.0001 ? dot(normalize(offset), axis) : 1.0;

        // Soften the rim over a fixed slice of the cone rather than a
        // fixed angle, so a narrow cone does not end up entirely edge.
        float edge = (1.0 - v_spot_cos_half) * 0.15 + 0.0001;
        attenuation *= smoothstep(
            v_spot_cos_half - edge, v_spot_cos_half + edge, aligned
        );
    }

    // Calculate final light contribution
    float lightStrength = attenuation * v_intensity;

    // Output with additive blending (handled by blend mode)
    frag_color = vec4(v_color * lightStrength, 1.0);
}
