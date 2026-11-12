"""`BloomEffect`'s passes, in order, against a recording device.

What the bloom *looks* like is held to ModernGL's on wgpu by
`tests/integration/test_wgpu_graph.py`, and its tonemap by
`tests/integration/test_bloom_tonemap_pixels.py`. This is the plumbing:
which shader reads which buffer and writes which, and how many times.

It used to count VAOs -- `apply()` rebuilt all three every frame and
leaked one. A device compiles each shader once and owns it, so there is
no longer anything per-frame for an effect to leak.
"""

from unittest.mock import MagicMock

import pytest

from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.vfx.effects.bloom import BLUR, COMPOSITE, THRESHOLD, BloomEffect
from tests.recording_device import RecordingDevice


@pytest.fixture
def device() -> RecordingDevice:
    return RecordingDevice()


def run_bloom(device: RecordingDevice, blur_passes: int) -> tuple[MagicMock, MagicMock]:
    manager = FramebufferManager(device, 64, 32)
    effect = BloomEffect(manager, threshold=0.7, intensity=1.5, blur_passes=blur_passes)
    source, target = MagicMock(width=64, height=32), MagicMock(width=64, height=32)
    effect.apply(device, source, target)
    return source, target


def test_the_passes_run_in_order(device: RecordingDevice) -> None:
    run_bloom(device, blur_passes=2)

    assert [run.shader for run in device.runs] == [
        THRESHOLD, BLUR, BLUR, BLUR, BLUR, COMPOSITE,
    ]  # fmt: skip


def test_the_blur_ping_pongs_between_its_two_buffers(device: RecordingDevice) -> None:
    source, target = run_bloom(device, blur_passes=1)
    threshold, across, down, composite = device.runs

    bright = threshold.output
    assert threshold.inputs == {"u_texture": source}
    assert across.inputs == {"u_texture": bright}
    assert across.uniforms["u_direction"] == (1.0, 0.0)
    assert down.inputs == {"u_texture": across.output}
    assert down.uniforms["u_direction"] == (0.0, 1.0)
    assert down.output is bright
    assert composite.inputs == {"u_scene": source, "u_bloom": bright}
    assert composite.output is target


def test_the_parameters_reach_the_shaders(device: RecordingDevice) -> None:
    run_bloom(device, blur_passes=1)

    assert device.runs[0].uniforms == {"u_threshold": 0.7}
    assert device.runs[1].uniforms["u_texel_size"] == (1 / 64, 1 / 32)
    assert device.runs[-1].uniforms == {"u_intensity": 1.5}


def test_its_scratch_buffers_are_hdr(device: RecordingDevice) -> None:
    run_bloom(device, blur_passes=1)

    assert device.runs[0].output.dtype == "f2"
    assert device.runs[1].output.dtype == "f2"


def test_release_is_idempotent() -> None:
    """A stack releasing an effect twice must not raise on the second."""
    effect = BloomEffect(MagicMock())

    effect.release()
    effect.release()
