#version 330 core

// An expanding wavefront: a bright annulus rather than the filled radial
// disc `light.frag` draws. Shares that shader's instance layout so the
// same quad/instance plumbing drives both.

in vec2 v_local;        // -1..1 across the instance quad
in vec3 v_color;
in float v_intensity;
in float v_thickness;   // band half-width, as a fraction of the radius

out vec4 frag_color;

void main() {
    float dist = length(v_local);

    // Outside the quad's inscribed circle there is nothing to draw, and
    // discarding early keeps the additive blend from tinting the corners.
    if (dist > 1.0) {
        discard;
    }

    // Distance from the wavefront itself (the rim of the disc), not from
    // its centre -- this is what turns the disc into a ring.
    float band = abs(1.0 - dist);
    float falloff = 1.0 - smoothstep(0.0, max(v_thickness, 0.001), band);

    // A soft inner glow trailing behind the crest, so the ring reads as a
    // wave of energy rather than a wireframe circle.
    float wake = (1.0 - smoothstep(0.0, 1.0, dist)) * 0.18;

    float strength = (falloff + wake) * v_intensity;
    if (strength <= 0.001) {
        discard;
    }

    frag_color = vec4(v_color * strength, strength);
}
