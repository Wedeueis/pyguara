"""Optional native acceleration, and how the engine decides to use it.

RFC-0003's Marco 3 moves the particle, spark and projectile pools into a
compiled extension. This is the seam that makes it *optional*: the module
is used when it is present and the pure-Python implementation runs when it
is not, so `uv sync` and `pip install pyguara` keep working with no Rust
toolchain and the engine stays installable as pure Python.

The cost of that choice is two implementations to keep in agreement, which
is paid by running the same tests against both -- see
`tests/test_native_particle_parity.py`.

Building it:

    cargo build --release

The crate is deliberately not wired into `pyproject.toml`'s build-system.
A note for whoever does wire it up: `maturin build` reads the project name
from `pyproject.toml` and emits a wheel called `pyguara-<version>`, which
would overwrite the real package. Set `module-name` first.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

_ENV_DISABLE = "PYGUARA_NO_NATIVE"

_module: Any | None = None
_looked = False


def _candidate_paths() -> list[Path]:
    """Where the compiled library might be, most-installed first."""
    root = Path(__file__).resolve().parents[3]
    return [
        root / "target" / "release" / "libpyguara_core_rs.so",
        root / "target" / "release" / "pyguara_core_rs.so",
        root / "target" / "debug" / "libpyguara_core_rs.so",
    ]


def native_module() -> Any | None:
    """Return the native extension, or None when it is unavailable.

    Looked up once and cached, including the failure: an engine that has
    decided it is running pure Python should not pay a filesystem probe per
    `ParticleSystem` constructed.

    Tried in two ways. An installed `pyguara_core_rs` on `sys.path` wins,
    which is what a packaged build would provide. Failing that, a library
    built in place by `cargo build` is loaded from `target/`, which is what
    a contributor gets without a packaging step.

    Set `PYGUARA_NO_NATIVE=1` to force the Python path -- used by the
    parity tests, and the first thing to try when a bug might be the
    accelerator's.

    Returns:
        The module, or None.
    """
    global _module, _looked
    if _looked:
        return _module
    _looked = True

    if os.environ.get(_ENV_DISABLE):
        return None

    try:  # a packaged install
        import pyguara_core_rs  # type: ignore[import-not-found]

        _module = pyguara_core_rs
        return _module
    except ImportError:
        pass

    for library in _candidate_paths():  # a local `cargo build`
        if not library.exists():
            continue
        spec = importlib.util.spec_from_file_location("pyguara_core_rs", library)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:  # noqa: BLE001 - a stale or mismatched build
            continue
        sys.modules.setdefault("pyguara_core_rs", module)
        _module = module
        return _module

    return None


def reset_for_tests() -> None:
    """Forget the cached lookup, so a test can change the environment."""
    global _module, _looked
    _module = None
    _looked = False
