"""The render graph's view of the GPU, the same on every backend that has one.

A pass used to be handed a `moderngl.Context` and to drive OpenGL itself:
bind a framebuffer, bind its textures to units, set uniforms by name, draw a
triangle strip. That made the graph an OpenGL graph, and a second backend
could only run it by imitating OpenGL.

What a pass actually does is narrower, and the same everywhere: read some
buffers, run one shader over the whole of another buffer, with a few
uniforms and a blend mode. `GraphicsDevice.run` is that. A pass describes the
work -- a `FullscreenShader`, its inputs by name, its uniform values, where
the result goes -- and the device does it: `ModernGLDevice` with the GLSL
source, `WgpuDevice` with the WGSL one.

**A shader carries both sources until stage E** of
`project/backlog/active/next_engine_plan.md` retires ModernGL, and then only
WGSL. Each is held to the other by rendering the same frame on both and
comparing.

**Texture coordinates differ, and the sources say so.** In GLSL, `v_uv` has
its origin at the bottom left, because a GL framebuffer's first row is the
bottom of the image. In WGSL, `in.uv` has it at the top left, as a wgpu
texture's first row is the top. A shader that only reads at `uv` does not
care; one whose effect has a direction -- rain falling, heat rising, a light
at a screen position -- flips `y` in one of the two.
"""

from __future__ import annotations

import contextlib
import struct
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pyguara.common.types import Color

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.backends.wgpu.frame import GpuFrame
    from pyguara.graphics.pipeline.framebuffer import Framebuffer

Blend = Literal["replace", "alpha", "add"]
"""How a pass combines with what its output already holds.

`alpha` is what every pass on the ModernGL backend has always drawn with,
because the renderer leaves GL blending on and in that mode. `add` is the
light accumulation. `replace` overwrites.
"""

UniformKind = Literal["f32", "i32", "vec2", "vec3", "vec4"]

# WGSL's uniform layout: (alignment, size) in bytes.
_LAYOUT: dict[str, tuple[int, int]] = {
    "f32": (4, 4),
    "i32": (4, 4),
    "vec2": (8, 8),
    "vec3": (16, 12),
    "vec4": (16, 16),
}
_WGSL_TYPE: dict[str, str] = {
    "f32": "f32",
    "i32": "i32",
    "vec2": "vec2<f32>",
    "vec3": "vec3<f32>",
    "vec4": "vec4<f32>",
}
_BLEND_CODE: dict[str, int] = {"replace": 0, "add": 1, "alpha": 2}

_GLSL_DIR = Path(__file__).parent.parent / "backends" / "moderngl" / "shaders"


def glsl(name: str) -> str:
    """Read one of the engine's GLSL fragment shaders by file name."""
    return (_GLSL_DIR / name).read_text()


@dataclass(frozen=True)
class Uniform:
    """One uniform a fullscreen shader takes.

    Attributes:
        name: Its name in both sources: a `uniform` in GLSL, a field of
            `params` in WGSL.
        kind: Its type.
    """

    name: str
    kind: UniformKind = "f32"


