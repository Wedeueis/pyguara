"""The seam that decides whether the engine runs native or Python.

Worth its own file because **every failure here is silent by design**.
`native_module()` returning None is how the engine stays installable
without a Rust toolchain, so a broken lookup, a stale build or a wrong
search path all present identically to "no extension here", the suite goes
green, and nobody has tested the accelerator.

That is not hypothetical. This module moved from
`pyguara/graphics/components/_native.py` to `pyguara/native.py` and its
`parents[3]` became wrong by two levels; the whole suite passed, with every
native test skipped.

Note which test below catches that, because it is not the obvious one.
With a wrong root, no candidate path exists, so every test that asks "is
there a library?" skips -- including
`test_a_library_on_disk_is_actually_loaded`, which was written for this
and does not catch it. The one that fails is
`test_the_repository_root_is_the_repository_root`, which asserts the
derived root is a PyGuara checkout and never asks about the extension at
all. Re-introducing the bug was how that was established, rather than
assumed.

See `docs/adr/0004-the-native-boundary.md`, Decision 4, for why the store
is one engine-wide choice rather than a per-subsystem one.
"""

from __future__ import annotations

import pytest

from pyguara import native
from pyguara.native import NativeAcceleration


@pytest.fixture(autouse=True)
def _isolated_mode(monkeypatch: pytest.MonkeyPatch) -> object:
    """Give each test a known mode and a clean environment.

    Two separate hazards, both real.

    The mode is module state, so a test that configures it would decide
    the store for every test that ran afterwards.

    And the environment has to be *cleared*, not merely restored: this
    file asserts about the override machinery itself, so inheriting a
    developer's `PYGUARA_NO_NATIVE` would make it assert about an
    environment it did not choose. Three tests here failed exactly that
    way under `PYGUARA_NO_NATIVE=1 uv run pytest` -- the one command the
    override exists for. The tests that are *about* the override set it
    themselves, after this.
    """
    monkeypatch.delenv("PYGUARA_NO_NATIVE", raising=False)
    native.reset_for_tests()
    yield
    native.reset_for_tests()


def _built() -> bool:
    """Whether this checkout has a usable extension at all."""
    native.reset_for_tests()
    return native.native_module() is not None


class TestTheSearchPath:
    def test_the_repository_root_is_the_repository_root(self) -> None:
        """One assertion that would have caught the move immediately."""
        assert (native._repository_root() / "pyproject.toml").is_file(), (
            f"the derived root {native._repository_root()} is not a PyGuara "
            f"checkout, so the library search below cannot find anything "
            f"and every native test will skip rather than fail"
        )

    def test_a_library_on_disk_is_actually_loaded(self) -> None:
        """A library that exists and is not loaded is a bug, not an absence.

        Distinguishes "there is no extension" (skip, the normal state
        without Rust) from "there is one at a path we derived, and we
        failed to use it" (fail) -- a stale build, an ABI mismatch, a
        rename in the crate.

        It does **not** catch a wrong search root: nothing exists at a
        wrong path, so this skips. The module docstring says which test
        does.
        """
        present = [path for path in native._candidate_paths() if path.exists()]
        if not present:
            pytest.skip("no compiled library in this checkout")

        native.reset_for_tests()

        assert native.native_module() is not None, (
            f"{present[0]} exists but was not loaded. The engine has "
            f"silently fallen back to Python, which is the designed "
            f"behaviour for a missing extension and a bug for a present one"
        )


class TestTheMode:
    def test_the_default_is_auto(self) -> None:
        """So a bare `ParticleSystem(...)` with no bootstrap behaves as before."""
        native.reset_for_tests()

        assert native.resolved() is NativeAcceleration.AUTO

    def test_off_declines_an_available_extension(self) -> None:
        if not _built():
            pytest.skip("native extension not built; `cargo build --release`")

        native.configure(NativeAcceleration.OFF)

        assert native.native_module() is None
        assert native.in_use() is False

    def test_auto_uses_what_is_available(self) -> None:
        built = _built()
        native.configure(NativeAcceleration.AUTO)

        assert native.in_use() is built

    def test_required_passes_when_the_extension_is_there(self) -> None:
        if not _built():
            pytest.skip("native extension not built; `cargo build --release`")

        assert native.configure(NativeAcceleration.REQUIRED) is (
            NativeAcceleration.REQUIRED
        )
        assert native.in_use() is True

    def test_required_fails_loudly_when_it_is_not(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of resolving at bootstrap rather than lazily."""
        monkeypatch.setattr(native, "_candidate_paths", list)
        monkeypatch.setitem(__import__("sys").modules, "pyguara_core_rs", None)
        native.reset_for_tests()

        with pytest.raises(RuntimeError, match="not available"):
            native.configure(NativeAcceleration.REQUIRED)

    def test_reconfiguring_takes_effect(self) -> None:
        """The lookup caches, so `configure` has to clear it."""
        if not _built():
            pytest.skip("native extension not built; `cargo build --release`")

        native.configure(NativeAcceleration.AUTO)
        assert native.in_use() is True

        native.configure(NativeAcceleration.OFF)

        assert native.in_use() is False


class TestTheEnvironmentOverride:
    def test_the_variable_forces_python(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PYGUARA_NO_NATIVE", "1")
        native.reset_for_tests()

        assert native.resolved() is NativeAcceleration.OFF
        assert native.native_module() is None

    def test_it_works_without_a_bootstrap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Checked in `_effective_mode`, not `configure`, for this reason.

        `PYGUARA_NO_NATIVE=1 uv run pytest` runs no bootstrap at all, and
        is the documented way to check whether a bug is the accelerator's.
        """
        monkeypatch.setenv("PYGUARA_NO_NATIVE", "1")
        native.reset_for_tests()  # nothing configured, as in a bare script

        assert native.native_module() is None

    def test_required_against_the_variable_is_a_contradiction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rather than silently picking a winner."""
        monkeypatch.setenv("PYGUARA_NO_NATIVE", "1")
        native.reset_for_tests()

        with pytest.raises(RuntimeError, match="contradict"):
            native.configure(NativeAcceleration.REQUIRED)


class TestTheReport:
    def test_it_names_the_store_in_force(self) -> None:
        native.configure(NativeAcceleration.OFF)

        report = native.describe()

        assert "off" in report
        assert "Python" in report

    def test_it_names_the_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A choice that changes behaviour and is not reported is the bug."""
        monkeypatch.setenv("PYGUARA_NO_NATIVE", "1")
        native.reset_for_tests()

        assert "PYGUARA_NO_NATIVE" in native.describe()

    def test_it_names_where_the_library_came_from(self) -> None:
        if not _built():
            pytest.skip("native extension not built; `cargo build --release`")
        native.configure(NativeAcceleration.AUTO)

        assert "native" in native.describe()
        assert "pyguara_core_rs" in native.describe()
