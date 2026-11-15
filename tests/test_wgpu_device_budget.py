"""Leaked wgpu devices do not accumulate across tests.

Each `NativeGpu` owns its own wgpu instance, adapter and device, and a driver
can segfault past its cap instead of refusing: Mesa's GL-on-D3D12 under WSLg
does at the tenth live device. Tests that build an application and never
shut it down leave its device alive, inside reference cycles, until a full
garbage collection. Whether ten piled up therefore depended on test order:
the default order passed, while a different one (one xdist worker's share,
replayed serially) aborted inside `WgpuWindow.present()` every time.

`tests/conftest.py` collects garbage after any test that leaves more than
its budget alive. The two tests here run in file order: the first leaks the
way an application left running does, the second checks the next test
starts within budget.
"""

from __future__ import annotations

import gc
from typing import Any

import pytest

from tests.conftest import _LIVE_DEVICE_BUDGET, REQUIRE_GPU

LEAKED = _LIVE_DEVICE_BUDGET + 3


def _device_class() -> Any:
    from pyguara import native

    extension = native.require_extension("this test")
    try:
        extension.NativeGpu(8, 8)
    except RuntimeError as error:
        if REQUIRE_GPU:
            pytest.fail(f"PYGUARA_REQUIRE_GPU is set and no adapter opened: {error}")
        pytest.skip(f"no graphics adapter for wgpu: {error}")
    # No `gc.collect()` here: the last test must see only what the
    # conftest's fixture freed. The probe above is not in a cycle, so
    # refcounting has already dropped it.
    return extension.NativeGpu


def test_the_count_follows_devices_opening_and_closing() -> None:
    device_class = _device_class()
    # Free what earlier tests leaked first, or the collection below frees
    # those as well and the count lands under `before`.
    gc.collect()
    before = device_class.live_devices()

    devices = [device_class(8, 8) for _ in range(3)]
    assert device_class.live_devices() == before + 3

    del devices
    gc.collect()
    assert device_class.live_devices() == before


def test_a_rejected_size_is_never_counted() -> None:
    device_class = _device_class()
    before = device_class.live_devices()

    with pytest.raises(ValueError):
        device_class(0, 8)

    assert device_class.live_devices() == before


class _Cycle:
    """Holds a device inside a reference cycle, as an `Application` does."""

    def __init__(self, device: Any) -> None:
        self.device = device
        self.me = self


def test_leaks_devices_the_way_an_application_left_running_does() -> None:
    device_class = _device_class()
    for _ in range(LEAKED):
        _Cycle(device_class(8, 8))

    # Refcounting cannot free a cycle: these stay alive past this test.
    assert device_class.live_devices() >= LEAKED


def test_the_next_test_starts_within_the_budget() -> None:
    device_class = _device_class()
    # `_device_class` opened and dropped one of its own; nothing else ran.
    assert device_class.live_devices() <= _LIVE_DEVICE_BUDGET