@dataclass(frozen=True, eq=False)
class FullscreenShader:
    """A shader run over the whole of a buffer, in both shading languages.

    Compared by identity: a device compiles each one once and keys its
    cache on the object, so make one per effect and keep it, at module
    level for an engine pass.

    Attributes:
        name: For error messages and the cache.
        inputs: The buffers it samples, by the names its sources use -- a
            `uniform sampler2D` in GLSL, a `texture_2d<f32>` in WGSL, which
            the preamble declares, sampled through `input_sampler`.
        uniforms: Its uniforms, in the order WGSL's `Params` lays them out.
        wgsl: A fragment entry point, `@fragment fn fragment(in: Varying)
            -> @location(0) vec4<f32>`, using `in.uv`, `params.<name>` and
            the inputs. The preamble is added by `wgsl_source`.
        glsl: A complete GLSL 330 fragment shader reading `v_uv`, run with
            `fullscreen_quad.vert`.
    """

    name: str
    inputs: tuple[str, ...] = ()
    uniforms: tuple[Uniform, ...] = ()
    wgsl: str | None = None
    glsl: str | None = None
    _layout: tuple[tuple[str, str, int], ...] = field(
        init=False, repr=False, default=()
    )

    def __post_init__(self) -> None:
        """Lay the uniforms out once."""
        offset = 0
        layout = []
        for uniform in self.uniforms:
            align, size = _LAYOUT[uniform.kind]
            offset = (offset + align - 1) // align * align
            layout.append((uniform.name, uniform.kind, offset))
            offset += size
        object.__setattr__(self, "_layout", tuple(layout))

    @property
    def uniform_bytes(self) -> int:
        """Size of WGSL's `Params` struct: rounded to 16, as uniform buffers are."""
        if not self._layout:
            return 0
        _, kind, offset = self._layout[-1]
        end = offset + _LAYOUT[kind][1]
        return (end + 15) // 16 * 16

    def pack(self, values: Mapping[str, Any]) -> bytes:
        """Lay `values` out as WGSL's `Params` struct expects them.

        Args:
            values: A value for every uniform, by name. A vector is any
                sequence of the right length.

        Returns:
            The bytes, `uniform_bytes` long.

        Raises:
            KeyError: If a uniform has no value, naming it.
        """
        out = bytearray(self.uniform_bytes)
        for name, kind, offset in self._layout:
            if name not in values:
                raise KeyError(f"{self.name}: no value for uniform '{name}'")
            value = values[name]
            if kind == "i32":
                struct.pack_into("<i", out, offset, int(value))
            elif kind == "f32":
                struct.pack_into("<f", out, offset, float(value))
            else:
                count = int(kind[-1])
                struct.pack_into(f"<{count}f", out, offset, *(float(v) for v in value))
        return bytes(out)

    def wgsl_source(self) -> str:
        """Assemble the complete WGSL module: preamble, vertex stage and `wgsl`.

        Raises:
            ValueError: If the shader has no WGSL source.
        """
        if self.wgsl is None:
            raise ValueError(f"{self.name} has no WGSL source, so wgpu cannot run it")
        lines = []
        if self._layout:
            fields = ",\n".join(
                f"    {name}: {_WGSL_TYPE[kind]}" for name, kind, _ in self._layout
            )
            lines.append(f"struct Params {{\n{fields},\n}};")
            lines.append("@group(0) @binding(0) var<uniform> params: Params;")
        lines.append("@group(0) @binding(1) var input_sampler: sampler;")
        for index, name in enumerate(self.inputs):
            lines.append(
                f"@group(0) @binding({2 + index}) var {name}: texture_2d<f32>;"
            )
        lines.append(_WGSL_VERTEX)
        lines.append(self.wgsl)
        return "\n".join(lines)


# One triangle that covers the target. `uv` is (0, 0) at the top left and
# (1, 1) at the bottom right, as wgpu addresses a texture.
_WGSL_VERTEX = """
struct Varying {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@vertex
fn vertex(@builtin(vertex_index) index: u32) -> Varying {
    let corner = vec2<f32>(f32((index << 1u) & 2u), f32(index & 2u));
    var out: Varying;
    out.position = vec4<f32>(corner * 2.0 - vec2<f32>(1.0, 1.0), 0.0, 1.0);
    out.uv = vec2<f32>(corner.x, 1.0 - corner.y);
    return out;
}
"""


