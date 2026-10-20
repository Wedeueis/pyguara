# ADR 0006: The wheel ships the extension, so native is the default store

- **Status:** accepted
- **Date:** 2026-10-20
- **Amends:** ADR 0003 (the crate's packaging), ADR 0004 Decision 4 (what
  the engine-wide switch is protecting against)

## Context

ADR 0003 built the native accelerator as a crate that is **not** wired into
`pyproject.toml`: `cargo build --release` produced a library, `uv sync`
kept working without a Rust toolchain, and `pyguara/native.py` used the
extension when it found one. That was the right shape for a spike whose
milestone was still a question.

It is the wrong shape for a shipped engine, and the reason is in the
numbers ADR 0004 recorded. A flow field recomputes **46-53x** faster; a
flock of 1000 agents goes from 16 ms a tick -- 96% of a 16.7 ms frame --
to 1.9 ms. Those are not optimisations, they are the difference between a
crowd the engine can carry and one it cannot. Under build-it-yourself
packaging, **every one of them is a lottery decided by whether the person
who installed PyGuara happened to have `cargo` on their machine.**

That also leaves Decision 4 defending against a condition the packaging
created. Decision 4 exists because "the same game, same code, same seed,
diverges between a machine that built the extension and one that did not",
and an engine-wide, observable switch is the right answer to that *given*
the divergence. Removing the divergence is better than reporting it.

## Decision

**maturin replaces hatchling as the build backend, and the compiled
extension ships inside the wheel.** `pip install pyguara` is native on
every platform the wheel matrix covers; nobody runs `cargo` to get the
performance the documentation promises.

Three mechanical consequences, each verified rather than assumed:

**1. The extension moves inside the package.** A mixed python/rust project
requires the module to live under the Python package, so the importable
name is `pyguara.pyguara_core_rs` rather than a top-level
`pyguara_core_rs`. The crate, the cargo library, the `#[pymodule]` and the
module keep one spelling -- which is why the name stutters rather than
being shortened to a private `_core` under the package.
`pyproject.toml` and `native.py` both
have to agree on it, so
`test_the_module_name_matches_the_one_maturin_installs` reads the former
and asserts the latter: a mismatch would make the import fail, the
`target/` fallback answer in a checkout, every test still pass, and an
*installed* PyGuara run pure Python while reporting nothing wrong.

**2. One wheel per platform, not per platform and interpreter.** The crate
already built against `abi3-py312`, so a single wheel serves 3.12 and
3.13. Verified by installing the 3.12-built wheel under 3.13 and checking
`native.store_name()` -- it reports `native`. The Linux row was verified
the whole way: built in maturin's own manylinux container, it tags as
`cp312-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64`, and installed
into an empty venv with no toolchain it recomputes a flow field through
the native store (`vector_at` returning the correct diagonal). Built
against the host instead, the wheel tags `manylinux_2_35` and maturin
refuses `manylinux2014` outright -- too-recent `GLIBC_2.3x` symbols --
which is why `manylinux: auto` and its container matter and a locally
built wheel is not the artifact to ship. Five wheels are built:
Linux x86_64 and aarch64, macOS x86_64 and arm64, Windows x64. Windows
x86/arm64 and Linux armv7/s390x/ppc64le are deliberately absent, because
`pygame-ce` and `pymunk` ship no wheels there and an installable PyGuara
wheel for a platform the engine cannot run on is a trap.

**3. The hatchling pin retires with the backend.** That pin
(`hatchling>=1.27,<1.28`) existed because 1.28 emits
`Metadata-Version: 2.5`, which released `twine`/`pkginfo` reject. maturin
1.15 emits **2.4** and `twine check` passes on its wheel, so the
workaround is not carried over -- and the release workflow now runs
`twine check` on every artifact, which asserts what the pin used to stand
in for.

### What this does not change

`native.py` stays **absent-tolerant**, and the pure-Python implementations
stay. They are not dead code:

- `PYGUARA_NO_NATIVE=1` is the first thing to try when a bug might be the
  accelerator's, and what the parity suites use.
- `native_acceleration = "off"` is a supported setting, and `SpatialHash`
  has a documented access pattern where Python is **faster** (ADR 0004,
  Decision 7).
- A platform outside the matrix installs from the sdist, and a developer
  may have a checkout with nothing built yet.

