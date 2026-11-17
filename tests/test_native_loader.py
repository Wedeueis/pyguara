"""The seam that finds the compiled extension, which the engine requires.

A broken lookup or a wrong search path looks the same as "no extension
here", and the engine then refuses to start. So the search itself is
tested, independently of whether this checkout built anything.

`test_the_repository_root_is_the_repository_root` is the test that
catches a wrong root: it asserts the derived root is a PyGuara checkout
and never asks about the extension.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

from pyguara import native


@pytest.fixture(autouse=True)
def _fresh_lookup() -> object:
    """Forget the cached lookup around each test, which may patch it."""
    native.reset_lookup()
    yield
    native.reset_lookup()


class TestTheSearchPath:
    def test_the_repository_root_is_the_repository_root(self) -> None:
        """One assertion that would have caught the move immediately."""
        assert (native._repository_root() / "pyproject.toml").is_file(), (
            f"the derived root {native._repository_root()} is not a PyGuara "
            f"checkout, so the library search below cannot find anything"
        )

    def test_the_module_name_matches_the_one_maturin_installs(self) -> None:
        """Two files spell this name, and a mismatch is silent.

        `pyproject.toml` decides where maturin puts the extension inside
        the wheel and `native.py` decides what to import. Change one and
        the import fails, the `target/` library answers instead, every
        test here still passes in a checkout -- and an installed PyGuara,
        which has no `target/`, cannot start.
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

        native.reset_lookup()
        source = native.status()["source"]

        assert source is not None
        assert Path(source) not in from_cargo, (
            f"{source} is the `target/` library, but an installed "
            f"extension exists and should have won"
        )

    def test_a_library_on_disk_is_actually_loaded(self) -> None:
        """A library that exists and is not loaded is a bug, not an absence.

        Distinguishes "there is no extension" from "there is one at a path
        we derived, and we failed to use it" -- a stale build, an ABI
        mismatch, a rename in the crate.

        It does not catch a wrong search root: nothing exists at a
        wrong path, so this skips. The module docstring says which test
        does.
        """
        present = [path for path in native._candidate_paths() if path.exists()]
        if not present:
            pytest.skip("no compiled library in this checkout")

        native.reset_lookup()

        assert native.native_module() is not None, (
            f"{present[0]} exists but was not loaded"
        )


class TestAMissingExtension:
    """Simulated with `sys.modules`, which `import_module` consults first."""

    @pytest.fixture
    def missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, native._MODULE_NAME, None)  # type: ignore[arg-type]
        monkeypatch.setattr(native, "_candidate_paths", lambda: [])
        native.reset_lookup()

    def test_the_lookup_reports_none(self, missing: None) -> None:
        assert native.native_module() is None

    def test_requiring_it_names_what_needed_it(self, missing: None) -> None:
        with pytest.raises(RuntimeError, match="SpatialHash needs the native"):
            native.require_extension("SpatialHash")

    def test_the_engine_refuses_to_start(
        self, missing: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """At bootstrap, not at whatever is built first."""
        from pyguara.application.bootstrap import create_headless_application

        monkeypatch.chdir(tmp_path)
        with pytest.raises(RuntimeError, match="PyGuara needs the native"):
            create_headless_application()

    def test_the_report_says_so(self, missing: None) -> None:
        assert native.describe() == "native extension: not found"
        assert native.status() == {"loaded": False, "source": None}


class TestTheReport:
    def test_it_names_where_the_library_came_from(self) -> None:
        native.require_extension("this test")
        status = native.status()
        assert status["loaded"] is True
        assert status["source"]
        assert native.describe() == f"native extension: {status['source']}"

    def test_the_store_is_the_one_a_replay_records(self) -> None:
        assert native.store_name() == native.STORE_NAME == "native"

    def test_the_old_switch_is_gone(self) -> None:
        """A config or environment variable naming it does nothing now."""
        for name in ("NativeAcceleration", "configure", "in_use", "resolved"):
            assert not hasattr(native, name), name