class GraphicsDevice(ABC):
    """What a render pass needs from the GPU.

    An abstract class rather than a `Protocol`, unusually for this
    codebase, because `RenderGraph` and `FramebufferManager` have to tell a
    device from a bare ModernGL context -- both are accepted until stage E
    -- and a runtime-checkable protocol cannot tell either from the
    `MagicMock` the unit tests hand in.
    """

    @property
    @abstractmethod
    def ctx(self) -> moderngl.Context | None:
        """The ModernGL context, for passes not yet ported; None on wgpu."""

    @abstractmethod
    def create_target(
        self, name: str, width: int, height: int, *, samples: int, dtype: str
    ) -> Framebuffer:
        """Make a buffer to draw into and sample from.

        Args:
            name: Its name in the manager.
            width: Width in pixels.
            height: Height in pixels.
            samples: MSAA samples; only 0 is supported on wgpu.
            dtype: `"f1"` for 8-bit, `"f2"` for 16-bit float.

        Returns:
            The buffer.
        """

    @abstractmethod
    def run(
        self,
        shader: FullscreenShader,
        inputs: Mapping[str, Framebuffer],
        uniforms: Mapping[str, Any],
        output: Framebuffer | None,
        *,
        blend: Blend = "alpha",
        viewport: tuple[int, int, int, int] | None = None,
        clear: Color | None = None,
    ) -> None:
        """Run `shader` over `output`, reading `inputs`.

        Afterwards `output` is where drawing goes, as a bound framebuffer
        stays bound in GL: the game's UI, drawn after the final pass, lands
        on the screen because the final pass wrote there.

        Args:
            shader: What to run.
            inputs: A buffer for each of `shader.inputs`, by name.
            uniforms: A value for each of `shader.uniforms`, by name.
            output: Where to write; None is the screen.
            blend: How to combine with what `output` holds.
            viewport: Restrict to this rectangle of `output`, in GL's
                convention -- `(x, y, width, height)` with `y` up from the
                bottom -- as `RenderGraph.screen_rect` gives it.
            clear: Clear all of `output` to this first.
        """

    def release(self) -> None:
        """Release compiled shaders. Buffers belong to their manager."""


def as_device(ctx_or_device: Any) -> GraphicsDevice:
    """Return a device for what a caller handed the graph or the manager.

    A `GraphicsDevice` is used as it is. Anything else is taken to be a
    ModernGL context, as every caller passed before devices existed, and
    wrapped -- including the `MagicMock` unit tests stand in for one.

    Args:
        ctx_or_device: A device, or a ModernGL context.

    Returns:
        The device.
    """
    if isinstance(ctx_or_device, GraphicsDevice):
        return ctx_or_device
    return ModernGLDevice(ctx_or_device)


