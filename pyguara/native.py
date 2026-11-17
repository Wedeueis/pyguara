"""The compiled extension, found once and required.

Every backend subsystem the engine ships is implemented in the extension
and has no Python counterpart, so there is no store to choose: an engine
that cannot load it stops at bootstrap and says why. See ADR 0011.

This module imports nothing from `pyguara` but the extension itself,
so it can be consulted from anywhere, including before bootstrap.

Building the extension is covered in `AGENTS.md` and
`docs/adr/0006-shipping-the-native-extension.md`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# The importable name of the extension. A mixed python/rust wheel requires
# the module to sit under the Python package, so it is dotted rather than
# top-level -- see `[tool.maturin]` in `pyproject.toml`. Spelled once here
# because it is also what the error messages quote and what the `target/`
# fallback registers in `sys.modules`.
_MODULE_NAME = "pyguara.pyguara_core_rs"

STORE_NAME = "native"
"""What a replay records as the store it was made with.

There is one. A replay recorded before the Python stores were retired
may say `"python"`; see `Application`'s playback check.
"""

_module: Any | None = None
_looked = False
_source: str | None = None


def _repository_root() -> Path:
    """Return the checkout this module was imported from.

    One level up from `pyguara/`. A wrong root finds no library and the
    engine falls back to Python without an error, so this is derived from
    the module's own path.
    """
    return Path(__file__).resolve().parents[1]


def _candidate_paths() -> list[Path]:
    """Where the compiled library might be, most-installed first.

    Only `cargo build` leaves a library at these paths. A maturin build
    *relocates* cargo's artifact to `target/maturin/`, so `target/release`
    is empty afterwards -- which is correct rather than a gap, because a
    maturin build either installed the extension (`maturin develop`, where
    the import above answers) or produced a wheel (`maturin build`, where
    nothing in the checkout should answer). `cargo build --release`
    re-creates it.
    """
    root = _repository_root()
    return [
        root / "target" / "release" / "libpyguara_core_rs.so",
        root / "target" / "release" / "pyguara_core_rs.so",
        root / "target" / "debug" / "libpyguara_core_rs.so",
    ]


def native_module() -> Any | None:
    """Return the native extension, or None when it cannot be loaded.

    Looked up once and cached, including the failure. An installed
    `pyguara.pyguara_core_rs` wins; failing that, a library built in place
    by `cargo build` is loaded from `target/`. Code that needs the
    extension calls `require_extension` instead, which names what is
    missing.

    Returns:
        The module, or None.
    """
    global _module, _looked, _source
    if _looked:
        return _module
    _looked = True

    # `import_module` rather than `from pyguara import pyguara_core_rs`,
    # because a successful import sets the submodule as an *attribute* of
    # the package: the `from` form would then answer from that attribute
    # and never consult `sys.modules`, which is exactly what the absence
    # tests patch. `import_module` checks `sys.modules` first and raises
    # on a None entry there.
    try:  # the wheel's extension, or one `uv sync` built
        installed = importlib.import_module(_MODULE_NAME)
    except ImportError:
        installed = None

    if installed is not None:
        _module = installed
        _source = getattr(installed, "__file__", None) or _MODULE_NAME
        return _module

    for library in _candidate_paths():  # a local `cargo build`
        if not library.exists():
            continue
        spec = importlib.util.spec_from_file_location(_MODULE_NAME, library)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:  # noqa: BLE001 - a stale or mismatched build
            continue
        sys.modules.setdefault(_MODULE_NAME, module)
        _module = module
        _source = str(library)
        return _module

    return None


def require_extension(needed_by: str) -> Any:
    """Return the extension, or raise naming what needed it.

    Args:
        needed_by: What wants it, for the error.

    Returns:
        The extension module.

    Raises:
        RuntimeError: If it cannot be loaded, listing where it was looked
            for.
    """
    module = native_module()
    if module is not None:
        return module
    searched = "\n  ".join(str(path) for path in _candidate_paths())
    raise RuntimeError(
        f"{needed_by} needs the native extension, and it cannot be loaded. "
        f"An installed PyGuara ships it; in a checkout, build it with "
        f"`uv sync` or `make native`. Looked for an importable "
        f"`{_MODULE_NAME}`, then:\n  {searched}"
    )


def store_name() -> str:
    """Return `STORE_NAME`, the token a replay records."""
    return STORE_NAME


def describe() -> str:
    """Return one line saying where the extension was loaded from.

    Logged at bootstrap and included in a crash report.
    """
    if native_module() is None:
        return "native extension: not found"
    return f"native extension: {_source}"


def status() -> dict[str, Any]:
    """Return where the extension came from, as structured facts.

    `source` is a path on this machine, so it is not part of `ProjectMap`,
    which is rendered into a committed `AGENTS.md`.

    Returns:
        `loaded` (whether the extension could be loaded) and `source`
        (where it was loaded from, or None).
    """
    return {"loaded": native_module() is not None, "source": _source}


def reset_lookup() -> None:
    """Forget the cached lookup, so the next call looks again.

    For tests that patch `sys.modules` to simulate a missing extension.
    """
    global _module, _looked, _source
    _module = None
    _looked = False
    _source = None
