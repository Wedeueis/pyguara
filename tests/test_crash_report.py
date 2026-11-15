"""A crash leaves a report in the user's data directory and says where.

Roadmap phase 2, crash capture. The hook is called directly with a real
exception for the unit tests; one test runs a real process to its death,
since an excepthook that only works when called by hand proves little.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import pyguara
from pyguara import crash


def _raised(message: str = "boom") -> tuple[type[BaseException], BaseException, object]:
    try:
        raise ValueError(message)
    except ValueError:
        return sys.exc_info()  # type: ignore[return-value]


@pytest.fixture(autouse=True)
def _restore_hook():
    original = sys.excepthook
    yield
    crash.uninstall_crash_reporter()
    crash.clear_notes()
    sys.excepthook = original


@pytest.fixture
def chained(monkeypatch) -> list[BaseException]:
    """Stand in for the interpreter's own hook, so nothing prints."""
    seen: list[BaseException] = []
    monkeypatch.setattr(sys, "excepthook", lambda t, e, tb: seen.append(e))
    return seen


def test_a_crash_writes_a_report_with_what_is_needed_to_diagnose_it(
    tmp_path: Path, chained: list[BaseException]
) -> None:
    reporter = crash.install_crash_reporter("Test Game", directory=tmp_path)
    crash.note("renderer", "wgpu")

    sys.excepthook(*_raised("the reactor melted"))

    reports = list(tmp_path.glob("crash-*.txt"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert "ValueError: the reactor melted" in text
    assert "Traceback" in text
    assert f"pyguara: {pyguara.__version__}" in text
    assert f"python: {sys.version.split()[0]}" in text
    assert "native store:" in text
    assert "renderer: wgpu" in text
    assert "game: Test Game" in text
    assert reporter.last_report == reports[0]


def test_the_previous_hook_still_runs(
    tmp_path: Path, chained: list[BaseException]
) -> None:
    crash.install_crash_reporter("Test Game", directory=tmp_path)
    exc_info = _raised()

    sys.excepthook(*exc_info)

    assert chained == [exc_info[1]]


def test_it_says_where_the_report_is(
    tmp_path: Path, chained: list[BaseException], capsys
) -> None:
    reporter = crash.install_crash_reporter("Test Game", directory=tmp_path)

    sys.excepthook(*_raised())

    assert str(reporter.last_report) in capsys.readouterr().err


def test_ctrl_c_is_not_a_crash(tmp_path: Path, chained: list[BaseException]) -> None:
    crash.install_crash_reporter("Test Game", directory=tmp_path)
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())  # type: ignore[arg-type]

    assert list(tmp_path.iterdir()) == []
    assert len(chained) == 1


def test_a_report_that_cannot_be_written_does_not_hide_the_crash(
    tmp_path: Path, chained: list[BaseException], capsys
) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("")
    crash.install_crash_reporter("Test Game", directory=blocked)
    exc_info = _raised()

    sys.excepthook(*exc_info)

    assert chained == [exc_info[1]]
    assert "could not write a crash report" in capsys.readouterr().err


def test_only_the_newest_reports_are_kept(
    tmp_path: Path, chained: list[BaseException]
) -> None:
    for i in range(5):
        (tmp_path / f"crash-20000101-00000{i}-1.txt").write_text("old")
    crash.install_crash_reporter("Test Game", directory=tmp_path, keep=3)

    sys.excepthook(*_raised())

    kept = sorted(p.name for p in tmp_path.glob("crash-*.txt"))
    assert len(kept) == 3
    assert "crash-20000101-000004-1.txt" in kept


def test_installing_twice_replaces_rather_than_reports_twice(
    tmp_path: Path, chained: list[BaseException]
) -> None:
    crash.install_crash_reporter("Test Game", directory=tmp_path / "a")
    crash.install_crash_reporter("Test Game", directory=tmp_path / "b")

    sys.excepthook(*_raised())

    assert not (tmp_path / "a").exists() or not list((tmp_path / "a").iterdir())
    assert len(list((tmp_path / "b").glob("crash-*.txt"))) == 1
    assert len(chained) == 1


def test_uninstall_puts_the_previous_hook_back(chained: list[BaseException]) -> None:
    before = sys.excepthook
    crash.install_crash_reporter("Test Game", directory=Path(os.devnull))
    crash.uninstall_crash_reporter()

    assert sys.excepthook is before


def test_the_default_directory_is_the_users_data_directory(
    tmp_path: Path, monkeypatch
) -> None:
    import platformdirs

    asked: list[tuple[str, str | None]] = []

    def user_data_dir(name: str, author: str | None = None, **_: object) -> str:
        asked.append((name, author))
        return str(tmp_path / name)

    monkeypatch.setattr(platformdirs, "user_data_dir", user_data_dir)

    reporter = crash.install_crash_reporter("Test Game")

    assert reporter.directory == tmp_path / "Test Game" / "crashes"
    assert asked == [("Test Game", None)]


def test_an_empty_game_name_is_refused() -> None:
    with pytest.raises(ValueError, match="app_name"):
        crash.install_crash_reporter("")


def test_a_real_process_that_dies_leaves_its_report(tmp_path: Path) -> None:
    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from pyguara.crash import install_crash_reporter
        install_crash_reporter("Test Game", directory=Path({str(tmp_path)!r}))
        raise RuntimeError("out of fuel")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 1
    reports = list(tmp_path.glob("crash-*.txt"))
    assert len(reports) == 1
    assert "RuntimeError: out of fuel" in reports[0].read_text(encoding="utf-8")
    assert str(reports[0]) in result.stderr
    # The interpreter's own traceback still prints after ours.
    assert "Traceback" in result.stderr


def test_the_engine_notes_its_renderer_when_it_starts() -> None:
    import pygame

    from pyguara.application.bootstrap import create_headless_application

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    try:
        create_headless_application()
        assert crash._notes["renderer"] == "headless"
    finally:
        pygame.quit()


def test_a_wgpu_start_notes_the_gpu_it_is_drawing_on() -> None:
    from pyguara.application.bootstrap import (
        NoGraphicsAdapterError,
        create_application,
    )

    try:
        app = create_application()
    except NoGraphicsAdapterError:
        if os.environ.get("PYGUARA_REQUIRE_GPU"):
            raise
        pytest.skip("no graphics adapter")
    try:
        assert crash._notes["renderer"] == "wgpu"
        assert crash._notes["gpu"]
    finally:
        app.shutdown()
