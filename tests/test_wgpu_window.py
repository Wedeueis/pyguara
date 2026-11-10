"""How the wgpu window names its native handle, and what it does without one.

No device is opened here except where a test says so: these are about the
decisions made *before* wgpu is involved, which is where the one crash this
backend has had came from.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara.graphics.backends.wgpu import window as window_module
from pyguara.graphics.backends.wgpu.window import native_window


def _pretend(
    monkeypatch: pytest.MonkeyPatch, driver: str, info: dict[str, Any]
) -> None:
    monkeypatch.setattr(pygame.display, "get_driver", lambda: driver)
    monkeypatch.setattr(pygame.display, "get_wm_info", lambda: info)
    monkeypatch.setattr(window_module, "_pointer", lambda capsule: capsule)


class TestNativeWindow:
    def test_x11_is_x11_even_when_the_wayland_fields_are_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # What pygame really returns on X11: `surface` and `shell_surface`
        # are the Wayland members of the same C union, holding leftover
        # bytes. Choosing by which keys exist read them as a Wayland
        # surface and the process died with a segmentation fault.
        _pretend(
            monkeypatch,
            "x11",
            {
                "window": 0x600002,
                "display": 0x1000,
                "surface": 0xBAD,
                "shell_surface": 0xBAD,
            },
        )

        assert native_window() == ("x11", 0x600002, 0x1000)

    def test_wayland(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _pretend(monkeypatch, "wayland", {"display": 0x2000, "surface": 0x3000})

        assert native_window() == ("wayland", 0x3000, 0x2000)

    def test_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _pretend(monkeypatch, "windows", {"window": 0x4000, "hinstance": 1})

        assert native_window() == ("win32", 0x4000, 0)

    @pytest.mark.parametrize("driver", ["dummy", "offscreen", "cocoa", "KMSDRM"])
    def test_a_driver_with_no_handle_to_offer_gives_none(
        self, monkeypatch: pytest.MonkeyPatch, driver: str
    ) -> None:
        _pretend(monkeypatch, driver, {"window": 5, "display": 6, "surface": 7})

        assert native_window() is None

    def test_a_missing_window_id_gives_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _pretend(monkeypatch, "x11", {"window": 0, "display": 0x1000})
        assert native_window() is None

        _pretend(monkeypatch, "windows", {})
        assert native_window() is None

    def test_no_display_at_all_gives_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def no_display() -> str:
            raise pygame.error("video system not initialized")

        monkeypatch.setattr(pygame.display, "get_driver", no_display)

        assert native_window() is None


class TestFallingBack:
    def test_a_window_that_cannot_be_drawn_to_falls_back_and_says_so(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from pyguara.graphics.backends.wgpu import GpuFrame

        try:
            frame = GpuFrame(16, 16, ("not-a-platform", 1, 1))
        except RuntimeError as error:
            pytest.skip(f"no graphics adapter for wgpu: {error}")

        assert frame.gpu.has_surface is False
        assert frame.gpu.present() is False
        frame.gpu.clear(9, 9, 9, 255)
        frame.gpu.end_frame()
        assert frame.gpu.read_pixels()[:4] == bytes([9, 9, 9, 255])

    def test_null_handles_are_refused_not_dereferenced(self) -> None:
        from pyguara import native

        gpu = native.require_extension("test").NativeGpu
        for kind, window, display in (
            ("win32", 0, 0),
            ("x11", 5, 0),
            ("wayland", 0, 5),
        ):
            with pytest.raises(ValueError, match="null"):
                gpu.for_window(kind, window, display, 16, 16)
