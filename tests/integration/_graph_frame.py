"""Run one render-graph case on one backend and write the result. Run as a script.

    python tests/integration/_graph_frame.py <moderngl|wgpu> <case> <out.rgba>

`test_wgpu_graph.py` runs this once per backend, each in a process of its
own: wgpu's GL backend cannot open a device while a ModernGL context is
current, and the reverse is no better.

A case starts from the same picture on both backends -- written straight
into a buffer, so neither renderer's rasterisation is part of what is
compared -- runs passes over it through `GraphicsDevice`, and writes the
output buffer as RGBA rows **top row first** on both. GL stores its rows
bottom-up, so its side flips the picture on the way in and the result on
the way out; a pass that turned the image upside down would show.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

WIDTH, HEIGHT = 96, 64


def picture() -> bytes:
    """An opaque RGBA image with no symmetry, top row first."""
    rows = []
    for y in range(HEIGHT):
        row = bytearray()
        for x in range(WIDTH):
            red = (x * 255) // (WIDTH - 1)
            green = (y * 255) // (HEIGHT - 1)
            blue = 255 if (x // 12 + y // 8) % 2 else 40
            if x < 20 and y < 12:  # A marker in the top-left corner.
                red, green, blue = 255, 255, 255
            row += bytes((red, green, blue, 255))
        rows.append(bytes(row))
    return b"".join(rows)


def flip(rows: bytes, width: int, height: int) -> bytes:
    """Reverse the row order of a tightly packed RGBA image."""
    stride = width * 4
    return b"".join(
        rows[y * stride : (y + 1) * stride] for y in reversed(range(height))
    )


class Backend:
    """What a case needs from either backend."""

    graph: Any

    def fill(self, buffer: Any, pixels: bytes) -> None:
        """Put a top-row-first RGBA image into a buffer."""
        raise NotImplementedError

    def read(self, buffer: Any) -> bytes:
        """Return a buffer as top-row-first RGBA, once the frame is drawn."""
        raise NotImplementedError


class GL(Backend):
    """ModernGL on a standalone context."""

    def __init__(self) -> None:
        import moderngl

        from pyguara.graphics.backends.moderngl.blend import (
            DEFAULT_BLEND_MODE,
            apply_blend_mode,
        )
        from pyguara.graphics.pipeline.device import ModernGLDevice
        from pyguara.graphics.pipeline.graph import RenderGraph

        self.ctx = moderngl.create_standalone_context()
        # What `ModernGLRenderer` sets up, and every pass runs under.
        apply_blend_mode(self.ctx, DEFAULT_BLEND_MODE)
        self.graph = RenderGraph(ModernGLDevice(self.ctx), WIDTH, HEIGHT)

    def fill(self, buffer: Any, pixels: bytes) -> None:
        buffer.texture.write(flip(pixels, buffer.width, buffer.height))

    def read(self, buffer: Any) -> bytes:
        data = buffer.fbo.read(components=4)
        return flip(data, buffer.width, buffer.height)


class WGPU(Backend):
    """The native wgpu frame, offscreen."""

    def __init__(self) -> None:
        import pygame

        from pyguara.graphics.backends.wgpu import GpuFrame, WgpuRenderer
        from pyguara.graphics.pipeline.device import WgpuDevice
        from pyguara.graphics.pipeline.graph import RenderGraph

        pygame.init()
        pygame.display.set_mode((8, 8))
        self.frame = GpuFrame(WIDTH, HEIGHT)
        self.renderer = WgpuRenderer(self.frame)
        self.graph = RenderGraph(WgpuDevice(self.frame), WIDTH, HEIGHT)
        self._drawn = False

    def fill(self, buffer: Any, pixels: bytes) -> None:
        import pygame

        from pyguara.common.types import Vector2
        from pyguara.graphics.backends.pygame.types import PygameTexture

        image = pygame.image.frombuffer(pixels, (buffer.width, buffer.height), "RGBA")
        buffer.bind()
        # Unscaled and nearest: texel for texel.
        self.renderer.draw_texture(
            PygameTexture("picture", image.copy()),
            Vector2(buffer.width // 2, buffer.height // 2),
        )
        buffer.unbind()

    def read(self, buffer: Any) -> bytes:
        if not self._drawn:
            self.frame.gpu.end_frame()
            self._drawn = True
        return bytes(self.frame.gpu.read_pixels(buffer.target))


def composite(backend: Backend) -> Any:
    """World times a coloured light map, through `CompositePass`."""
    from pyguara.common.types import Color
    from pyguara.graphics.pipeline.passes import CompositePass

    manager = backend.graph.fbo_manager
    world = manager.get_or_create("w", dtype="f1")
    light = manager.get_or_create("l", dtype="f1")
    out = manager.get_or_create("out", dtype="f1")
    backend.fill(world, picture())
    light.clear(Color(128, 200, 255, 255))
    CompositePass(
        world_fbo_name="w", light_fbo_name="l", output_fbo_name="out"
    ).execute(backend.graph.ctx, backend.graph)
    return out


def composite_unlit(backend: Backend) -> Any:
    """With no light map the world is multiplied by itself, as it always was."""
    from pyguara.graphics.pipeline.passes import CompositePass

    manager = backend.graph.fbo_manager
    world = manager.get_or_create("w", dtype="f1")
    out = manager.get_or_create("out", dtype="f1")
    backend.fill(world, picture())
    CompositePass(
        world_fbo_name="w", light_fbo_name="none", output_fbo_name="out"
    ).execute(backend.graph.ctx, backend.graph)
    return out


CASES: dict[str, Callable[[Backend], Any]] = {
    "composite": composite,
    "composite_unlit": composite_unlit,
}


def main() -> None:
    """Run the case named on the command line on the backend named there."""
    backend_name, case, out = sys.argv[1], sys.argv[2], sys.argv[3]
    backend: Backend = GL() if backend_name == "moderngl" else WGPU()
    result = CASES[case](backend)
    Path(out).write_bytes(backend.read(result))


if __name__ == "__main__":
    main()
