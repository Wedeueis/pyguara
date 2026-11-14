"""The render graph's view of the GPU.

What a pass does is narrow: read some buffers, run one shader over the
whole of another buffer -- or many instanced quads into it -- with a few
uniforms and a blend mode. `GraphicsDevice.run` and `draw_instanced` are
that. A pass describes the work -- a `FullscreenShader` or an
`InstancedShader`, its inputs by name, its uniform values, where the result
goes -- and the device does it. `WgpuDevice` is the device: the native wgpu
frame.

Shaders are WGSL. A pass used to carry a GLSL twin of each, for the ModernGL
backend, until stage E of `project/backlog/active/next_engine_plan.md`
retired it. Two that draw procedural noise -- the heat haze and the storm --
are still written in GL's coordinate convention, `v_uv` with y up, because
that is what their noise was approved against; every other shader uses
wgpu's, `in.uv` with (0, 0) at the top left.
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pyguara.common.types import Color

if TYPE_CHECKING:
    from pyguara.graphics.backends.wgpu.frame import GpuFrame
    from pyguara.graphics.pipeline.framebuffer import Framebuffer

Blend = Literal["replace", "alpha", "add"]
"""How a pass combines with what its output already holds.

`alpha` is what the passes draw with: straight-alpha blending, as every
pass was approved with against ModernGL. `add` is the light accumulation.
`replace` overwrites.
"""

UniformKind = Literal["f32", "i32", "vec2", "vec3", "vec4", "mat4"]

# WGSL's uniform layout: (alignment, size) in bytes.
_LAYOUT: dict[str, tuple[int, int]] = {
    "f32": (4, 4),
    "i32": (4, 4),
    "vec2": (8, 8),
    "vec3": (16, 12),
    "vec4": (16, 16),
    "mat4": (16, 64),
}
_WGSL_TYPE: dict[str, str] = {
    "f32": "f32",
    "i32": "i32",
    "vec2": "vec2<f32>",
    "vec3": "vec3<f32>",
    "vec4": "vec4<f32>",
    "mat4": "mat4x4<f32>",
}
# Floats in a per-instance attribute.
_ATTRIBUTE_FLOATS: dict[str, int] = {"f32": 1, "vec2": 2, "vec3": 3, "vec4": 4}

_Layout = tuple[tuple[str, str, int], ...]


def _lay_out(uniforms: Sequence[Uniform]) -> _Layout:
    """Place each uniform at its WGSL offset."""
    offset = 0
    layout = []
    for uniform in uniforms:
        align, size = _LAYOUT[uniform.kind]
        offset = (offset + align - 1) // align * align
        layout.append((uniform.name, uniform.kind, offset))
        offset += size
    return tuple(layout)


def _layout_bytes(layout: _Layout) -> int:
    """Size of a `Params` struct: rounded to 16, as uniform buffers are."""
    if not layout:
        return 0
    _, kind, offset = layout[-1]
    return (offset + _LAYOUT[kind][1] + 15) // 16 * 16


def _pack(shader: str, layout: _Layout, values: Mapping[str, Any]) -> bytes:
    """Lay `values` out as a `Params` struct; see `FullscreenShader.pack`."""
    out = bytearray(_layout_bytes(layout))
    for name, kind, offset in layout:
        if name not in values:
            raise KeyError(f"{shader}: no value for uniform '{name}'")
        value = values[name]
        if kind == "i32":
            struct.pack_into("<i", out, offset, int(value))
        elif kind == "f32":
            struct.pack_into("<f", out, offset, float(value))
        else:
            count = 16 if kind == "mat4" else int(kind[-1])
            floats = [float(v) for v in value]
            if len(floats) != count:
                raise ValueError(
                    f"{shader}: uniform '{name}' is {count} floats, got {len(floats)}"
                )
            struct.pack_into(f"<{count}f", out, offset, *floats)
    return bytes(out)


def _params_preamble(layout: _Layout, group: int = 0) -> list[str]:
    """Declare the `Params` struct and its binding, if there are uniforms."""
    if not layout:
        return []
    fields = ",\n".join(f"    {name}: {_WGSL_TYPE[kind]}" for name, kind, _ in layout)
    return [
        f"struct Params {{\n{fields},\n}};",
        f"@group({group}) @binding(0) var<uniform> params: Params;",
    ]


_BLEND_CODE: dict[str, int] = {"replace": 0, "add": 1, "alpha": 2}


@dataclass(frozen=True)
class Uniform:
    """One uniform a fullscreen shader takes.

    Attributes:
        name: Its name: a field of `params` in WGSL.
        kind: Its type. A `mat4` is sixteen floats, column by column, as
            GL and WGSL both store one.
    """

    name: str
    kind: UniformKind = "f32"


@dataclass(frozen=True)
class Attribute:
    """One per-instance value an `InstancedShader` reads.

    Attributes:
        name: A field of `Instance` in WGSL.
        kind: `f32`, `vec2`, `vec3` or `vec4`.
    """

    name: str
    kind: UniformKind = "f32"

    def __post_init__(self) -> None:
        """Refuse a kind that cannot be a vertex attribute."""
        if self.kind not in _ATTRIBUTE_FLOATS:
            raise ValueError(f"attribute '{self.name}' cannot be a {self.kind}")


@dataclass(frozen=True, eq=False)
class FullscreenShader:
    """A shader run over the whole of a buffer.

    Compared by identity: a device compiles each one once and keys its
    cache on the object, so make one per effect and keep it, at module
    level for an engine pass.

    Attributes:
        name: For error messages and the cache.
        inputs: The buffers it samples, by the names its sources use -- a
            `texture_2d<f32>` the preamble declares, sampled through
            `input_sampler`.
        uniforms: Its uniforms, in the order WGSL's `Params` lays them out.
        wgsl: A fragment entry point, `@fragment fn fragment(in: Varying)
            -> @location(0) vec4<f32>`, using `in.uv`, `params.<name>` and
            the inputs. The preamble is added by `wgsl_source`.
    """

    name: str
    inputs: tuple[str, ...] = ()
    uniforms: tuple[Uniform, ...] = ()
    wgsl: str | None = None
    _layout: tuple[tuple[str, str, int], ...] = field(
        init=False, repr=False, default=()
    )

    def __post_init__(self) -> None:
        """Lay the uniforms out once."""
        object.__setattr__(self, "_layout", _lay_out(self.uniforms))

    @property
    def uniform_bytes(self) -> int:
        """Size of WGSL's `Params` struct: rounded to 16, as uniform buffers are."""
        return _layout_bytes(self._layout)

    def pack(self, values: Mapping[str, Any]) -> bytes:
        """Lay `values` out as WGSL's `Params` struct expects them.

        Args:
            values: A value for every uniform, by name. A vector is any
                sequence of the right length.

        Returns:
            The bytes, `uniform_bytes` long.

        Raises:
            KeyError: If a uniform has no value, naming it.
            ValueError: If a vector or matrix has the wrong number of floats.
        """
        return _pack(self.name, self._layout, values)

    def wgsl_source(self) -> str:
        """Assemble the complete WGSL module: preamble, vertex stage and `wgsl`.

        Raises:
            ValueError: If the shader has no WGSL source.
        """
        if self.wgsl is None:
            raise ValueError(f"{self.name} has no WGSL source, so wgpu cannot run it")
        lines = _params_preamble(self._layout)
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


