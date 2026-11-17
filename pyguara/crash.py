"""Crash reports: an unhandled exception leaves a file behind, and says where.

The report holds the traceback, the engine and Python versions, the
platform, which native store was in force, and whatever the engine
noted on the way, such as the renderer. It is written to the player's
data directory, and holds paths from their machine.

Opt-in, because the directory is named after the game. Install it
before the application is built, so a failure at startup is reported
too.

Example:
    from pyguara.crash import install_crash_reporter

    install_crash_reporter("Reclaimer")
    app = create_application()
    app.run(TitleScene(...))
"""

from __future__ import annotations

import contextlib
import datetime
import os
import platform
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

__all__ = [
    "CrashReporter",
    "clear_notes",
    "install_crash_reporter",
    "note",
    "uninstall_crash_reporter",
]

ExceptHook = Callable[
    [type[BaseException], BaseException, TracebackType | None], object
]

_notes: dict[str, str] = {}
_installed: CrashReporter | None = None


def note(key: str, value: object) -> None:
    """Record a fact for any crash report written from now on.

    The engine notes what it learns while starting -- the renderer chosen,
    for one -- so a report says what was running, not only where it failed.
    A game may note its own: the level, the build id. A later note under the
    same key replaces the earlier one.

    Args:
        key: A short name, written as `key: value`.
        value: Anything; written with `str()`.
    """
    _notes[key] = str(value)


def clear_notes() -> None:
    """Forget every noted fact. For tests, and for a game that restarts."""
    _notes.clear()


@dataclass
class CrashReporter:
    """The installed hook: where reports go, and the hook it chains to.

    Built by `install_crash_reporter()`, not directly.

    Attributes:
        app_name: The game's name, written into each report.
        directory: Where reports are written. Created on the first crash,
            not at install, so a game that never crashes leaves nothing.
        keep: How many reports to keep; older ones are deleted on write.
        previous_hook: The `sys.excepthook` this one replaced and calls
            after writing, so the traceback still reaches stderr.
        last_report: The most recent report written, or None.
    """

    app_name: str
    directory: Path
    keep: int
    previous_hook: ExceptHook
    last_report: Path | None = field(default=None)

    def __call__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        """Write a report, say where, then hand over to the previous hook.

        Never raises: a reporter that fails while reporting would replace
        the crash being reported with its own. A failure to write is said on
        stderr, and the previous hook runs regardless.
        """
        if not issubclass(exc_type, KeyboardInterrupt):
            try:
                self.last_report = self._write(exc_type, exc_value, exc_tb)
                _say(f"The game crashed. A report was written to {self.last_report}")
            except Exception as error:  # noqa: BLE001 -- must not mask the crash
                _say(f"The game crashed, and could not write a crash report: {error!r}")
        self.previous_hook(exc_type, exc_value, exc_tb)

    def _write(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now()
        path = self.directory / f"crash-{now:%Y%m%d-%H%M%S}-{os.getpid()}.txt"
        text = "".join(
            [
                f"{self.app_name} crashed at {now.isoformat(timespec='seconds')}\n\n",
                *(f"{key}: {value}\n" for key, value in _facts(self.app_name)),
                "\n",
                *traceback.format_exception(exc_type, exc_value, exc_tb),
            ]
        )
        path.write_text(text, encoding="utf-8")
        self._prune(keep=path)
        return path

    def _prune(self, keep: Path) -> None:
        # Names sort by time: crash-YYYYmmdd-HHMMSS-pid.txt.
        reports = sorted(self.directory.glob("crash-*.txt"))
        for old in reports[: max(len(reports) - self.keep, 0)]:
            if old != keep:
                old.unlink(missing_ok=True)


def install_crash_reporter(
    app_name: str,
    app_author: str | None = None,
    *,
    directory: Path | None = None,
    keep: int = 20,
) -> CrashReporter:
    """Write a report for any exception that would otherwise end the program.

    Replaces `sys.excepthook` and chains to the one it replaced, so the
    traceback still prints where there is a console. Installing again
    replaces the earlier reporter rather than stacking a second.

    Covers the main thread. An exception in another thread does not end the
    program, and is not reported.

    Args:
        app_name: The game's name: the directory name, and the report's
            first line.
        app_author: Vendor name, used only on Windows. Defaults to
            `app_name`.
        directory: Where to write, instead of `crashes/` in the per-user
            data directory.
        keep: How many reports to keep. At least 1.

    Returns:
        The installed reporter, whose `directory` says where reports go.

    Raises:
        ValueError: If `app_name` is empty or `keep` is below 1.
    """
    global _installed
    if not app_name:
        raise ValueError("app_name must be a non-empty string")
    if keep < 1:
        raise ValueError(f"keep must be at least 1, got {keep}")

    if directory is None:
        import platformdirs

        directory = (
            Path(platformdirs.user_data_dir(app_name, app_author, roaming=False))
            / "crashes"
        )

    uninstall_crash_reporter()
    reporter = CrashReporter(
        app_name=app_name,
        directory=directory,
        keep=keep,
        previous_hook=sys.excepthook,
    )
    sys.excepthook = reporter
    _installed = reporter
    return reporter


def uninstall_crash_reporter() -> None:
    """Put back the hook `install_crash_reporter()` replaced. A no-op if none."""
    global _installed
    if _installed is not None and sys.excepthook is _installed:
        sys.excepthook = _installed.previous_hook
    _installed = None


def _facts(app_name: str) -> list[tuple[str, str]]:
    """List what was running as `key: value` pairs, each guarded on its own."""
    import pyguara

    facts = [
        ("game", app_name),
        ("pyguara", pyguara.__version__),
        ("python", sys.version.split()[0]),
        ("platform", platform.platform()),
        ("frozen", str(bool(getattr(sys, "frozen", False)))),
    ]
    try:
        from pyguara import native

        facts.append(("native extension", native.describe()))
    except Exception as error:  # noqa: BLE001 -- a fact, not the crash
        facts.append(("native extension", f"unknown ({error!r})"))
    facts.extend(sorted(_notes.items()))
    return facts


def _say(message: str) -> None:
    # A windowed build has no stderr: sys.stderr is None there.
    if sys.stderr is not None:
        with contextlib.suppress(Exception):  # nowhere else to say it
            print(message, file=sys.stderr, flush=True)
