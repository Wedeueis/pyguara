"""Native acceleration, and how the engine decides to use it.

Track R moves parts of the engine into a compiled extension. The wheel
ships it, so an installed PyGuara runs native by default -- but this is
still the seam that makes it *absent-tolerant*: the module is used when it
is present and the pure-Python implementation runs when it is not, which
is what `PYGUARA_NO_NATIVE=1`, a platform with no wheel and
`native_acceleration = "off"` all rely on.

It lives at the top of the package rather than under `graphics/` because
it is no longer a graphics concern -- `ParticleSystem` and `Sparks` were
merely first. It deliberately imports nothing from `pyguara` but the
compiled extension itself, which imports nothing back, so it can be
consulted from anywhere, including from modules loaded before the engine
is bootstrapped.

The cost of that choice is two implementations to keep in agreement, which
is paid by running the same tests against both -- see
`tests/test_native_particle_parity.py`.

Building it, in a checkout:

    uv sync        # maturin is the build backend, so this compiles it
    make native    # rebuild in place after editing Rust

`cargo build --release` also works and is what `_candidate_paths` finds,
but it is now the *second* place looked at. An install wins over it, so a
bare `cargo build` after `uv sync` leaves the older installed library in
force and the new code silently unused -- rebuild with `make native`,
which is `maturin develop --release`; plain `maturin develop` builds a
*debug* extension that is slower than the Python it replaces.
See `docs/adr/0006-shipping-the-native-extension.md`.
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
    `PerformanceConfig.native_acceleration`. It is a single engine-wide
    choice rather than a per-subsystem one on purpose, and the purpose is
    reproducibility: a store picked silently from whether a `.so` happens
    to be on disk means the same game, with the same code and the same
    seed, behaves differently on a machine that built the extension and
    one that did not. That is invisible for a particle effect and is
    gameplay for a flock of enemies. See
    `docs/adr/0004-the-native-boundary.md`, Decision 4.

    OFF: never native. The pure-Python implementations run even when the
         extension is built and importable.

    AUTO: native where available, Python otherwise. The default, and the
          right setting for development and for a game that does not
          depend on native behaviour.

    REQUIRED: native, and **fail at startup** if the extension is missing.
              What a game ships with once it depends on native
              performance, so the failure is a clear error at boot rather
              than a frame-rate mystery or a divergent simulation.
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

    One level up from `pyguara/`, and derived rather than hardcoded
    because getting it wrong fails *silently*: a wrong root finds no
    library, `native_module()` falls back to Python exactly as it is
    designed to, and the suite goes green having tested none of the
    accelerator. That is precisely what happened when this module moved
    here from `pyguara/graphics/components/`, where the same expression
    needed `parents[3]`. `tests/test_native_loader.py` now fails instead.
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

    Logged at bootstrap, because Decision 4 of ADR 0004 asks for the
    resolved store to be *observable*: a choice that changes behaviour and
    is not reported is the thing being fixed.

    The store is named with `store_name()`'s token rather than spelled
    out in prose. It used to read "-> Python" in one branch and
    "-> native" in the other, which is one fact in two spellings -- and
    the moment a second reporter existed, `status()`, the two could not
    be checked against each other without a case fudge. Same fact, same
    token, in every report of it.
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

    `describe()`'s companion, and the split is deliberate: that one is one
    line of prose for a boot log, this one is for anything that has to
    *compare* or render the same facts -- Studio's `project_overview`,
    and the tests that assert the two agree.

    ADR 0004's Decision 4 asks for the resolved store to be observable,
    on the grounds that a silent choice which changes behaviour is the
    defect being fixed. A boot line satisfies that for whoever starts the
    process; an agent or an author who attached to a running Studio
    session never saw it.

    `source` is a path on this machine and is meant to be: two people
    reading the same project get different answers, which is exactly the
    thing worth seeing. That is also why this is **not** part of
    `ProjectMap` -- `pyguara studio instructions` renders one into a
    committed `AGENTS.md`, and a local `.so` path has no business there.

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

    Looked up once and cached, including the failure: an engine that has
    decided it is running pure Python should not pay a filesystem probe per
    `ParticleSystem` constructed.

    Tried in two ways. An installed `pyguara.pyguara_core_rs` wins, which
    is what the wheel provides and what `uv sync` builds in a checkout.
    Failing that, a library built in place by `cargo build` is loaded from
    `target/`, which is what a contributor gets who ran cargo and nothing
    else.

    Returns None whenever the resolved mode is `OFF`, which includes
    `PYGUARA_NO_NATIVE=1` -- the first thing to try when a bug might be
    the accelerator's, and what the parity tests use.

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