@dataclass(frozen=True, eq=False)
class InstancedShader:
    """Many quads, one per instance, each placed and shaded by the shader.

    What a light pass is: a quad per light, sized by its radius, additively
    blended. Compared by identity, like `FullscreenShader`.

    Attributes:
        name: For error messages and the cache.
        attributes: The per-instance values, in the order a row packs them.
        uniforms: Its uniforms, as for `FullscreenShader`.
        wgsl: A `vertex` entry point taking `@builtin(vertex_index)` and an
            `Instance`, and a `fragment` one; the preamble declares
            `Params`, `Instance` and `quad_corner(index)`, which gives the
            six corners of a unit quad centred on the origin, two triangles.
    """

    name: str
    attributes: tuple[Attribute, ...]
    uniforms: tuple[Uniform, ...] = ()
    wgsl: str | None = None
    _layout: _Layout = field(init=False, repr=False, default=())

    def __post_init__(self) -> None:
        """Lay the uniforms out once."""
        object.__setattr__(self, "_layout", _lay_out(self.uniforms))

    @property
    def uniform_bytes(self) -> int:
        """Size of WGSL's `Params` struct."""
        return _layout_bytes(self._layout)

    @property
    def floats(self) -> tuple[int, ...]:
        """How many floats each attribute is."""
        return tuple(_ATTRIBUTE_FLOATS[a.kind] for a in self.attributes)

    @property
    def stride(self) -> int:
        """Bytes in one row of instance data."""
        return 4 * sum(self.floats)

    def pack(self, values: Mapping[str, Any]) -> bytes:
        """Lay the uniforms out; see `FullscreenShader.pack`."""
        return _pack(self.name, self._layout, values)

    def wgsl_source(self) -> str:
        """Assemble the complete WGSL module: preamble and `wgsl`.

        Raises:
            ValueError: If the shader has no WGSL source.
        """
        if self.wgsl is None:
            raise ValueError(f"{self.name} has no WGSL source, so wgpu cannot run it")
        lines = _params_preamble(self._layout)
        fields = ",\n".join(
            f"    @location({index}) {a.name}: {_WGSL_TYPE[a.kind]}"
            for index, a in enumerate(self.attributes)
        )
        lines.append(f"struct Instance {{\n{fields},\n}};")
        lines.append(_WGSL_QUAD)
        lines.append(self.wgsl)
        return "\n".join(lines)


