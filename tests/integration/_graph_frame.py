"""Run one render-graph case and write the result. Run as a script.

    python tests/integration/_graph_frame.py wgpu <case> <out.rgba>

`test_wgpu_graph.py` holds each case to its golden image. A case starts
from a known picture -- drawn straight into a buffer, so the renderer's
rasterisation is not part of what is compared -- runs passes over it
through `GraphicsDevice`, and writes the output buffer top row first.

The cases were first held to ModernGL's output, pass by pass, which is
what approved the golden images; that backend has since been retired.
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
    ).execute(backend.graph)
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
    ).execute(backend.graph)
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
    light_pass = LightPass(_lighting())
    light_pass.set_camera(camera, Viewport(0, 0, WIDTH, HEIGHT))
    light_pass.execute(backend.graph)
    return backend.graph.fbo_manager.get(LIGHT_FBO_NAME)


def lit(backend: Backend) -> Any:
    """The picture lit by that light map: light, then composite, end to end."""
    from pyguara.graphics.pipeline.passes import CompositePass

    manager = backend.graph.fbo_manager
    world = manager.get_or_create("w", dtype="f1")
    out = manager.get_or_create("out", dtype="f1")
    backend.fill(world, picture())
    lights(backend)
    CompositePass(world_fbo_name="w", output_fbo_name="out").execute(backend.graph)
    return out


def _post_process(backend: Backend, *effects: Any) -> Any:
    """Run the picture through `PostProcessPass` with these effects."""
    from pyguara.graphics.pipeline.passes import PostProcessPass
    from pyguara.graphics.vfx.post_process import PostProcessStack

    manager = backend.graph.fbo_manager
    world = manager.get_or_create("w", dtype="f1")
    backend.fill(world, picture())
    stack = PostProcessStack(manager)
    for effect in effects:
        stack.add_effect(effect)
    PostProcessPass(stack, input_fbo_name="w", output_fbo_name="out").execute(
        backend.graph
    )
    return manager.get("out")


def vignette(backend: Backend) -> Any:
    """Edges darkened, the centre left alone."""
    from pyguara.graphics.vfx.effects import VignetteEffect

    return _post_process(backend, VignetteEffect(intensity=0.7, radius=0.6))


def bloom(backend: Backend) -> Any:
    """Bright areas thresholded, blurred both ways, added back, tonemapped."""
    from pyguara.graphics.vfx.effects import BloomEffect

    effect = BloomEffect(backend.graph.fbo_manager, threshold=0.6, blur_passes=2)
    return _post_process(backend, effect)


def heat_haze(backend: Backend) -> Any:
    """Shimmer, dust and sun: procedural noise, hashed on position."""
    from pyguara.graphics.vfx.effects import HeatHazeEffect

    effect = HeatHazeEffect(haze=6.0, horizon=0.3, dust=0.8, sun=0.5, wind=-0.6)
    effect.update(2.0)
    return _post_process(backend, effect)


def storm(backend: Backend) -> Any:
    """Rain, a forked bolt and a flash."""
    from pyguara.common.random import RandomStream
    from pyguara.graphics.vfx.effects import StormEffect

    effect = StormEffect(rain=0.8, wind=0.25, rng=RandomStream(4))
    effect.update(1.3)
    effect.strike(x=0.4)
    effect.bolt, effect.flash = 1.0, 0.3
    return _post_process(backend, effect)


def chain(backend: Backend) -> Any:
    """Three effects through the stack's ping-pong buffers, then copied out."""
    from games.quintal_cerrado.soil_health_effect import SoilHealthEffect
    from pyguara.graphics.vfx.effects import BloomEffect, VignetteEffect

    return _post_process(
        backend,
        SoilHealthEffect(health=0.2, strength=0.8),
        BloomEffect(backend.graph.fbo_manager, threshold=0.6, blur_passes=1),
        VignetteEffect(),
    )


def passthrough(backend: Backend) -> Any:
    """No effect enabled: the input is copied to the output unchanged."""
    from pyguara.graphics.vfx.effects import VignetteEffect

    return _post_process(backend, VignetteEffect(enabled=False))


