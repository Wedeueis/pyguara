"""Native acceleration, and how the engine decides to use it.

The compiled extension is used when it is present and allowed, and the
pure-Python implementations run otherwise. `PYGUARA_NO_NATIVE=1`, a
platform with no wheel and `native_acceleration = "off"` rely on that.

This module imports nothing from `pyguara` but the extension itself,
so it can be consulted from anywhere, including before bootstrap.

Building the extension is covered in `AGENTS.md` and
`docs/adr/0006-shipping-the-native-extension.md`.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Any

_ENV_DISABLE = "PYGUARA_NO_NATIVE"

# The importable name of the extension. A mixed python/rust wheel requires
# the module to sit under the Python package, so it is dotted rather than
# top-level -- see `[tool.maturin]` in `pyproject.toml`. Spelled once here
# because it is also what the error messages quote and what the `target/`
# fallback registers in `sys.modules`.
_MODULE_NAME = "pyguara.pyguara_core_rs"


class NativeAcceleration(Enum):
    """Whether the engine uses the compiled extension.

    One value for the whole process, resolved once at bootstrap from
    `PerformanceConfig.native_acceleration`, so the same game with the
    same seed behaves the same wherever it runs. See ADR 0004, Decision 4.

    OFF: never native. The pure-Python implementations run even when the
         extension is built and importable.

    AUTO: native where available, Python otherwise. The default.

    REQUIRED: native, and fail at startup if the extension is missing.
              For a game that depends on native performance.
    """

    OFF = "off"
    AUTO = "auto"
    REQUIRED = "required"


_mode: NativeAcceleration = NativeAcceleration.AUTO
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


def _effective_mode() -> NativeAcceleration:
    """Return the mode in force, after the environment override.

    `PYGUARA_NO_NATIVE=1` forces `OFF`, and it is checked here rather than
    in `configure()` so it works whether or not the engine was ever
    bootstrapped -- a bare `ParticleSystem(...)` in a script or a test has
    no bootstrap behind it, and that is exactly where the override gets
    reached for.
    """
    if os.environ.get(_ENV_DISABLE):
        return NativeAcceleration.OFF
    return _mode


def configure(mode: NativeAcceleration) -> NativeAcceleration:
    """Set the process-wide store, once, at bootstrap.

    Resolving `REQUIRED` here is the point of calling it early: the
    extension is probed immediately and a missing one raises *at startup*,
    rather than at whatever later moment first constructs an accelerated
    object. A game that depends on native performance should not discover
    it is running the Python fallback from its frame times.

    Args:
        mode: The configured setting, from
            `PerformanceConfig.native_acceleration`.

    Returns:
        The mode actually in force, which differs from `mode` when
        `PYGUARA_NO_NATIVE` is set.

    Raises:
        RuntimeError: If `mode` is `REQUIRED` and either the extension is
            unavailable or `PYGUARA_NO_NATIVE` is set -- the two
            instructions contradict each other, and picking a winner
            silently is how a build ends up shipping the wrong store.
    """
    global _mode
    if mode is NativeAcceleration.REQUIRED and os.environ.get(_ENV_DISABLE):
        raise RuntimeError(
            f"native_acceleration is 'required' but {_ENV_DISABLE} is set. "
            f"These contradict: one demands the extension, the other "
            f"forbids it. Unset the variable, or configure 'auto'."
        )

    _mode = mode
    reset_lookup()

    if mode is NativeAcceleration.REQUIRED and native_module() is None:
        searched = "\n  ".join(str(path) for path in _candidate_paths())
        raise RuntimeError(
            f"native_acceleration is 'required' but the extension is not "
            f"available. An installed PyGuara ships it; in a checkout, "
            f"build it with `uv sync` or `make native`, or "
            f"configure 'auto' to fall back to Python. Looked for an "
            f"importable `{_MODULE_NAME}`, then:\n  {searched}"
        )
    return _effective_mode()


def resolved() -> NativeAcceleration:
    """Return the mode in force, environment override included."""
    return _effective_mode()


def in_use() -> bool:
    """Report whether a native store is actually backing the engine.

    The honest question, and not the same as `resolved() is not OFF`:
    `AUTO` with no compiled extension resolves to `AUTO` and runs Python.
    """
    return native_module() is not None


def store_name() -> str:
    """Return a short, comparable name for the store in force.

    `"native"` or `"python"`. Separate from `describe()`, which is prose
    for a human and carries a filesystem path: this is the token that gets
    written into a replay's metadata and compared on playback, so it has
    to be stable across machines and short enough to read in a JSON file.

    Returns:
        The store's name.
    """
    return "native" if native_module() is not None else "python"


def describe() -> str:
    """Return one line saying which store is in force and why.

    Logged at bootstrap. The store is named with `store_name()`'s token,
    the same one `status()` reports.
    """
    mode = _effective_mode()
    overridden = (
        f" ({_ENV_DISABLE} override)"
        if os.environ.get(_ENV_DISABLE) and _mode is not NativeAcceleration.OFF
        else ""
    )
    if native_module() is None:
        reason = (
            "disabled"
            if mode is NativeAcceleration.OFF
            else "no compiled extension found"
        )
        return (
            f"native acceleration: {mode.value}{overridden} -> "
            f"{store_name()} ({reason})"
        )
    return (
        f"native acceleration: {mode.value}{overridden} -> {store_name()} ({_source})"
    )


def status() -> dict[str, Any]:
    """Return the resolved store as structured facts.

    The structured form of `describe()`, for anything that compares or
    renders the facts, such as Studio's `project_overview`.

    `source` is a path on this machine, so it is not part of `ProjectMap`,
    which is rendered into a committed `AGENTS.md`.

    Returns:
        `store` ("native" or "python"), `mode` (the configured setting),
        `source` (where the library was loaded from, or None), and
        `env_override` (whether `PYGUARA_NO_NATIVE` is forcing the
        answer).
    """
    module = native_module()
    return {
        "store": "native" if module is not None else "python",
        "mode": _effective_mode().value,
        "source": _source,
        "env_override": bool(os.environ.get(_ENV_DISABLE)),
    }


def native_module() -> Any | None:
    """Return the native extension, or None when it is unavailable.

    Looked up once and cached, including the failure. An installed
    `pyguara.pyguara_core_rs` wins; failing that, a library built in place
    by `cargo build` is loaded from `target/`.

    Returns None whenever the resolved mode is `OFF`, which includes
    `PYGUARA_NO_NATIVE=1`.

    Returns:
        The module, or None.
    """
    global _module, _looked, _source
    if _looked:
        return _module
    _looked = True

    if _effective_mode() is NativeAcceleration.OFF:
        return None

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
        # Its own `__file__` rather than "installed", because this branch
        # also catches a library *this* module put in `sys.modules` on an
        # earlier lookup, and reporting that as an install is misleading
        # to the one person who ever reads it -- someone debugging which
        # store is running.
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
    """Return the extension for code that has no Python implementation.

    Not `native_module()`: that answers "which *store* is in force", and
    returns None under `PYGUARA_NO_NATIVE=1`, a debugging switch. A backend
    with nothing to fall back to is not a store and is not governed by it --
    the same variable silently changing what a game can ask its audio for
    would be a gameplay change from a debug switch. See ADR 0004, Decision 4.

    Args:
        needed_by: What wants it, for the error.

    Returns:
        The extension module.

    Raises:
        RuntimeError: If it cannot be imported.
    """
    try:
        return importlib.import_module(_MODULE_NAME)
    except ImportError:
        pass
    for library in _candidate_paths():
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
        return module
    raise RuntimeError(
        f"{needed_by} needs the native extension, and it cannot be imported. "
        "An installed PyGuara ships it; in a checkout, run `make native`."
    )


def reset_lookup() -> None:
    """Forget the cached lookup, keeping the configured mode.

    Called by `configure()`, because a mode set after something already
    asked would otherwise be ignored for the life of the process.
    """
    global _module, _looked, _source
    _module = None
    _looked = False
    _source = None


def reset_for_tests() -> None:
    """Forget the cached lookup *and* the configured mode."""
    global _mode
    _mode = NativeAcceleration.AUTO
    reset_lookup()