# The unit quad as two triangles.
_WGSL_QUAD = """
fn quad_corner(index: u32) -> vec2<f32> {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-0.5, -0.5), vec2<f32>(0.5, -0.5), vec2<f32>(0.5, 0.5),
        vec2<f32>(-0.5, -0.5), vec2<f32>(0.5, 0.5), vec2<f32>(-0.5, 0.5),
    );
    return corners[index];
}
"""


@dataclass(frozen=True, eq=False)
class SpriteShader:
    """A sprite's own shader: what a `Material` runs in place of the default.

    The author writes one WGSL function, and the engine does the rest: the
    vertex stage is the sprite pipeline's own, so a material sprite is
    placed, sized, turned, flipped and batched exactly as any other.

    ```wgsl
    fn material(sprite: Sprite) -> vec4<f32> {
        let texel = textureSample(sprite_texture, sprite_sampler, sprite.uv);
        return vec4<f32>(mix(texel.rgb, params.flash, params.amount), texel.a) * sprite.color;
    }
    ```

    In scope: `sprite.uv` (the texture coordinate, atlas region and flips
    applied), `sprite.color` (the tint, 0-1 -- a plain sprite is `texel *
    color`), `sprite_texture` and `sprite_sampler`, `params.<name>` for
    each uniform, and `material_texture` / `material_sampler` when
    `texture` is set -- a mask, a ramp, a noise field, from
    `Material.texture`.

    Compared by identity, like the other shaders: make one per kind of
    material, at module level, and share it between materials.

    Attributes:
        name: For error messages and the cache.
        uniforms: Values a `Material` supplies, by name.
        texture: Whether it samples a second texture.
        wgsl: The `material` function and anything it calls.
    """

    name: str
    uniforms: tuple[Uniform, ...] = ()
    texture: bool = False
    wgsl: str | None = None
    _layout: _Layout = field(init=False, repr=False, default=())

    def __post_init__(self) -> None:
        """Lay the uniforms out once."""
        object.__setattr__(self, "_layout", _lay_out(self.uniforms))

    @property
    def uniform_bytes(self) -> int:
        """Size of WGSL's `Params` struct."""
        return _layout_bytes(self._layout)

    def pack(self, values: Mapping[str, Any]) -> bytes:
        """Lay the uniforms out; see `FullscreenShader.pack`."""
        return _pack(self.name, self._layout, values)

    def wgsl_source(self) -> str:
        """Assemble the author's part of the module: bindings and `wgsl`.

        The vertex stage, the sprite texture and the entry point that calls
        `material` are added natively, by `NativeGpu.create_material`.

        Raises:
            ValueError: If the shader has no WGSL source.
        """
        if self.wgsl is None:
            raise ValueError(f"{self.name} has no WGSL source, so wgpu cannot run it")
        lines = _params_preamble(self._layout, group=2)
        if self.texture:
            lines.append("@group(2) @binding(1) var material_texture: texture_2d<f32>;")
            lines.append("@group(2) @binding(2) var material_sampler: sampler;")
        lines.append(self.wgsl)
        return "\n".join(lines)