def pulse(backend: Backend) -> Any:
    """`mourisco_ressonancia`'s wavefront rings, added over a lit light map."""
    from games.mourisco_ressonancia.pulse_pass import PulsePass, PulseRing
    from pyguara.common.types import Vector2
    from pyguara.graphics.components.camera import Camera2D
    from pyguara.graphics.pipeline.buffers import LIGHT_FBO_NAME
    from pyguara.graphics.pipeline.viewport import Viewport

    lights(backend)
    camera = Camera2D(WIDTH, HEIGHT)
    camera.position = Vector2(WIDTH / 2, HEIGHT / 2)
    rings = PulsePass()
    rings.set_rings(
        [
            PulseRing(Vector2(30, 30), 24.0, (0.4, 0.9, 1.0), 1.5),
            PulseRing(Vector2(60, 40), 14.0, (1.0, 0.5, 0.2), 0.8, thickness=0.2),
            PulseRing(Vector2(80, 16), 6.0, (0.9, 0.9, 0.9), 2.0, thickness=0.02),
        ]
    )
    rings.set_camera(camera, Viewport(0, 0, WIDTH, HEIGHT))
    rings.execute(backend.graph)
    return backend.graph.fbo_manager.get(LIGHT_FBO_NAME)


def _shape_rows() -> dict[str, list[list[float]]]:
    """Rows for every branch of the shape shader, in `ShapeBatch`'s layout.

    Centre, padded half-size, rotation, colour (0-1), stroke, kind.
    """
    import math

    rect, circle, line = 0.0, 1.0, 2.0
    return {
        "rects": [
            [20, 16, 10, 7, 0.0, 1.0, 0.3, 0.2, 1.0, 0.0, rect],
            [50, 18, 12.5, 8.5, 0.5, 0.2, 0.8, 1.0, 1.0, 3.0, rect],
            [78, 46, 9, 9, -0.3, 0.9, 0.9, 0.2, 0.6, 0.0, rect],
        ],
        "circles": [
            [24, 44, 11, 11, 0.0, 0.4, 1.0, 0.5, 1.0, 0.0, circle],
            [52, 46, 9.5, 9.5, 0.0, 1.0, 0.5, 0.9, 1.0, 3.0, circle],
            [70, 20, 3.2, 3.2, 0.0, 1.0, 1.0, 1.0, 0.5, 0.0, circle],
        ],
        "lines": [
            # Off the half-pixel: an edge through pixel centres is a
            # tie-break between GPUs, not a test of the port.
            [48, 32.2, 30 + 1.5, 1.5, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, line],
            [48, 32, 25 + 2.5, 2.5, math.pi / 5, 1.0, 0.6, 0.1, 0.8, 0.0, line],
            [30, 52, 12 + 1, 1, -1.2, 0.3, 0.9, 1.0, 1.0, 0.0, line],
        ],
    }


def shapes(backend: Backend) -> Any:
    """A `ShapeBatch` of each kind, through each backend's own world renderer."""
    from pyguara.common.types import Color
    from pyguara.graphics.types import ShapeBatch, ShapeKind

    manager = backend.graph.fbo_manager
    out = manager.get_or_create("out", dtype="f1")
    out.clear(Color(20, 30, 40, 255))
    rows = _shape_rows()
    batches = [
        ShapeBatch(ShapeKind.RECT, rows["rects"]),
        ShapeBatch(ShapeKind.CIRCLE, rows["circles"]),
        ShapeBatch(ShapeKind.LINE, rows["lines"]),
    ]
    assert isinstance(backend, WGPU)
    out.bind()
    for batch in batches:
        backend.renderer.render_shapes(batch)
    out.unbind()
    return out


CASES: dict[str, Callable[[Backend], Any]] = {
    "shapes": shapes,
    "pulse": pulse,
    "vignette": vignette,
    "bloom": bloom,
    "heat_haze": heat_haze,
    "storm": storm,
    "chain": chain,
    "passthrough": passthrough,
    "composite": composite,
    "composite_unlit": composite_unlit,
    "lights": lights,
    "lit": lit,
}
"""Each case returns the buffer to compare: 8-bit as bytes, HDR as floats."""


def main() -> None:
    """Run the case named on the command line on the backend named there."""
    backend_name, case, out = sys.argv[1], sys.argv[2], sys.argv[3]
    if backend_name != "wgpu":
        raise SystemExit(f"unknown backend {backend_name!r}: wgpu is the one")
    backend: Backend = WGPU()
    result = CASES[case](backend)
    Path(out).write_bytes(backend.read(result))


if __name__ == "__main__":
    main()