class ModernGLDevice(GraphicsDevice):
    """`GraphicsDevice` over a ModernGL context, running the GLSL sources."""

    def __init__(self, ctx: moderngl.Context) -> None:
        """Wrap a context.

        Args:
            ctx: The ModernGL context.
        """
        self._ctx = ctx
        # Keyed on the shader's identity, holding the shader too so the id
        # cannot be reused while its program lives.
        self._programs: dict[int, tuple[FullscreenShader, Any, Any]] = {}

    @property
    def ctx(self) -> moderngl.Context:
        """The ModernGL context."""
        return self._ctx

    def create_target(
        self, name: str, width: int, height: int, *, samples: int, dtype: str
    ) -> Framebuffer:
        """Make a ModernGL framebuffer with a linear-filtered colour texture."""
        from pyguara.graphics.pipeline.framebuffer import Framebuffer

        return Framebuffer(self._ctx, name, width, height, samples=samples, dtype=dtype)

    def _program(self, shader: FullscreenShader) -> tuple[Any, Any]:
        found = self._programs.get(id(shader))
        if found is not None:
            return found[1], found[2]
        if shader.glsl is None:
            raise ValueError(
                f"{shader.name} has no GLSL source, so ModernGL cannot run it"
            )
        program = self._ctx.program(
            vertex_shader=glsl("fullscreen_quad.vert"),
            fragment_shader=shader.glsl,
        )
        vao = self._ctx.vertex_array(program, [])
        self._programs[id(shader)] = (shader, program, vao)
        return program, vao

    def run(
        self,
        shader: FullscreenShader,
        inputs: Mapping[str, Framebuffer],
        uniforms: Mapping[str, Any],
        output: Framebuffer | None,
        *,
        blend: Blend = "alpha",
        viewport: tuple[int, int, int, int] | None = None,
        clear: Color | None = None,
    ) -> None:
        """Bind, set and draw, as the passes did by hand."""
        from pyguara.graphics.backends.moderngl.blend import BlendMode, blending

        program, vao = self._program(shader)
        if output is None:
            screen = self._ctx.screen
            if clear is not None:
                screen.viewport = (0, 0, *screen.size)
                screen.use()
                red, green, blue, alpha = _rgba(clear)
                screen.clear(red / 255, green / 255, blue / 255, alpha / 255)
            if viewport is not None:
                screen.viewport = viewport
            screen.use()
        else:
            output.bind()
            if clear is not None:
                output.clear(clear)
        for unit, name in enumerate(shader.inputs):
            inputs[name].texture.use(unit)
            _set(program, name, unit)
        for uniform in shader.uniforms:
            _set(program, uniform.name, uniforms[uniform.name])
        if blend == "add":
            with blending(self._ctx, BlendMode.ADDITIVE):
                vao.render(mode=self._ctx.TRIANGLE_STRIP, vertices=4)
        elif blend == "replace":
            self._ctx.disable(self._ctx.BLEND)
            try:
                vao.render(mode=self._ctx.TRIANGLE_STRIP, vertices=4)
            finally:
                from pyguara.graphics.backends.moderngl.blend import (
                    DEFAULT_BLEND_MODE,
                    apply_blend_mode,
                )

                apply_blend_mode(self._ctx, DEFAULT_BLEND_MODE)
        else:
            vao.render(mode=self._ctx.TRIANGLE_STRIP, vertices=4)

    def release(self) -> None:
        """Release every compiled program."""
        for _, program, vao in self._programs.values():
            vao.release()
            program.release()
        self._programs.clear()


class WgpuFramebuffer:
    """A buffer in the native wgpu frame, with `Framebuffer`'s interface.

    Bound by naming it as the target pushes go to; read by a fullscreen
    pass by id. It has no `texture` or `fbo` to hand out: a pass that
    reaches for one has not been ported to `GraphicsDevice.run` yet.
    """

    def __init__(
        self, frame: GpuFrame, name: str, width: int, height: int, dtype: str
    ) -> None:
        """Make the target.

        Args:
            frame: The frame it lives in.
            name: Its name in the manager.
            width: Width in pixels.
            height: Height in pixels.
            dtype: `"f1"` or `"f2"`.
        """
        if dtype not in ("f1", "f2"):
            raise ValueError(f"wgpu buffers are 'f1' or 'f2', not {dtype!r}")
        self._gpu = frame.gpu
        self._name = name
        self._width = width
        self._height = height
        self._dtype = dtype
        self.target: int | None = self._gpu.create_target(width, height, dtype == "f2")

    @property
    def name(self) -> str:
        """Identifier for this framebuffer."""
        return self._name

    @property
    def width(self) -> int:
        """Width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Height in pixels."""
        return self._height

    @property
    def samples(self) -> int:
        """Always 0: the wgpu frame does not multisample."""
        return 0

    @property
    def dtype(self) -> str:
        """`"f1"` (8-bit) or `"f2"` (16-bit float)."""
        return self._dtype

    @property
    def texture(self) -> Any:
        """Not available on wgpu; see the class docstring."""
        raise AttributeError(
            f"'{self._name}' is a wgpu buffer: it has no ModernGL texture. A pass "
            f"that reads one has to run through GraphicsDevice.run."
        )

    @property
    def fbo(self) -> Any:
        """Not available on wgpu; see the class docstring."""
        raise AttributeError(f"'{self._name}' is a wgpu buffer: it has no GL FBO.")

    def _id(self) -> int:
        if self.target is None:
            raise RuntimeError(f"Framebuffer '{self._name}' was released")
        return self.target

    def bind(self) -> None:
        """Send drawing here."""
        self._gpu.set_target(self._id())

    def unbind(self) -> None:
        """Send drawing to the screen again."""
        self._gpu.set_target(0)

    def clear(self, color: Color) -> None:
        """Clear to a colour, leaving drawing going where it was going."""
        previous = self._gpu.current_target
        self._gpu.set_target(self._id())
        self._gpu.clear_target(*(channel / 255 for channel in _rgba(color)))
        self._gpu.set_target(previous)

    def resize(self, width: int, height: int) -> None:
        """Give it a new size. Its contents are lost, as in GL."""
        if (width, height) == (self._width, self._height):
            return
        self._gpu.resize_target(self._id(), width, height)
        self._width, self._height = width, height

    def release(self) -> None:
        """Free the target."""
        if self.target is not None:
            self._gpu.destroy_target(self.target)
            self.target = None


