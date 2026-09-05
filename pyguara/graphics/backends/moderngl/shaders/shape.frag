#version 330 core

// Input from vertex shader
in vec2 v_local;
in vec2 v_size;
in vec4 v_color;
in float v_width;
in float v_shape_type;

// Output color
out vec4 frag_color;

// Signed distance to an axis-aligned box, centered at the origin.
float sd_box(vec2 p, vec2 half_extent) {
    vec2 d = abs(p) - half_extent;
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}

// Signed distance to a circle, centered at the origin.
float sd_circle(vec2 p, float radius) {
    return length(p) - radius;
}

// Signed distance to a capsule (thick line segment) along the local x-axis.
float sd_segment(vec2 p, float half_length, float half_width) {
    vec2 q = vec2(clamp(p.x, -half_length, half_length), 0.0);
    return length(p - q) - half_width;
}

void main() {
    int shape = int(v_shape_type + 0.5);
    float half_stroke = v_width * 0.5;
    float d;

    if (shape == 0) {
        // v_size is padded by half_stroke to keep a stroked border unclipped
        // by the instance quad; recover the true box half-extent here.
        d = sd_box(v_local, v_size - vec2(half_stroke));
    } else if (shape == 1) {
        d = sd_circle(v_local, v_size.x - half_stroke);
    } else {
        // Lines are always filled capsules: v_size.x is padded by v_size.y
        // (the capsule's rounded end caps), recovered here as the true
        // half-length.
        d = sd_segment(v_local, v_size.x - v_size.y, v_size.y);
    }

    float alpha = v_width <= 0.0 ? step(d, 0.0) : step(abs(d), half_stroke);

    if (alpha <= 0.0) {
        discard;
    }

    frag_color = vec4(v_color.rgb, v_color.a * alpha);
}