class GraphicsDevice(ABC):
    """What a render pass needs from the GPU.

    `WgpuDevice` is the engine's; `tests/recording_device.py` records calls
    for unit tests of a pass's plumbing.
    """

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
        stays bound: the game's UI, drawn after the final pass, lands
        on the screen because the final pass wrote there.

        Args:
            shader: What to run.
            inputs: A buffer for each of `shader.inputs`, by name.
            uniforms: A value for each of `shader.uniforms`, by name.
            output: Where to write; None is the screen.
            blend: How to combine with what `output` holds.
            viewport: Restrict to this rectangle of `output`, as
                `RenderGraph.screen_rect` gives it: `(x, y, width, height)`
                with `y` measured up from the bottom.
            clear: Clear all of `output` to this first.
        """

    @abstractmethod
    def draw_instanced(
        self,
        shader: InstancedShader,
        data: bytes,
        count: int,
        uniforms: Mapping[str, Any],
        output: Framebuffer,
        *,
        blend: Blend = "alpha",
    ) -> None:
        """Draw `count` quads into `output`, one per row of `data`.

        Afterwards `output` is where drawing goes, as for `run`.

        Args:
            shader: What to draw them with.
            data: `count` rows of `shader.stride` bytes: each attribute's
                floats, little-endian, in order.
            count: How many.
            uniforms: A value for each of `shader.uniforms`, by name.
            output: Where to draw.
            blend: How to combine with what `output` holds.
        """

    @abstractmethod
    def clear(
        self, buffer: Framebuffer, rgba: tuple[float, float, float, float]
    ) -> None:
        """Clear a buffer to a colour given in floats, which may exceed 1.0.

        `Framebuffer.clear` takes 0-255 channels, which cannot say "1.4"
        to an HDR buffer; an ambient light can.

        Args:
            buffer: The buffer.
            rgba: Red, green, blue and alpha.
        """

    def resize_screen(self, width: int, height: int) -> None:
        """Make the screen the window's size.

        A no-op for a device whose screen follows the window by itself.

        Args:
            width: The window's width in pixels.
            height: The window's height in pixels.
        """

    def release(self) -> None:
        """Release compiled shaders. Buffers belong to their manager."""


class WgpuFramebuffer:
    """A buffer in the native wgpu frame, with `Framebuffer`'s interface.

    Bound by naming it as the target pushes go to; read by a pass by id.
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
        self.clear_rgba(tuple(channel / 255 for channel in _rgba(color)))

    def clear_rgba(self, rgba: tuple[float, ...]) -> None:
        """Clear to a colour in floats, which may exceed 1.0 in an HDR buffer."""
        previous = self._gpu.current_target
        self._gpu.set_target(self._id())
        self._gpu.clear_target(*rgba)
        self._gpu.set_target(previous)

    def resize(self, width: int, height: int) -> None:
        """Give it a new size. Its contents are lost."""
        if (width, height) == (self._width, self._height):
            return
        self._gpu.resize_target(self._id(), width, height)
        self._width, self._height = width, height

    def read_rgba(self) -> bytes:
        """Read the buffer back as 8-bit RGBA, top row first.

        For capture and inspection, after the frame is drawn. An HDR buffer
        is clipped to 0-1 on the way, as the screen would show it.
        """
        raw = bytes(self._gpu.read_pixels(self._id()))
        if self._dtype != "f2":
            return raw
        import numpy as np

        floats = np.frombuffer(raw, dtype="<f2").astype(np.float32)
        return (np.clip(floats, 0.0, 1.0) * 255 + 0.5).astype(np.uint8).tobytes()

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
        self._effects: dict[int, tuple[FullscreenShader | InstancedShader, int]] = {}

    @property
    def frame(self) -> GpuFrame:
        """The native frame, for what draws outside the graph: the editor."""
        return self._frame

    def resize_screen(self, width: int, height: int) -> None:
        """Give the main target -- the window -- the window's size."""
        if (width, height) != (self._gpu.width, self._gpu.height):
            self._gpu.resize(width, height)

    def create_target(
        self, name: str, width: int, height: int, *, samples: int, dtype: str
    ) -> Framebuffer:
        """Make a buffer in the native frame."""
        if samples:
            raise ValueError("the wgpu backend does not multisample its buffers")
        # Same interface; `FramebufferManager` holds either kind.
        buffer: Any = WgpuFramebuffer(self._frame, name, width, height, dtype)
        return buffer  # type: ignore[no-any-return]

    def _effect(self, shader: FullscreenShader | InstancedShader) -> int:
        found = self._effects.get(id(shader))
        if found is None:
            if isinstance(shader, InstancedShader):
                effect = self._gpu.create_effect(
                    shader.wgsl_source(), 0, shader.uniform_bytes, list(shader.floats)
                )
            else:
                effect = self._gpu.create_effect(
                    shader.wgsl_source(), len(shader.inputs), shader.uniform_bytes
                )
            found = (shader, effect)
            self._effects[id(shader)] = found
        return found[1]

    def draw_instanced(
        self,
        shader: InstancedShader,
        data: bytes,
        count: int,
        uniforms: Mapping[str, Any],
        output: Framebuffer,
        *,
        blend: Blend = "alpha",
    ) -> None:
        """Queue the quads in the native frame, then draw into `output`."""
        target = _target_of(output)
        self._gpu.instanced(
            self._effect(shader),
            target,
            data,
            count,
            shader.pack(uniforms),
            _BLEND_CODE[blend],
        )
        self._gpu.set_target(target)

    def clear(
        self, buffer: Framebuffer, rgba: tuple[float, float, float, float]
    ) -> None:
        """Clear a buffer in the native frame, in floats."""
        target: Any = buffer
        target.clear_rgba(rgba)

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
            # `screen_rect`'s y is up from the bottom; the frame's is down from
            # the top.
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