class WgpuDevice(GraphicsDevice):
    """`GraphicsDevice` over the native wgpu frame, running the WGSL sources."""

    def __init__(self, frame: GpuFrame) -> None:
        """Draw through a frame.

        Args:
            frame: The frame the renderers and the window share.
        """
        self._frame = frame
        self._gpu = frame.gpu
        self._effects: dict[int, tuple[FullscreenShader, int]] = {}

    @property
    def ctx(self) -> None:
        """No ModernGL context behind this device."""
        return None

    def create_target(
        self, name: str, width: int, height: int, *, samples: int, dtype: str
    ) -> Framebuffer:
        """Make a buffer in the native frame."""
        if samples:
            raise ValueError("the wgpu backend does not multisample its buffers")
        # Same interface; `FramebufferManager` holds either kind.
        buffer: Any = WgpuFramebuffer(self._frame, name, width, height, dtype)
        return buffer  # type: ignore[no-any-return]

    def _effect(self, shader: FullscreenShader) -> int:
        found = self._effects.get(id(shader))
        if found is None:
            effect = self._gpu.create_effect(
                shader.wgsl_source(), len(shader.inputs), shader.uniform_bytes
            )
            found = (shader, effect)
            self._effects[id(shader)] = found
        return found[1]

    def run(
        self,
        shader: FullscreenShader,
        inputs: Mapping[str, Framebuffer],
        uniforms: Mapping[str, Any],
        output: Framebuffer | None,
        *,
        blend: Blend = "alpha",
        viewport: tuple[int, int, int, int] | None = None,
        clear: Color | None = None,
    ) -> None:
        """Queue the pass in the native frame, then draw into `output`."""
        target = 0 if output is None else _target_of(output)
        if viewport is not None:
            # GL's y is up from the bottom; the frame's is down from the top.
            x, y, width, height = viewport
            viewport = (x, self._target_height(output) - y - height, width, height)
        self._gpu.fullscreen(
            self._effect(shader),
            target,
            [_target_of(inputs[name]) for name in shader.inputs],
            shader.pack(uniforms),
            _BLEND_CODE[blend],
            viewport,
            None if clear is None else tuple(c / 255 for c in _rgba(clear)),
        )
        self._gpu.set_target(target)

    def _target_height(self, output: Framebuffer | None) -> int:
        return int(self._gpu.height if output is None else output.height)


def _set(program: Any, name: str, value: Any) -> None:
    """Set a GLSL uniform, if the compiler kept it.

    A uniform the shader declares but never reads is optimised away, and
    ModernGL then raises `KeyError` for it -- not a mistake in the pass.
    """
    with contextlib.suppress(KeyError):
        program[name] = value


def _target_of(buffer: Any) -> int:
    target = getattr(buffer, "target", None)
    if not isinstance(target, int):
        raise TypeError(
            f"{buffer!r} is not a wgpu buffer; make it through this graph's "
            f"FramebufferManager"
        )
    return target


def _rgba(color: Color | Sequence[int]) -> tuple[int, int, int, int]:
    """Return a colour's channels, with alpha 255 when it has none."""
    alpha = int(color[3]) if len(color) > 3 else 255
    return (int(color[0]), int(color[1]), int(color[2]), alpha)
