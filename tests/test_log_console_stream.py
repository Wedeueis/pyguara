"""A logger's console output goes to the stdout of the moment it logs.

`pyguara studio ops` swaps `sys.stdout` for stderr to keep stdout for its
protocol. A logger built before the swap kept the original stream, so a
warning from it landed in front of the first reply and broke the client.
"""

from __future__ import annotations

import io
import sys

import pytest

from pyguara.log.logger import EngineLogger
from pyguara.log.types import LogLevel


def test_a_logger_built_before_stdout_is_swapped_follows_the_swap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", before)
    logger = EngineLogger(
        "test.console.stream",
        LogLevel.INFO,
        event_dispatcher=None,
        log_file=None,
        console_output=True,
        propagate=False,
    )

    monkeypatch.setattr(sys, "stdout", after)
    logger.warning("after the swap")

    assert "after the swap" in after.getvalue()
    assert before.getvalue() == ""


def test_console_output_off_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    logger = EngineLogger(
        "test.console.off",
        LogLevel.INFO,
        event_dispatcher=None,
        log_file=None,
        console_output=False,
        propagate=False,
    )

    logger.warning("nowhere")

    assert stream.getvalue() == ""
