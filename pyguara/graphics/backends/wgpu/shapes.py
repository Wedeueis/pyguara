"""`ShapeBatch` on wgpu: ModernGL's shape shader, ported.

A batch's rows are already the instance layout `shape.vert` reads --
centre, padded half-size, rotation, colour, stroke, kind -- so they go to
the GPU as they are, one instanced draw for the whole batch.

**These follow ModernGL's conventions, not pygame's.** A line in a batch is
a capsule with rounded ends, and a circle's edge is a signed distance at
the pixel centre. The renderer's per-primitive `draw_line` and
`draw_circle` match pygame instead. They meet in `Sparks`, the one
producer of batches, and those are the shapes the demos that use sparks
were made to look like on ModernGL, which is what stage D holds them to.
"""

from __future__ import annotations

from pyguara.graphics.pipeline.device import Attribute, InstancedShader, Uniform

SHAPES = InstancedShader(
    "shapes",
    attributes=(
        Attribute("pos", "vec2"),
        Attribute("size", "vec2"),
        Attribute("rotation"),
        Attribute("color", "vec4"),
        Attribute("width"),
        # `shape_type` in the GLSL; `type` is reserved in WGSL.
        Attribute("kind"),
    ),
    uniforms=(Uniform("u_projection", "mat4"),),
    wgsl="""
struct Varying {
    @builtin(position) position: vec4<f32>,
    @location(0) local: vec2<f32>,
    @location(1) size: vec2<f32>,
    @location(2) color: vec4<f32>,
    @location(3) width: f32,
    @location(4) @interpolate(flat) kind: f32,
};

@vertex
fn vertex(@builtin(vertex_index) index: u32, shape: Instance) -> Varying {
    let local = quad_corner(index) * 2.0 * shape.size;
    let c = cos(shape.rotation);
    let s = sin(shape.rotation);
    // shape.vert's mat2(c, s, -s, c) * local: from +x towards +y.
    let rotated = vec2<f32>(c * local.x - s * local.y, s * local.x + c * local.y);
    var out: Varying;
    out.position = params.u_projection * vec4<f32>(rotated + shape.pos, 0.0, 1.0);
    out.local = local;
    out.size = shape.size;
    out.color = shape.color;
    out.width = shape.width;
    out.kind = shape.kind;
    return out;
}

fn sd_box(p: vec2<f32>, half_extent: vec2<f32>) -> f32 {
    let d = abs(p) - half_extent;
    return length(max(d, vec2<f32>(0.0))) + min(max(d.x, d.y), 0.0);
}

fn sd_segment(p: vec2<f32>, half_length: f32, half_width: f32) -> f32 {
    let q = vec2<f32>(clamp(p.x, -half_length, half_length), 0.0);
    return length(p - q) - half_width;
}

@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let shape = i32(in.kind + 0.5);
    let half_stroke = in.width * 0.5;
    var d: f32;
    if (shape == 0) {
        d = sd_box(in.local, in.size - vec2<f32>(half_stroke));
    } else if (shape == 1) {
        d = length(in.local) - (in.size.x - half_stroke);
    } else {
        d = sd_segment(in.local, in.size.x - in.size.y, in.size.y);
    }
    var alpha = step(d, 0.0);
    if (in.width > 0.0) {
        alpha = step(-in.width, d) * step(d, 0.0);
    }
    if (alpha <= 0.0) {
        discard;
    }
    return vec4<f32>(in.color.rgb, in.color.a * alpha);
}
""",
)
"""A batch of rectangles, circles or capsules, as `shape.frag` draws them."""
