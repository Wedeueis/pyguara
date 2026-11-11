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


def flip(rows: bytes, width: int, height: int, texel: int = 4) -> bytes:
    """Reverse the row order of a tightly packed image of `texel`-byte pixels."""
    stride = width * texel
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
        """Return a buffer as top-row-first RGBA, once the frame is drawn.

        Bytes for an 8-bit buffer; little-endian half floats for an HDR one.
        """
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
        if buffer.dtype == "f2":
            data = buffer.fbo.read(components=4, dtype="f2")
            return flip(data, buffer.width, buffer.height, texel=8)
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


def _lighting() -> Any:
    """A lit scene: overlapping and HDR point lights, a cone, a sun, ambient."""
    from pyguara.common.components import Transform
    from pyguara.common.types import Color, Vector2
    from pyguara.ecs.manager import EntityManager
    from pyguara.graphics.lighting.components import (
        AmbientLight,
        LightSource,
        LightType,
    )
    from pyguara.graphics.lighting.light_system import LightingSystem

    world = EntityManager()

    def light(x: float, y: float, source: Any) -> None:
        entity = world.create_entity()
        entity.add_component(Transform(position=Vector2(x, y)))
        entity.add_component(source)

    light(28, 30, LightSource(color=Color(255, 80, 40), radius=26.0))
    # Overlaps the first, and at 2.5 needs the HDR map to hold it.
    light(
        44, 36,
        LightSource(color=Color(40, 120, 255), radius=22.0, intensity=2.5, falloff=1.0),
    )  # fmt: skip
    # Aimed down and to the right: upside down, it would point up.
    light(
        70, 18,
        LightSource(
            color=Color(255, 255, 255),
            radius=20.0,
            light_type=LightType.SPOT,
            spot_angle=50.0,
            spot_direction=60.0,
        ),
    )  # fmt: skip
    light(
        84, 52,
        LightSource(
            color=Color(200, 255, 120),
            radius=9.0,
            intensity=0.5,
            light_type=LightType.DIRECTIONAL,
        ),
    )  # fmt: skip
    world.create_entity().add_component(
        AmbientLight(color=Color(30, 40, 60), intensity=0.5)
    )
    lighting = LightingSystem(world)
    lighting.update(0.0)
    return lighting


def lights(backend: Backend) -> Any:
    """The light map `LightPass` draws: additive quads over ambient, in HDR."""
    from pyguara.common.types import Vector2
    from pyguara.graphics.components.camera import Camera2D
    from pyguara.graphics.pipeline.buffers import LIGHT_FBO_NAME
    from pyguara.graphics.pipeline.passes import LightPass
    from pyguara.graphics.pipeline.viewport import Viewport

    camera = Camera2D(WIDTH, HEIGHT)
    camera.position = Vector2(WIDTH / 2, HEIGHT / 2)
    light_pass = LightPass(backend.graph.ctx, _lighting())
    light_pass.set_camera(camera, Viewport(0, 0, WIDTH, HEIGHT))
    light_pass.execute(backend.graph.ctx, backend.graph)
    return backend.graph.fbo_manager.get(LIGHT_FBO_NAME)


def lit(backend: Backend) -> Any:
    """The picture lit by that light map: light, then composite, end to end."""
    from pyguara.graphics.pipeline.passes import CompositePass

    manager = backend.graph.fbo_manager
    world = manager.get_or_create("w", dtype="f1")
    out = manager.get_or_create("out", dtype="f1")
    backend.fill(world, picture())
    lights(backend)
    CompositePass(world_fbo_name="w", output_fbo_name="out").execute(
        backend.graph.ctx, backend.graph
    )
    return out


CASES: dict[str, Callable[[Backend], Any]] = {
    "composite": composite,
    "composite_unlit": composite_unlit,
    "lights": lights,
    "lit": lit,
}
"""Each case returns the buffer to compare: 8-bit as bytes, HDR as floats."""


def main() -> None:
    """Run the case named on the command line on the backend named there."""
    backend_name, case, out = sys.argv[1], sys.argv[2], sys.argv[3]
    backend: Backend = GL() if backend_name == "moderngl" else WGPU()
    result = CASES[case](backend)
    Path(out).write_bytes(backend.read(result))


if __name__ == "__main__":
    main()
