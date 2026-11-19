#!/usr/bin/env python
"""Measure what the wgpu backend's present copy costs a frame.

The renderer draws each frame into an offscreen target and `present`
copies it onto the window with one full-screen triangle. This runs the
same work -- a full-screen pass sampling one screen-sized texture and
writing another -- N times a frame, and reports the cost of one from the
slope, so no window is needed. The frame copied is hashed noise, which a
GPU's colour compression cannot shrink, as it could a flat clear.

    uv run python tools/present_copy_probe.py
    LIBGL_ALWAYS_SOFTWARE=1 uv run python tools/present_copy_probe.py --counts 0,4,16

The second line runs it on Mesa's software rasteriser, where it reaches
the GL backend; a software adapter needs far fewer copies to measure.
"""

from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

from pyguara import native
from pyguara.graphics.pipeline.device import FullscreenShader

COPY = FullscreenShader(
    "copy",
    inputs=("frame",),
    wgsl="""
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    return textureSample(frame, input_sampler, in.uv);
}
""",
)

NOISE = FullscreenShader(
    "noise",
    wgsl="""
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    let p = vec2<u32>(in.position.xy);
    var h = p.x * 1973u + p.y * 9277u;
    h = (h ^ (h >> 13u)) * 1274126177u;
    h = h ^ (h >> 16u);
    let rgb = vec3<f32>(f32(h & 255u), f32((h >> 8u) & 255u), f32((h >> 16u) & 255u));
    return vec4<f32>(rgb / 255.0, 1.0);
}
""",
)

WARM_UP = 20
SIZES = ((1920, 1080), (2560, 1440))


def frame_ms(gpu: Any, copies: int, frames: int) -> float:
    """Median milliseconds for a frame of noise followed by `copies` copies.

    Each frame ends by copying into a 1x1 target and reading it back,
    which waits for the GPU at a cost that does not depend on `copies`.
    """
    noise = gpu.create_effect(NOISE.wgsl_source(), 0, 0)
    copy = gpu.create_effect(COPY.wgsl_source(), 1, COPY.uniform_bytes)
    ping = gpu.create_target(gpu.width, gpu.height, False)
    pong = gpu.create_target(gpu.width, gpu.height, False)
    fence = gpu.create_target(1, 1, False)
    times = []
    for frame in range(WARM_UP + frames):
        start = time.perf_counter()
        gpu.fullscreen(noise, 0, [], b"", 0, None, None)
        source = 0
        for index in range(copies):
            target = ping if index % 2 == 0 else pong
            gpu.fullscreen(copy, target, [source], b"", 0, None, None)
            source = target
        gpu.fullscreen(copy, fence, [source], b"", 0, None, None)
        gpu.end_frame()
        gpu.read_pixels(fence)
        if frame >= WARM_UP:
            times.append(time.perf_counter() - start)
    for target in (ping, pong, fence):
        gpu.destroy_target(target)
    return statistics.median(times) * 1000


def main() -> None:
    """Print each size's frame times and the cost of one copy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--counts", default="0,64,256", help="copies a frame")
    arguments = parser.parse_args()
    counts = [int(count) for count in arguments.counts.split(",")]
    extension: Any = native.require_extension("present_copy_probe")
    for width, height in SIZES:
        gpu = extension.NativeGpu(width, height)
        rows = {count: frame_ms(gpu, count, arguments.frames) for count in counts}
        per_copy = (rows[counts[-1]] - rows[counts[0]]) / (counts[-1] - counts[0])
        times = "  ".join(f"N={count} {ms:.2f} ms" for count, ms in rows.items())
        print(
            f"{gpu.adapter}  {width}x{height}  {times}  -> {per_copy * 1000:.0f} us a copy"
        )
        del gpu


if __name__ == "__main__":
    main()
