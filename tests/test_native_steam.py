"""The Steam binding, where it can be tested without Steam.

`NativeSteam` loads Valve's `steam_api` at run time; the game ships it and
this repository never does, so CI has no Steam. What is pinned here is that
every way of not having Steam is an error naming which -- and that a failed
start leaves nothing half-open, so the next attempt behaves the same. Steam
itself is exercised by hand on a machine running it (workstream 5b/5e).
"""

from __future__ import annotations

import ctypes.util
import sys

import pytest

from pyguara import native

module = native.native_module()
pytestmark = pytest.mark.skipif(module is None, reason="extension not built")


def test_it_names_steam_api_for_this_platform() -> None:
    expected = {
        "win32": "steam_api64.dll",
        "darwin": "libsteam_api.dylib",
    }.get(sys.platform, "libsteam_api.so")

    assert module.steam_library_name() == expected  # type: ignore[union-attr]


def test_a_missing_library_is_an_error_naming_it_and_can_be_retried() -> None:
    path = "/no/such/dir/" + module.steam_library_name()  # type: ignore[union-attr]
    for _ in range(2):
        with pytest.raises(RuntimeError, match="could not load /no/such/dir/"):
            module.NativeSteam(path)  # type: ignore[union-attr]


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or ctypes.util.find_library("m") is None,
    reason="needs a Linux system library that is not steam_api",
)
def test_a_library_that_is_not_steam_api_is_refused_by_name() -> None:
    with pytest.raises(RuntimeError, match="not a steam_api this engine can use"):
        module.NativeSteam("libm.so.6")  # type: ignore[union-attr]
