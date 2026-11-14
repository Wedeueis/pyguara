"""The mixer's Linux device: ALSA, loaded when a mixer opens one, never linked.

Linked, `libasound.so.2` was a load-time dependency of the whole extension,
and on a machine without it -- `python:3.12-slim`, a server -- importing
`pyguara.pyguara_core_rs` failed and took every native store with it. These
pin that it stays unlinked, that the device path works where ALSA is, and
that ALSA's own stderr noise does not leak while a device is refused.

ALSA's `null` device takes samples with no card, so the path from `dlopen`
to `snd_pcm_writei` runs here without one. It does not pace like a card, so
nothing below times playback against the wall.
"""

from __future__ import annotations

import ctypes.util
import shutil
import subprocess
import sys
import time

import pytest

from pyguara import native

module = native.native_module()
pytestmark = [
    pytest.mark.skipif(module is None, reason="extension not built"),
    pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only"),
]
needs_alsa = pytest.mark.skipif(
    ctypes.util.find_library("asound") is None, reason="ALSA is not installed"
)


def _clip(mixer: object) -> object:
    pcm = b"".join(
        (600 * (i % 50) - 15000).to_bytes(2, "little", signed=True) for i in range(4410)
    )
    return mixer.clip(pcm, 44100, 1)  # type: ignore[attr-defined]


@pytest.mark.skipif(shutil.which("readelf") is None, reason="needs readelf")
def test_the_extension_does_not_link_alsa() -> None:
    assert module is not None
    dynamic = subprocess.run(
        ["readelf", "-d", module.__file__],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    needed = [line for line in dynamic.splitlines() if "(NEEDED)" in line]
    assert needed, "readelf listed no dependencies at all"
    assert not any("libasound" in line for line in needed), needed


@needs_alsa
def test_a_device_opens_plays_and_closes_through_alsa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYGUARA_ALSA_DEVICE", "null")
    mixer = module.NativeMixer(output="device")  # type: ignore[union-attr]
    try:
        assert mixer.output == "device: ALSA null"
        assert mixer.rate == 48000
        voice = mixer.play(_clip(mixer), 1.0, 1.0)
        deadline = time.perf_counter() + 2.0
        while mixer.is_playing(voice) and time.perf_counter() < deadline:
            time.sleep(0.005)
        assert not mixer.is_playing(voice), "the writer never consumed the voice"
    finally:
        started = time.perf_counter()
        mixer.close()
    assert time.perf_counter() - started < 1.0, "closing waited on the writer"


@needs_alsa
def test_a_refused_device_is_silent_and_says_why_quietly(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PYGUARA_ALSA_DEVICE", "pyguara_no_such_device")
    mixer = module.NativeMixer(output="device")  # type: ignore[union-attr]
    try:
        assert mixer.output.startswith(
            'silent: ALSA could not open "pyguara_no_such_device"'
        ), mixer.output
    finally:
        mixer.close()
    assert "ALSA lib" not in capfd.readouterr().err
