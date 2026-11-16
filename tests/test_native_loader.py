"""The seam that decides whether the engine runs native or Python.

Every failure here is silent by design: `native_module()` returning
None is how the engine runs without the extension, so a broken lookup
or a wrong search path looks the same as "no extension here", and
every native test skips.

`test_the_repository_root_is_the_repository_root` is the test that
catches a wrong root: it asserts the derived root is a PyGuara
checkout and never asks about the extension. See ADR 0004, Decision 4.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

from pyguara import native
from pyguara.native import NativeAcceleration


@pytest.fixture(autouse=True)
def _isolated_mode(monkeypatch: pytest.MonkeyPatch) -> object:
    """Give each test a known mode and a clean environment.

    The mode is module state, so a test that configures it would decide
    the store for every test after it.

    The environment is cleared, not just restored: this file asserts
    about the override itself, so it must not inherit a developer's
    `PYGUARA_NO_NATIVE`. The tests about the override set it themselves,
    after this.
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

    def test_the_module_name_matches_the_one_maturin_installs(self) -> None:
        """Two files spell this name, and a mismatch is silent.

        `pyproject.toml` decides where maturin puts the extension inside
        the wheel and `native.py` decides what to import. Change one and
        the import fails, the `target/` library answers instead, every
        test here still passes in a checkout -- and an installed PyGuara,
        which has no `target/`, runs pure Python while reporting nothing
        wrong. The whole file exists because that failure is quiet.
        """
        config = tomllib.loads(
            (native._repository_root() / "pyproject.toml").read_text()
        )

        assert config["tool"]["maturin"]["module-name"] == native._MODULE_NAME

    def test_an_installed_extension_wins_over_a_cargo_build(self) -> None:
        """Which matters because the two can disagree.

        `uv sync` installs the extension into the package; a later
        `cargo build --release` writes a *different*, newer library under
        `target/` that is then never loaded. Asserting the order here is
        what makes that documented rather than discovered -- the fix is
        `maturin develop`, not another `cargo build`.
        """
        if importlib.util.find_spec(native._MODULE_NAME) is None:
            pytest.skip("nothing installed; only a cargo build could answer")
        from_cargo = [path for path in native._candidate_paths() if path.exists()]
        if not from_cargo:
            pytest.skip("no cargo build present to lose the race")

        native.reset_for_tests()
        source = native.status()["source"]

        assert source is not None
        assert Path(source) not in from_cargo, (
            f"{source} is the `target/` library, but an installed "
            f"extension exists and should have won"
        )

    def test_a_library_on_disk_is_actually_loaded(self) -> None:
        """A library that exists and is not loaded is a bug, not an absence.

        Distinguishes "there is no extension" (skip, the normal state
        without Rust) from "there is one at a path we derived, and we
        failed to use it" (fail) -- a stale build, an ABI mismatch, a
        rename in the crate.

        It does not catch a wrong search root: nothing exists at a
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
        monkeypatch.setitem(sys.modules, native._MODULE_NAME, None)
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
        assert "python" in report

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


class TestTheStructuredStatus:
    """`status()` is `describe()` for a machine, and must not drift from it.

    Two reports of one fact are two chances to disagree, so these mostly
    assert that they do not. The division of labour: Studio asserts that
    it *reports* whatever this module says
    (`tests/studio/test_ops.py::TestProjectOverviewReportsTheEngine`),
    and this asserts that what it says is true. Keeping the mode tests
    here is not tidiness -- the mode is process-wide module state, and
    this file is where the fixture that isolates it lives.
    """

    @pytest.mark.parametrize(
        "mode",
        [NativeAcceleration.OFF, NativeAcceleration.AUTO, NativeAcceleration.REQUIRED],
    )
    def test_the_mode_is_the_configured_one(self, mode: NativeAcceleration) -> None:
        """Not pinned by a default-environment test, which reads `auto`.

        A `status()` that returned a hardcoded "auto" passed every other
        test of it, because the suite runs under `auto`. This one
        configures each mode in turn, which is the only way the field is
        checked at all.
        """
        if mode is NativeAcceleration.REQUIRED and not _built():
            pytest.skip("native extension not built; `cargo build --release`")
        native.configure(mode)

        assert native.status()["mode"] == mode.value

    def test_the_store_is_the_one_actually_in_force(self) -> None:
        native.configure(NativeAcceleration.OFF)
        assert native.status()["store"] == "python"

        native.configure(NativeAcceleration.AUTO)
        assert native.status()["store"] == native.store_name()

    def test_auto_without_an_extension_is_honest_about_running_python(self) -> None:
        """`auto` resolves to `auto`, and the store is the honest question.

        The same distinction `in_use()` exists for: a mode of `auto` says
        what was asked for, not what happened.
        """
        if _built():
            pytest.skip("the extension is built, so auto does find one")
        native.configure(NativeAcceleration.AUTO)

        status = native.status()
        assert status["mode"] == "auto"
        assert status["store"] == "python"
        assert status["source"] is None

    def test_the_environment_override_is_reported_as_such(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Otherwise the report says `off` and nobody knows who chose it."""
        monkeypatch.setenv("PYGUARA_NO_NATIVE", "1")
        native.reset_for_tests()

        status = native.status()
        assert status["env_override"] is True
        assert status["store"] == "python"

    def test_the_source_names_the_library_that_was_loaded(self) -> None:
        if not _built():
            pytest.skip("native extension not built; `cargo build --release`")
        native.configure(NativeAcceleration.AUTO)

        source = native.status()["source"]
        assert source is not None
        assert "pyguara_core_rs" in source

    @pytest.mark.parametrize("mode", [NativeAcceleration.OFF, NativeAcceleration.AUTO])
    def test_it_does_not_drift_from_the_prose_report(
        self, mode: NativeAcceleration
    ) -> None:
        """Both read the same module state; the risk is one being changed.

        Plain string containment, deliberately. An earlier version of
        this needed a `.capitalize()` and a `.replace()` to pass, because
        `describe()` said "-> Python" in one branch and "-> native" in
        the other. A test that has to normalise before comparing is
        reporting a real inconsistency, and the fix belonged in
        `describe()`, not here.
        """
        native.configure(mode)

        status = native.status()
        described = native.describe()

        assert described.startswith(f"native acceleration: {status['mode']}")
        assert f"-> {status['store']} " in described
