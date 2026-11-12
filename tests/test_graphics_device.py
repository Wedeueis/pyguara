"""`FullscreenShader` and the device plumbing that needs no GPU."""

from __future__ import annotations

import struct

import pytest

from pyguara.graphics.pipeline.device import (
    FullscreenShader,
    Uniform,
)
from pyguara.graphics.pipeline.graph import RenderGraph


class TestUniformLayout:
    """`pack` must lay values out exactly as WGSL's uniform rules place them.

    Get one offset wrong and the shader reads the wrong number with nothing
    to say so -- the class of mistake this exists to rule out.
    """

    def test_a_vec3_starts_on_16_and_a_float_may_fill_its_tail(self) -> None:
        shader = FullscreenShader(
            "s",
            uniforms=(
                Uniform("a", "f32"),
                Uniform("colour", "vec3"),
                Uniform("b", "f32"),
                Uniform("offset", "vec2"),
            ),
        )

        packed = shader.pack({"a": 1, "colour": (2, 3, 4), "b": 5, "offset": (6, 7)})

        # a@0, colour@16 (vec3 aligns to 16), b@28 (in colour's tail),
        # offset@32 (vec2 aligns to 8); 40 bytes, rounded up to 48.
        assert shader.uniform_bytes == 48
        assert struct.unpack_from("<f", packed, 0) == (1.0,)
        assert struct.unpack_from("<3f", packed, 16) == (2.0, 3.0, 4.0)
        assert struct.unpack_from("<f", packed, 28) == (5.0,)
        assert struct.unpack_from("<2f", packed, 32) == (6.0, 7.0)

    def test_an_integer_is_packed_as_one(self) -> None:
        shader = FullscreenShader("s", uniforms=(Uniform("count", "i32"),))

        assert struct.unpack_from("<i", shader.pack({"count": 3}), 0) == (3,)

    def test_no_uniforms_is_no_bytes(self) -> None:
        shader = FullscreenShader("s")

        assert shader.uniform_bytes == 0
        assert shader.pack({}) == b""

    def test_a_missing_value_names_the_uniform(self) -> None:
        shader = FullscreenShader("glow", uniforms=(Uniform("strength"),))

        with pytest.raises(KeyError, match="glow: no value for uniform 'strength'"):
            shader.pack({})


class TestWgslSource:
    def test_the_preamble_declares_what_the_shader_uses(self) -> None:
        shader = FullscreenShader(
            "s",
            inputs=("u_world", "u_lightmap"),
            uniforms=(Uniform("tint", "vec4"),),
            wgsl="@fragment fn fragment(in: Varying) -> @location(0) vec4<f32> "
            "{ return params.tint; }",
        )

        source = shader.wgsl_source()

        assert "tint: vec4<f32>" in source
        assert "@group(0) @binding(0) var<uniform> params: Params;" in source
        assert "@group(0) @binding(1) var input_sampler: sampler;" in source
        assert "@group(0) @binding(2) var u_world: texture_2d<f32>;" in source
        assert "@group(0) @binding(3) var u_lightmap: texture_2d<f32>;" in source

    def test_no_uniforms_declares_no_buffer(self) -> None:
        source = FullscreenShader("s", wgsl="").wgsl_source()

        assert "var<uniform>" not in source

    def test_a_shader_without_wgsl_says_so(self) -> None:
        with pytest.raises(ValueError, match="blur has no WGSL source"):
            FullscreenShader("blur").wgsl_source()


class TestDevices:
    def test_the_graph_and_its_manager_share_one_device(self) -> None:
        from tests.recording_device import RecordingDevice

        device = RecordingDevice()
        graph = RenderGraph(device, 64, 48)

        assert graph.fbo_manager.device is graph.device is device
