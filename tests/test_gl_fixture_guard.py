"""The shared GL fixture must not skip silently where GL is mandatory.

Every GL test in this repository skipped on CI for as long as CI had no
Mesa installed, and a skip reads as a pass: the pixel suites proved things
locally and nothing in the pipeline. `PYGUARA_REQUIRE_GL` is what turns
that into a failure, so it needs a test of its own -- it is precisely the
kind of guard that is never exercised until the day it matters.

The fixture body is called directly here, since the point is what it does
when no context can be created, which is not a state this machine can be
put into.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests import conftest


def _no_context(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("no display and no EGL")


@pytest.fixture
def without_gl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every context-creation attempt fail."""
    moderngl = pytest.importorskip("moderngl")
    monkeypatch.setattr(moderngl, "create_standalone_context", _no_context)


def test_it_skips_when_gl_is_merely_absent(
    without_gl: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A laptop with no GPU still runs the rest of the suite green."""
    monkeypatch.setattr(conftest, "REQUIRE_GL", False)

    with pytest.raises(pytest.skip.Exception, match="no standalone GL context"):
        next(conftest.gl_ctx.__wrapped__())  # type: ignore[attr-defined]


def test_it_fails_when_gl_is_required(
    without_gl: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(conftest, "REQUIRE_GL", True)

    with pytest.raises(pytest.fail.Exception, match="would have skipped silently"):
        next(conftest.gl_ctx.__wrapped__())  # type: ignore[attr-defined]


def test_the_failure_names_what_went_wrong(
    without_gl: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both attempts are reported, so a broken runner is diagnosable."""
    monkeypatch.setattr(conftest, "REQUIRE_GL", True)

    with pytest.raises(pytest.fail.Exception) as excinfo:
        next(conftest.gl_ctx.__wrapped__())  # type: ignore[attr-defined]

    message = str(excinfo.value)
    assert "default" in message and "egl" in message
    assert "no display and no EGL" in message