Decision 4's engine-wide switch therefore stands exactly as written. What
changes is that `auto` now resolves to native for essentially every
installed game rather than for whoever had a toolchain, so the divergence
it reports has become rare instead of routine.

## The cost, stated

**A source build now needs a Rust toolchain where none was needed
before.** This is not a side effect to be minimised; it is the price, and
it falls on three groups:

- **Contributors.** `uv sync` compiles the crate. A checkout without
  `cargo` no longer produces a working environment at all -- previously it
  produced one that silently ran Python.
- **The sdist.** `pip install pyguara --no-binary` and any platform
  outside the five wheels compile the crate themselves.
- **Downstream builds** that pin `--no-binary` by policy.

The mitigation is the wheel matrix itself: the platforms a PyGuara game
actually ships on are covered, so almost nobody performs a source build.

The sdist also needed trimming. maturin's default is the whole git
checkout -- **1156 files**, including `assets/`, `games/`, `docs/`,
`tests/` and two agent scratch directories, where hatchling shipped 404.
`[tool.maturin] exclude` brings it to 414: the package, the crate,
`Cargo.toml`, `Cargo.lock`, `pyproject.toml`, the readme, the licence and
the changelog, which is everything a source build needs and nothing else.

## What this introduces, and what guards each thing

Shipping a compiled artifact adds failure modes that are **silent by
construction** -- an engine running Python where native was expected
installs, imports, runs every demo, and is merely slower. Each one gets a
guard rather than a note:

| failure mode | guard |
| --- | --- |
| a wheel built without the extension in it | `wheels.yml` opens the archive and asserts a `.so`/`.pyd`/`.dylib` is present -- which works for the cross-compiled rows too, as they cannot run their own wheel |
| CI never compiling the crate, so every parity suite skips | fixed as a side effect: `make install` builds it. Plus a step that calls `configure(REQUIRED)`, the engine's own mechanism for refusing to run Python by accident |
| the pure-Python store rotting now that nobody runs it | a `python-fallback` job runs the unit suite under `PYGUARA_NO_NATIVE=1` |
| `maturin develop` defaulting to a **debug** build, which is slower than Python and would fail every perf guard | `make native` passes `--release` |
| an installed extension outranking a newer `cargo build --release`, so edited Rust is silently not running | documented in `native.py`, and asserted by `test_an_installed_extension_wins_over_a_cargo_build` -- the fix is `maturin develop`, not another `cargo build` |

The first of those is the one worth dwelling on. Before this change the
pipeline had **no `cargo` step at all**: the five Track R subsystems were
merged by a CI run that compiled nothing, skipped every parity suite, and
reported green. CI was precisely the contributor-without-Rust that
`AGENTS.md` warns about.

## Alternatives considered

**Publish the accelerator as its own wheel** (`pyguara_core_rs`), with
`pyguara` staying pure Python and depending on it under platform markers.
This keeps a toolchain-free source build and a `py3-none-any` wheel.
Rejected: two distributions means two version matrices, and an install
where the accelerator does not match the engine version is a parity
violation nothing would detect -- the two implementations have to agree,
and that is only checkable when they ship together.

**Keep build-it-yourself** (the status quo). Rejected: it makes the
engine's headline performance a property of the installer's machine, and
it is the condition Decision 4 was written to cope with rather than one
worth preserving.

**Ship both a pure-Python wheel and platform wheels.** A `py3-none-any`
wheel is a valid install candidate on every platform, so resolvers would
hand it to people who could have had the extension, reintroducing the
lottery with extra steps.

## Consequences

- `uv sync` is the one-step build; `make native` (`maturin develop
  --release`) rebuilds in place after editing Rust. `cargo build --release`
  still works and is still found, but is now the *second* place looked at.
- Every CI job that installs the project installs a Rust toolchain, cached
  with `Swatinem/rust-cache`.
- `wheels.yml` is a reusable workflow called by both `ci.yml` and
  `release.yml`, so what a release publishes is built by the same job that
  verified it on the branch.
- `AGENTS.md`'s claim that "nothing in this repository requires" a Rust
  toolchain is now false and has been rewritten. ADR 0003's "not wired
  into `pyproject.toml`" and its warning about `maturin build` overwriting
  the real package are superseded here: `module-name` is set, which is what
  that warning asked for.
- W29 (Nuitka, source protection only) now has a PyO3 extension to verify
  against, which the plan already listed as a risk alongside `pymunk`'s
  CFFI.
